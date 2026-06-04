"""
OpenAI-compatible gateway. Clients point their SDK here:

    from openai import OpenAI
    client = OpenAI(base_url="http://localhost:8000/v1",
                    api_key="<tenant-key or GATEWAY_MASTER_KEY>")

Request lifecycle:
  1.  Auth: tenant lookup in SQLite, fallback to master env key
  2.  PII redaction of the user prompts (optional, controlled per tenant)
  3.  Build cache namespace + look up cache
  4.  Classify -> tier (rule + nearest-centroid learned)
  5.  Apply tenant.min_tier floor
  6.  Budget check (monthly cap per tenant)
  7.  Inject Anthropic prompt-cache breakpoints
  8.  Call LiteLLM Router (with built-in provider fallbacks)
  9.  Optional cascade: cheap response -> verifier -> balanced retry
  10. Cache write + cost compute + record usage + post-hook log
  11. Return OpenAI-shaped response
"""
from __future__ import annotations
import asyncio
import copy
import hashlib
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

import classifier as classifier_module
import conversation
import persistence
import pii
import prompt_cache
import tenants
import verifier
from classifier import classify, RouteDecision
from pricing import compute_cost
from semantic_cache import SemanticCache

# --- Config ----------------------------------------------------------------
LOG = logging.getLogger("gateway")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")

GATEWAY_MASTER_KEY = os.environ.get("GATEWAY_MASTER_KEY", "")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
ENABLE_CACHE = os.environ.get("ENABLE_SEMANTIC_CACHE", "true").lower() == "true"
ENABLE_CLASSIFIER = os.environ.get("ENABLE_CLASSIFIER", "true").lower() == "true"
ENABLE_PII = os.environ.get("ENABLE_PII_REDACTION", "true").lower() == "true"
CACHE_THRESHOLD = float(os.environ.get("SEMANTIC_CACHE_THRESHOLD", "0.95"))
CACHE_TTL = int(os.environ.get("SEMANTIC_CACHE_TTL_SECONDS", "86400"))
SHADOW_LOG_PATH = os.environ.get("SHADOW_LOG_PATH", "/app/shadow_log.jsonl")
LITELLM_CONFIG = os.environ.get("LITELLM_CONFIG", "/app/litellm_config.yaml")

# Baseline cost = what we'd have paid sending everything to tier-balanced.
# Used by the persistence layer to compute "savings vs. baseline" per call.
BASELINE_IN_PER_TOK = 0.000003
BASELINE_OUT_PER_TOK = 0.000015

TIER_ORDER = {"cheap": 0, "balanced": 1, "frontier": 2}
state: dict[str, Any] = {}


# --- Lifespan -------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = yaml.safe_load(Path(LITELLM_CONFIG).read_text())

    # Build gateway metadata (cost + tier) from raw config, then strip
    # custom fields LiteLLM's ModelInfo schema doesn't accept.
    info_by_alias: dict[str, dict] = {}
    for entry in cfg["model_list"]:
        merged = {**entry.get("model_info", {}), **entry.get("gateway_info", {})}
        info_by_alias.setdefault(entry["model_name"], merged)
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
    state["cache"] = (
        SemanticCache(REDIS_URL, ttl_seconds=CACHE_TTL, threshold=CACHE_THRESHOLD)
        if ENABLE_CACHE else None
    )

    # Load trained classifier weights (warns + falls back on miss)
    if ENABLE_CLASSIFIER:
        classifier_module.load_weights()

    # Initialise the tenants DB (creates schema on first hit) and seed a
    # "default" tenant for backward compatibility when running pilot.sh,
    # which uses GATEWAY_MASTER_KEY as a single-tenant key.
    try:
        existing = tenants.list_tenants()
        if not existing and GATEWAY_MASTER_KEY:
            try:
                tenants.create_tenant(
                    tenant_id="default",
                    name="Default (master-key fallback)",
                    monthly_budget_usd=10000.0,
                    notes="Auto-created from GATEWAY_MASTER_KEY on first boot",
                )
                LOG.info("Created 'default' tenant for master-key bootstrap mode.")
            except Exception:
                pass
    except Exception:
        LOG.exception("tenants init failed")

    LOG.info("Gateway up. tiers=%s cache=%s classifier=%s pii=%s",
             list(info_by_alias.keys()), ENABLE_CACHE, ENABLE_CLASSIFIER, ENABLE_PII)
    yield


app = FastAPI(lifespan=lifespan, title="VIREN Gateway", version="0.2.0")


# --- Auth ------------------------------------------------------------------

def _resolve_tenant(authorization: str | None) -> tuple[str, tenants.Tenant | None]:
    """Returns (tenant_id, Tenant or None).

    Two auth paths:
      - Tenant key (viren_...) -> looked up in SQLite, full per-tenant config
      - GATEWAY_MASTER_KEY env -> admin/bootstrap, treated as tenant 'default'
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    # Try tenant store first
    if token.startswith("viren_"):
        t = tenants.lookup_by_key(token)
        if t is None:
            raise HTTPException(401, "invalid or revoked tenant key")
        return t.id, t

    # Master key fallback (kept for pilot.sh compatibility)
    if GATEWAY_MASTER_KEY and token == GATEWAY_MASTER_KEY:
        t = tenants.lookup_by_key(token)  # default tenant won't actually have this key
        # Treat as the "default" tenant if it exists, else just return id only
        try:
            default_row = next((d for d in tenants.list_tenants() if d["id"] == "default"), None)
        except Exception:
            default_row = None
        if default_row:
            # Build a Tenant from the row
            t = tenants.Tenant(
                id="default", name=default_row["name"],
                contact_email=default_row["contact_email"],
                min_tier=default_row["min_tier"],
                monthly_budget_usd=default_row["monthly_budget_usd"],
                allowed_models=[], active=bool(default_row["active"]),
            )
            return "default", t
        return "default", None

    raise HTTPException(401, "invalid api key")


# --- Prompt-cache injection (unchanged) -----------------------------------

def inject_prompt_cache(messages: list[dict]) -> list[dict]:
    if any(isinstance(m.get("content"), list) and any(
            isinstance(b, dict) and b.get("cache_control") for b in m["content"]
            ) for m in messages):
        return messages
    out = []
    for m in messages:
        if m.get("role") == "system" and isinstance(m.get("content"), str) and len(m["content"]) > 2000:
            out.append({
                "role": "system",
                "content": [{"type": "text", "text": m["content"],
                             "cache_control": {"type": "ephemeral"}}],
            })
        else:
            out.append(m)
    return out


# --- Cascade verifier -----------------------------------------------------

def looks_low_quality(response: dict, expects_json: bool = False) -> bool:
    choice = (response.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    finish = choice.get("finish_reason")

    if finish == "length":
        return True
    if isinstance(text, str):
        if len(text.strip()) < 4:
            return True
        low = text.strip().lower()
        if low in {"i don't know", "i cannot help", "as an ai"}:
            return True
        if "i'm not sure" in low and len(text) < 200:
            return True
        # If we asked for JSON, the response should parse as JSON.
        if expects_json:
            stripped = text.strip()
            if stripped.startswith("```"):
                parts = stripped.split("```", 2)
                # parts[0]="" parts[1]="json\n{...}\n" parts[2]="" — use middle
                stripped = parts[1].strip() if len(parts) > 1 else stripped
                if stripped.startswith("json"):
                    stripped = stripped[4:].strip()
            try:
                json.loads(stripped)
            except Exception:
                return True
    return False


# --- Endpoints ------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "ok": True,
        "tiers": list(state["model_info"].keys()),
        "version": app.version,
        "classifier_loaded": classifier_module._CENTROIDS is not None,
        "cache_enabled": state["cache"] is not None,
        "cache_degraded": (state["cache"].degraded
                          if state["cache"] is not None and hasattr(state["cache"], "degraded")
                          else None),
        "pii_redaction": ENABLE_PII,
    }


@app.get("/v1/models")
async def list_models(authorization: str | None = Header(None)):
    _resolve_tenant(authorization)
    return {"object": "list", "data": [
        {"id": name, "object": "model", "owned_by": "viren"} for name in state["model_info"]
    ]}


# --- Admin endpoints (master key only) ------------------------------------

def _require_master(authorization: str | None) -> None:
    if not GATEWAY_MASTER_KEY:
        raise HTTPException(403, "admin endpoints disabled (no master key)")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != GATEWAY_MASTER_KEY:
        raise HTTPException(403, "admin operation requires master key")


@app.post("/admin/tenants")
async def admin_create_tenant(request: Request, authorization: str | None = Header(None)):
    _require_master(authorization)
    body = await request.json()
    try:
        new_key = tenants.create_tenant(
            tenant_id=body["id"],
            name=body["name"],
            contact_email=body.get("contact_email"),
            min_tier=body.get("min_tier", "cheap"),
            monthly_budget_usd=float(body.get("monthly_budget_usd", 1000)),
            notes=body.get("notes"),
        )
        return {"id": body["id"], "api_key": new_key,
                "warning": "Store this key now — it cannot be retrieved later."}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/admin/tenants")
async def admin_list_tenants(authorization: str | None = Header(None)):
    _require_master(authorization)
    return {"tenants": tenants.list_tenants()}


@app.get("/admin/usage/{tenant_id}")
async def admin_usage(tenant_id: str, authorization: str | None = Header(None)):
    _require_master(authorization)
    summary = persistence.summarize(tenant_id=tenant_id)
    summary["budget"] = tenants.get_usage(tenant_id)
    return summary


# --- The main endpoint ----------------------------------------------------

@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    authorization: str | None = Header(None),
    x_min_tier: str | None = Header(None),
    x_route_hint: str | None = Header(None),
    x_no_cache: str | None = Header(None),
    x_no_pii_redact: str | None = Header(None),
    x_pilot_id: str | None = Header(None),
    x_conversation_id: str | None = Header(None),
):
    tenant_id, tenant_obj = _resolve_tenant(authorization)
    body = await request.json()

    messages: list[dict] = body.get("messages", [])
    requested_model: str = body.get("model", "tier-balanced")
    temperature: float | None = body.get("temperature")
    tools: list[dict] | None = body.get("tools")
    stream: bool = bool(body.get("stream"))
    expects_json = bool(body.get("response_format")) or (
        isinstance(body.get("response_format"), dict)
        and body["response_format"].get("type") == "json_object"
    )

    # ---- PII redaction (before anything reads the prompts) ---------------
    pii_entities: list[dict] = []
    if ENABLE_PII and not x_no_pii_redact:
        messages, pii_entities = pii.redact_messages(messages)
        body["messages"] = messages

    # ---- Budget guardrail ------------------------------------------------
    if tenant_obj is not None:
        over, spent, cap = tenants.over_budget(tenant_obj)
        if over:
            raise HTTPException(429, f"monthly budget exceeded: ${spent:.2f} / ${cap:.2f}")

    # ---- Tier decision ---------------------------------------------------
    if requested_model in state["model_info"]:
        decision = RouteDecision(
            tier=state["model_info"][requested_model].get("tier", "balanced"),
            reason="client requested tier explicitly",
            confidence=1.0,
        )
    elif ENABLE_CLASSIFIER:
        decision = classify(messages, body.get("max_tokens"))
    else:
        decision = RouteDecision("balanced", "classifier disabled", 0.5)

    # Apply header min-tier guardrail
    if x_min_tier and x_min_tier in TIER_ORDER:
        if TIER_ORDER[decision.tier] < TIER_ORDER[x_min_tier]:
            decision = RouteDecision(
                tier=x_min_tier,                                   # type: ignore[arg-type]
                reason=f"upgraded by x-min-tier={x_min_tier} (was {decision.tier})",
                confidence=decision.confidence,
            )

    # Apply per-tenant min-tier floor
    if tenant_obj is not None and tenant_obj.min_tier in TIER_ORDER:
        if TIER_ORDER[decision.tier] < TIER_ORDER[tenant_obj.min_tier]:
            decision = RouteDecision(
                tier=tenant_obj.min_tier,                          # type: ignore[arg-type]
                reason=f"tenant min_tier={tenant_obj.min_tier} (was {decision.tier})",
                confidence=decision.confidence,
            )

    # Conversation tier stickiness (v0.3.4): never drop below the highest tier
    # this conversation has used. Only routes UP — safe by construction.
    if len(messages) > 1 or x_conversation_id:
        try:
            conv_id = conversation.conversation_id(x_conversation_id, messages)
            eff_tier, sticky_reason = conversation.apply_stickiness(decision.tier, conv_id)
            if sticky_reason:
                decision = RouteDecision(tier=eff_tier, reason=sticky_reason,  # type: ignore[arg-type]
                                         confidence=decision.confidence)
        except Exception:
            LOG.exception("conversation stickiness failed (non-fatal)")

    chosen_alias = f"tier-{decision.tier}"

    # ---- Cache lookup ----------------------------------------------------
    cache: SemanticCache | None = (
        state["cache"] if (ENABLE_CACHE and not x_no_cache and not stream) else None
    )
    cache_hit = None
    if cache is not None:
        try:
            sys_hash = SemanticCache.hash_messages_system(messages)
            tool_hash = SemanticCache.hash_tools(tools)
            prompt_text = SemanticCache.prompt_text(messages)
            cache_hit = cache.lookup(
                prompt_text=prompt_text,
                tenant=tenant_id,
                model_class=chosen_alias,
                system_hash=sys_hash,
                tool_hash=tool_hash,
                temperature=temperature,
            )
        except Exception:
            LOG.exception("cache lookup failed (non-fatal)")

    if cache_hit is not None:
        resp = dict(cache_hit.response)
        resp["id"] = "cached-" + uuid.uuid4().hex[:12]
        await _post_hook(
            tenant_id=tenant_id, pilot_id=x_pilot_id, body=body, decision=decision,
            response=resp, latency_ms=0.0,
            cache_hit=cache_hit.source, cache_similarity=cache_hit.similarity,
            pii_entities=pii_entities,
        )
        return JSONResponse(resp)

    # ---- Prefix cache injection (v0.3.2) --------------------------------
    # Smarter than the old inject_prompt_cache: handles few-shot prefixes and
    # respects Anthropic's token minimum. We inject Anthropic-style breakpoints
    # unconditionally; litellm drop_params=True strips cache_control for
    # providers that don't support it (DeepSeek/OpenAI cache automatically),
    # so this is safe across the mixed-provider tiers.
    body["messages"] = prompt_cache.inject_cache_breakpoints(messages, "anthropic")

    # ---- Call -----------------------------------------------------------
    router: Router = state["router"]
    body_for_call = dict(body)
    body_for_call["model"] = chosen_alias

    if stream:
        return await _stream(router, body_for_call, tenant_id, decision, x_pilot_id, pii_entities)

    t0 = time.perf_counter()
    try:
        response = await router.acompletion(**body_for_call)
    except Exception as e:
        LOG.exception("router call failed")
        raise HTTPException(502, f"upstream error: {e}")
    latency_ms = (time.perf_counter() - t0) * 1000

    response_dict = response.model_dump() if hasattr(response, "model_dump") else dict(response)

    # ---- Cascade if cheap response looks weak ----------------------------
    # v0.3.1: LLM cascade verifier replaces the old heuristic-only check.
    # Heuristic pre-filter runs first (free); LLM grader only on responses
    # that survive it. Both gated by VERIFIER_MODE.
    cascade_used = False
    verifier_score = None
    if decision.tier == "cheap":
        try:
            vr = await verifier.verify(
                router, response_dict, messages, expects_json=expects_json,
                mode=(tenant_obj.verifier_mode if tenant_obj and getattr(tenant_obj, "verifier_mode", None) else None),
            )
            verifier_score = vr.score
            if vr.escalate:
                LOG.info("cascade: %s -> escalating to balanced", vr.reason)
                body_for_call["model"] = "tier-balanced"
                response = await router.acompletion(**body_for_call)
                response_dict = response.model_dump() if hasattr(response, "model_dump") else dict(response)
                decision = RouteDecision("balanced", f"cascade from cheap ({vr.reason})", 0.7)
                cascade_used = True
        except Exception:
            LOG.exception("cascade/verify failed; returning original cheap response")

    # ---- Cache write ----------------------------------------------------
    if cache is not None and not cascade_used:
        try:
            cache.store(
                prompt_text=SemanticCache.prompt_text(messages),
                response=response_dict,
                tenant=tenant_id,
                model_class=chosen_alias,
                system_hash=SemanticCache.hash_messages_system(messages),
                tool_hash=SemanticCache.hash_tools(tools),
                temperature=temperature,
            )
        except Exception:
            LOG.exception("cache write failed (non-fatal)")

    await _post_hook(
        tenant_id=tenant_id, pilot_id=x_pilot_id, body=body, decision=decision,
        response=response_dict, latency_ms=latency_ms,
        cache_hit=None, cache_similarity=None, cascade=cascade_used,
        pii_entities=pii_entities, verifier_score=verifier_score,
    )
    return JSONResponse(response_dict)


async def _stream(router, body, tenant_id, decision, pilot_id, pii_entities):
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
                tenant_id=tenant_id, pilot_id=pilot_id, body=body, decision=decision,
                response={"streamed_chunks": len(chunks)},
                latency_ms=latency_ms, cache_hit=None, cache_similarity=None,
                pii_entities=pii_entities,
            )
    return StreamingResponse(gen(), media_type="text/event-stream")


# --- Post-hook: record + log -----------------------------------------------

async def _post_hook(
    *, tenant_id: str, pilot_id: str | None, body: dict, decision: RouteDecision,
    response: dict, latency_ms: float, cache_hit: str | None,
    cache_similarity: float | None, cascade: bool = False,
    pii_entities: list[dict] | None = None, verifier_score: int | None = None,
) -> None:
    info = state["model_info"].get(f"tier-{decision.tier}", {})
    cost = compute_cost(
        response,
        input_cost_per_token=float(info.get("input_cost_per_token", 0)),
        output_cost_per_token=float(info.get("output_cost_per_token", 0)),
    ) if response.get("usage") else None

    in_tok = (response.get("usage") or {}).get("prompt_tokens") or 0
    out_tok = (response.get("usage") or {}).get("completion_tokens") or 0
    baseline_cost = in_tok * BASELINE_IN_PER_TOK + out_tok * BASELINE_OUT_PER_TOK

    msgs = body.get("messages") or []
    last_user = next((m.get("content") for m in reversed(msgs) if m.get("role") == "user"), "")
    prompt_text_for_hash = last_user if isinstance(last_user, str) else json.dumps(last_user)
    prompt_hash = hashlib.sha256(prompt_text_for_hash.encode()).hexdigest()[:16]

    record_event = {
        "ts": time.time(),
        "tenant": tenant_id,
        "pilot_id": pilot_id,
        "tier": decision.tier,
        "tier_reason": decision.reason,
        "tier_confidence": decision.confidence,
        "model_returned": response.get("model"),
        "latency_ms": round(latency_ms, 2),
        "cache_hit": cache_hit,
        "cache_similarity": cache_similarity,
        "cascade": cascade,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cached_input_tokens": cost.cached_input_tokens if cost else 0,
        "cost_usd": cost.total_cost if cost else 0.0,
        "baseline_cost_usd": baseline_cost,
        "pii_entities": pii_entities or [],
        "prompt_hash": prompt_hash,
        "verifier_score": verifier_score,
    }

    # 1. SQLite (canonical store)
    persistence.record(record_event)

    # 2. JSONL (debugging tail/grep)
    try:
        with open(SHADOW_LOG_PATH, "a") as f:
            f.write(json.dumps(record_event) + "\n")
    except Exception:
        LOG.exception("post-hook log write failed")

    # 3. Tenant usage counter
    try:
        tenants.record_usage(tenant_id, record_event["cost_usd"])
    except Exception:
        LOG.exception("tenant usage update failed")

    LOG.info("call tenant=%s tier=%s reason=%s cost=$%.5f baseline=$%.5f latency=%.0fms cache=%s pii=%d",
             tenant_id, decision.tier, decision.reason, record_event["cost_usd"],
             baseline_cost, latency_ms, cache_hit, len(pii_entities or []))
