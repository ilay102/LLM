"""
The rigorous pairwise judge. Run AFTER `promptfoo eval` (or instead of, if you
want a self-contained pipeline).

What it does, per prompt in dataset.jsonl:
  1. Calls the BASELINE   (Sonnet 4.6 direct) — what the client pays for today
  2. Calls the SHADOW     (the gateway, which routes to cheap/balanced/frontier)
  3. Randomises A/B order, sends both to JUDGE (Sonnet 4.6 by default; pass
     --judge-opus for Opus 4.7) with judge_prompt.txt
  4. Parses {"winner":..., "axis":..., "reason":...}
  5. Records cost (server-side from token usage) + latency
  6. Writes pairwise_results.jsonl  →  consumed by generate_report.py

Output is a JSONL of:
  {prompt, baseline_text, shadow_text, gateway_tier, winner, axis, reason,
   baseline_cost, shadow_cost, baseline_latency_ms, shadow_latency_ms,
   ...}

This is what generate_report.py turns into the executive HTML.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import random
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8000/v1")
GATEWAY_KEY = os.environ.get("GATEWAY_KEY", "dev-key-change-me")

# ---- Pricing for Sonnet 4.6 baseline (USD per token) ----------------------
SONNET_IN = 3.0 / 1_000_000
SONNET_OUT = 15.0 / 1_000_000
# Gateway reports its own cost via /v1 response usage + our pricing.py logs
# in shadow_log.jsonl — we recompute here using returned model name.
PRICE_TABLE = {
    "claude-haiku-4-5-20251001":  (0.80 / 1e6, 4.0 / 1e6),
    "claude-sonnet-4-6":          (3.0 / 1e6, 15.0 / 1e6),
    "claude-opus-4-7":            (15.0 / 1e6, 75.0 / 1e6),
    "gpt-4o-mini":                (0.15 / 1e6, 0.60 / 1e6),
}

JUDGE_PROMPT = Path(__file__).with_name("judge_prompt.txt").read_text()


@dataclass
class PairResult:
    prompt: str
    baseline_text: str
    shadow_text: str
    gateway_model: str
    winner: str            # "BASELINE" | "SHADOW" | "TIE"
    judge_axis: str
    judge_reason: str
    baseline_cost: float
    shadow_cost: float
    baseline_in_tokens: int
    shadow_in_tokens: int
    baseline_out_tokens: int
    shadow_out_tokens: int
    baseline_latency_ms: float
    shadow_latency_ms: float


def price_for(model: str) -> tuple[float, float]:
    for k, v in PRICE_TABLE.items():
        if k in model:
            return v
    return (SONNET_IN, SONNET_OUT)  # safe default


async def call_baseline(client: AsyncAnthropic, prompt: str) -> tuple[str, dict, float]:
    t0 = time.perf_counter()
    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    dt = (time.perf_counter() - t0) * 1000
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    usage = {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens, "model": resp.model}
    return text, usage, dt


async def call_shadow(client: AsyncOpenAI, prompt: str) -> tuple[str, dict, float]:
    t0 = time.perf_counter()
    resp = await client.chat.completions.create(
        model="auto",   # gateway classifies & picks tier
        max_tokens=1024,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    dt = (time.perf_counter() - t0) * 1000
    text = resp.choices[0].message.content or ""
    usage = {
        "in": resp.usage.prompt_tokens,
        "out": resp.usage.completion_tokens,
        "model": resp.model or "unknown",
    }
    return text, usage, dt


async def judge_pair(
    client: AsyncAnthropic, judge_model: str, prompt: str, a: str, b: str
) -> tuple[str, str, str]:
    body = JUDGE_PROMPT.replace("<<<USER_PROMPT>>>", prompt) \
                       .replace("<<<RESPONSE_A>>>", a) \
                       .replace("<<<RESPONSE_B>>>", b)
    resp = await client.messages.create(
        model=judge_model,
        max_tokens=300,
        temperature=0.0,
        messages=[{"role": "user", "content": body}],
    )
    raw = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
    # Parse the single-line JSON
    try:
        # Find first {...} in case the model added prose
        start = raw.index("{"); end = raw.rindex("}") + 1
        verdict = json.loads(raw[start:end])
    except Exception:
        return "TIE", "parse_error", raw[:200]
    return (
        verdict.get("winner", "TIE").upper(),
        verdict.get("axis", "n/a"),
        verdict.get("reason", "")[:300],
    )


async def evaluate_one(
    sem: asyncio.Semaphore,
    anth: AsyncAnthropic,
    oai: AsyncOpenAI,
    judge_model: str,
    prompt: str,
    seed: int,
) -> PairResult:
    async with sem:
        # Run both sides concurrently
        (b_text, b_usage, b_lat), (s_text, s_usage, s_lat) = await asyncio.gather(
            call_baseline(anth, prompt),
            call_shadow(oai, prompt),
        )

        # Randomise A/B to remove position bias
        rng = random.Random(seed)
        if rng.random() < 0.5:
            a_label, a_text = "BASELINE", b_text
            b_label, b_text2 = "SHADOW", s_text
        else:
            a_label, a_text = "SHADOW", s_text
            b_label, b_text2 = "BASELINE", b_text

        winner_letter, axis, reason = await judge_pair(anth, judge_model, prompt, a_text, b_text2)
        if winner_letter == "A":
            winner = a_label
        elif winner_letter == "B":
            winner = b_label
        else:
            winner = "TIE"

        b_in_p, b_out_p = price_for(b_usage["model"])
        s_in_p, s_out_p = price_for(s_usage["model"])

        return PairResult(
            prompt=prompt,
            baseline_text=b_text,
            shadow_text=s_text,
            gateway_model=s_usage["model"],
            winner=winner,
            judge_axis=axis,
            judge_reason=reason,
            baseline_cost=b_usage["in"] * b_in_p + b_usage["out"] * b_out_p,
            shadow_cost=s_usage["in"] * s_in_p + s_usage["out"] * s_out_p,
            baseline_in_tokens=b_usage["in"],
            shadow_in_tokens=s_usage["in"],
            baseline_out_tokens=b_usage["out"],
            shadow_out_tokens=s_usage["out"],
            baseline_latency_ms=b_lat,
            shadow_latency_ms=s_lat,
        )


async def amain() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="dataset.jsonl")
    p.add_argument("--out", default="pairwise_results.jsonl")
    p.add_argument("--judge-opus", action="store_true", help="Use Opus 4.7 as judge (more rigorous, more expensive)")
    p.add_argument("--concurrency", type=int, default=4)
    args = p.parse_args()

    judge_model = "claude-opus-4-7" if args.judge_opus else "claude-sonnet-4-6"
    print(f"judge: {judge_model}")

    anth = AsyncAnthropic(api_key=ANTHROPIC_KEY)
    oai = AsyncOpenAI(base_url=GATEWAY_URL, api_key=GATEWAY_KEY)

    prompts: list[str] = []
    with open(args.dataset) as f:
        for line in f:
            row = json.loads(line)
            prompts.append(row["vars"]["prompt"])

    sem = asyncio.Semaphore(args.concurrency)
    tasks = [evaluate_one(sem, anth, oai, judge_model, p, seed=i) for i, p in enumerate(prompts)]
    results: list[PairResult] = []
    for fut in asyncio.as_completed(tasks):
        r = await fut
        results.append(r)
        print(f"  [{len(results)}/{len(prompts)}] winner={r.winner} "
              f"savings=${(r.baseline_cost - r.shadow_cost)*1000:.3f}/1k "
              f"tier={r.gateway_model}")

    with open(args.out, "w") as f:
        for r in results:
            f.write(json.dumps(asdict(r)) + "\n")
    print(f"\nwrote {len(results)} rows to {args.out}")


if __name__ == "__main__":
    asyncio.run(amain())
