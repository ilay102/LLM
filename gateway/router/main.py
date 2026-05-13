"""
OpenAI-compatible gateway. Clients point their SDK here:

    from openai import OpenAI
    client = OpenAI(base_url="http://localhost:8000/v1",
                    api_key="<GATEWAY_MASTER_KEY>")

Request lifecycle:
  1.  Auth & parse                                 (this file)
  2.  Build cache namespace (system_hash, etc.)    (semantic_cache.py)
  3.  Cache lookup                                  -> hit?  return immediately
  4.  Classify -> tier (cheap/balanced/frontier)   (classifier.py)
  5.  Inject Anthropic prompt-cache breakpoints    (this file)
  6.  Call LiteLLM Router with tier alias          (LiteLLM does fallbacks)
  7.  Optional cascade: if response looks weak on tier-cheap, retry on
      tier-balanced. Whichever judge says "good" returns.
  8.  Cache write + cost compute + post-hook log
  9.  Return OpenAI-shaped response

Streaming: kept simple for now (we proxy non-streaming first; the cascade and
cache decisions are hard to do correctly mid-stream — see blueprint risk #2).
Streaming requests bypass the cache write but still get routed.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import litellm
import yaml
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from litellm import Router
from pydantic import BaseModel

from classifier import classify, RouteDecision
from pricing import compute_cost
from semantic_cache import SemanticCache

# --- Config ----------------------------------------------------------------
LOG = logging.getLogger("gateway")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")

GATEWAY_KEY = os.environ["GATEWAY_MASTER_KEY"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
ENABLE_CACHE = os.environ.get("ENABLE_SEMANTIC_CACHE", "true").lower() == "true"
ENABLE_CLASSIFIER = os.environ.get("ENABLE_CLASSIFIER", "true").lower() == "true"
CACHE_THRESHOLD = float(os.environ.get("SEMANTIC_CACHE_THRESHOLD", "0.95"))
CACHE_TTL = int(os.environ.get("SEMANTIC_CACHE_TTL_SECONDS", "86400"))
SHADOW_LOG_PATH = os.environ.get("SHADOW_LOG_PATH", "/app/shadow_log.jsonl")
LITELLM_CONFIG = os.environ.get("LITELLM_CONFIG", "/app/litellm_config.yaml")

# Tier-allowlist guardrails for cost control. A tenant can pin minimum tier
# per route via the `x-min-tier` request header (e.g. "balanced" forbids cheap).
TIER_ORDER = {"cheap": 0, "balanced": 1, "frontier": 2}


# --- Lifespan: load LiteLLM Router + cache ---------------------------------
state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    import copy
    cfg = yaml.safe_load(Path(LITELLM_CONFIG).read_text())

    # Build gateway metadata (cost + tier) from the raw config before stripping
    # custom fields that LiteLLM's ModelInfo schema doesn't accept.
    info_by_alias: dict[str, dict] = {}
    for entry in cfg["model_list"]:
        merged = {**entry.get("model_info", {}), **entry.get("gateway_info", {})}
        info_by_alias.setdefault(entry["model_name"], merged)

    # Strip gateway_info from model_list entries so LiteLLM validation passes.
    clean_model_list = copy.deepcopy(cfg["model_list"])
    for entry in clean_model_list:
        entry.pop("gateway_info", None)

    router = Router(
        model_list=clean_model_list,
        fallbacks=cfg.get("litellm_settings", {}).get("fallbacks", []),
        num_retries=cfg.get("litellm_settings", {}).get("num_retries", 2),
        timeout=cfg.get("litellm_settings", {}).get("request_timeout", 60),
        allowed_fails=cfg.get("router_settings", {}).get("allowed_fails", 3),
        cooldown_time=cfg.get("router_settings", {}).get("cooldown_time", 30),
    )

    state["router"] = router
    state["model_info"] = info_by_alias
    state["cache"] = SemanticCache(REDIS_URL, ttl_seconds=CACHE_TTL, threshold=CACHE_THRESHOLD) if ENABLE_CACHE else None
    LOG.info("Gateway up. tiers=%s cache=%s classifier=%s",
             list(info_by_alias.keys()), ENABLE_CACHE, ENABLE_CLASSIFIER)
    yield


app = FastAPI(lifespan=lifespan, title="MSP LLM Gateway", version="0.1.0")


# --- Auth ------------------------------------------------------------------
def _check_auth(authorization: str | None) -> str:
    """Return tenant_id. For dev we accept the master key for tenant 'default'."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != GATEWAY_KEY:
        raise HTTPException(401, "invalid api key")
    return "default"


# --- Anthropic prompt-cache injection --------------------------------------
def inject_prompt_cache(messages: list[dict]) -> list[dict]:
    """
    Add `cache_control: {type: 'ephemeral'}` to the LAST static system block
    and to the second-to-last user message (the typical RAG context boundary).
    Anthropic charges 90% off on cache reads; LiteLLM forwards this verbatim.

    Skip if any message already has cache_control set (caller knows better).
    """
    if any(isinstance(m.get("content"), list) and any(
            isinstance(b, dict) and b.get("cache_control") for b in m["content"]
            ) for m in messages):
        return messages

    out = []
    for i, m in enumerate(messages):
        if m.get("role") == "system" and isinstance(m.get("content"), str) and len(m["content"]) > 2000:
            out.append({
                "role": "system",
                "content": [{"type": "text", "text": m["content"], "cache_control": {"type": "ephemeral"}}],
            })
        else:
            out.append(m)
    return out


# --- Cascade verifier ------------------------------------------------------
def looks_low_quality(response: dict) -> bool:
    """
    Heuristic-only verifier for the cascade. Cheap, no LLM call.
    A real deployment plugs in a small classifier; here we use signals that
    correlate with bad small-model output.
    """
    choice = (response.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    finish = choice.get("finish_reason")

    if finish == "length":          # hit max_tokens — likely truncated answer
        return True
    if isinstance(text, str):
        if len(text.strip()) < 4:
            return True
        if text.strip().lower() in {"i don't know", "i cannot help", "as an ai"}:
            return True
        # Refusal / hedge markers from weaker models
        if "i'm not sure" in text.lower() and len(text) < 200:
            return True
    return False


# --- Endpoints -------------------------------------------------------------
@app.get("/health")
async def health():
    return {"ok": True, "tiers": list(state["model_info"].keys())}


@app.get("/v1/models")
async def list_models(authorization: str | None = Header(None)):
    _check_auth(authorization)
    # Advertise the tier aliases as if they were models. Clients ask for these.
    return {"object": "list", "data": [
        {"id": name, "object": "model", "owned_by": "msp-gateway"} for name in state["model_info"]
    ]}


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    authorization: str | None = Header(None),
    x_min_tier: str | None = Header(None),         # tenant guardrail
    x_route_hint: str | None = Header(None),        # client-provided hint
    x_no_cache: str | None = Header(None),          # opt out of cache
):
    tenant = _check_auth(authorization)
    body = await request.json()

    messages: list[dict] = body.get("messages", [])
    requested_model: str = body.get("model", "tier-balanced")
    temperature: float | None = body.get("temperature")
    tools: list[dict] | None = body.get("tools")
    stream: bool = bool(body.get("stream"))

    # ---- 1. Decide tier ------------------------------------------------
    if requested_model in state["model_info"]:
        # Client asked for a specific tier alias -> respect it. They opted in.
        decision = RouteDecision(
            tier=state["model_info"][requested_model].get("tier", "balanced"),
            reason="client requested tier explicitly",
            confidence=1.0,
        )
    elif ENABLE_CLASSIFIER:
        decision = classify(messages, body.get("max_tokens"))
    else:
        decision = RouteDecision("balanced", "classifier disabled", 0.5)

    # Apply min-tier guardrail
    if x_min_tier and x_min_tier in TIER_ORDER:
        if TIER_ORDER[decision.tier] < TIER_ORDER[x_min_tier]:
            decision = RouteDecision(
                tier=x_min_tier,                                   # type: ignore[arg-type]
                reason=f"upgraded by x-min-tier={x_min_tier} (was {decision.tier})",
                confidence=decision.confidence,
            )

    chosen_alias = f"tier-{decision.tier}"

    # ---- 2. Cache lookup ----------------------------------------------
    cache: SemanticCache | None = state["cache"] if (ENABLE_CACHE and not x_no_cache and not stream) else None
    cache_hit = None
    if cache is not None:
        sys_hash = SemanticCache.hash_messages_system(messages)
        tool_hash = SemanticCache.hash_tools(tools)
        prompt_text = SemanticCache.prompt_text(messages)
        cache_hit = cache.lookup(
            prompt_text=prompt_text,
            tenant=tenant,
            model_class=chosen_alias,
            system_hash=sys_hash,
            tool_hash=tool_hash,
            temperature=temperature,
        )

    if cache_hit is not None:
        resp = dict(cache_hit.response)
        resp["id"] = "cached-" + uuid.uuid4().hex[:12]
        await _post_hook(
            tenant=tenant, body=body, decision=decision, response=resp,
            latency_ms=0.0, cache_hit=cache_hit.source, cache_similarity=cache_hit.similarity,
        )
        return JSONResponse(resp)

    # ---- 3. Inject prompt-cache breakpoints ----------------------------
    body["messages"] = inject_prompt_cache(messages)

    # ---- 4. Call the chosen tier --------------------------------------
    router: Router = state["router"]
    body_for_call = dict(body)
    body_for_call["model"] = chosen_alias

    if stream:
        # Streaming path: no cascade, no cache write. Pure passthrough.
        return await _stream(router, body_for_call, tenant, decision)

    t0 = time.perf_counter()
    try:
        response = await router.acompletion(**body_for_call)
    except Exception as e:
        LOG.exception("router call failed")
        raise HTTPException(502, f"upstream error: {e}")
    latency_ms = (time.perf_counter() - t0) * 1000

    # LiteLLM returns a pydantic object; normalise to dict
    response_dict = response.model_dump() if hasattr(response, "model_dump") else dict(response)

    # ---- 5. Cascade if cheap response looks weak ----------------------
    cascade_used = False
    if decision.tier == "cheap" and looks_low_quality(response_dict):
        LOG.info("cascade: cheap response failed verifier, retrying on balanced")
        body_for_call["model"] = "tier-balanced"
        try:
            response = await router.acompletion(**body_for_call)
            response_dict = response.model_dump() if hasattr(response, "model_dump") else dict(response)
            decision = RouteDecision("balanced", "cascade from cheap (verifier failed)", 0.7)
            cascade_used = True
        except Exception:
            LOG.exception("cascade retry failed; returning original cheap response")

    # ---- 6. Cache write -----------------------------------------------
    if cache is not None and not cascade_used:  # don't cache the upgraded answer under cheap key
        try:
            cache.store(
                prompt_text=SemanticCache.prompt_text(messages),
                response=response_dict,
                tenant=tenant,
                model_class=chosen_alias,
                system_hash=SemanticCache.hash_messages_system(messages),
                tool_hash=SemanticCache.hash_tools(tools),
                temperature=temperature,
            )
        except Exception:
            LOG.exception("cache write failed (non-fatal)")

    await _post_hook(
        tenant=tenant, body=body, decision=decision, response=response_dict,
        latency_ms=latency_ms, cache_hit=None, cache_similarity=None, cascade=cascade_used,
    )
    return JSONResponse(response_dict)


async def _stream(router: Router, body: dict, tenant: str, decision: RouteDecision):
    """Minimal SSE proxy. No cascade, no cache."""
    async def gen():
        t0 = time.perf_counter()
        chunks: list[str] = []
        try:
            stream = await router.acompletion(**body, stream=True)
            async for chunk in stream:
                data = chunk.model_dump() if hasattr(chunk, "model_dump") else dict(chunk)
                payload = json.dumps(data)
                chunks.append(payload)
                yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            latency_ms = (time.perf_counter() - t0) * 1000
            await _post_hook(
                tenant=tenant, body=body, decision=decision,
                response={"streamed_chunks": len(chunks)},
                latency_ms=latency_ms, cache_hit=None, cache_similarity=None,
            )
    return StreamingResponse(gen(), media_type="text/event-stream")


# --- Post-hook: append a structured log line for every call ----------------
async def _post_hook(
    *, tenant: str, body: dict, decision: RouteDecision, response: dict,
    latency_ms: float, cache_hit: str | None, cache_similarity: float | None,
    cascade: bool = False,
) -> None:
    info = state["model_info"].get(f"tier-{decision.tier}", {})
    cost = compute_cost(
        response,
        input_cost_per_token=float(info.get("input_cost_per_token", 0)),
        output_cost_per_token=float(info.get("output_cost_per_token", 0)),
    ) if response.get("usage") else None

    record = {
        "ts": time.time(),
        "tenant": tenant,
        "tier": decision.tier,
        "tier_reason": decision.reason,
        "tier_confidence": decision.confidence,
        "model_returned": response.get("model"),
        "latency_ms": round(latency_ms, 2),
        "cache_hit": cache_hit,
        "cache_similarity": cache_similarity,
        "cascade": cascade,
        "input_tokens": response.get("usage", {}).get("prompt_tokens"),
        "output_tokens": response.get("usage", {}).get("completion_tokens"),
        "cost_usd": cost.total_cost if cost else 0.0,
        "request_excerpt": (body.get("messages") or [{}])[-1].get("content", "")[:300] if body.get("messages") else "",
    }
    try:
        with open(SHADOW_LOG_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        LOG.exception("post-hook log write failed")
    LOG.info("call tier=%s reason=%s cost=$%.5f latency=%.0fms cache=%s",
             decision.tier, decision.reason, record["cost_usd"], latency_ms, cache_hit)
