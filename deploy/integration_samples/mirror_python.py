"""
mirror_python.py — drop-in async traffic mirror for Python apps.

What this does:
    Your production code keeps calling OpenAI / Anthropic exactly as before.
    Every request is ALSO sent (fire-and-forget) to the VIREN gateway, so
    we can build a side-by-side comparison without touching your hot path.

Properties you should care about:
    - Mirror runs in an asyncio background task; never blocks the caller.
    - Never raises out of the mirror — your prod call always returns first.
    - If the gateway is unreachable, the mirror call is dropped silently.
    - Mirror requests carry an x-pilot-id header so we can group them.

Usage — minimal (3 lines):

    from mirror_python import attach_mirror
    from openai import OpenAI

    real_client = OpenAI(api_key="<your-real-openai-key>")
    attach_mirror(real_client, gateway_url="https://gw.example.com/v1",
                  gateway_key="<pilot-key-we-gave-you>", pilot_id="acme-pilot-1")

    # Now use real_client exactly as before — mirror happens in background.
    resp = real_client.chat.completions.create(model="gpt-4o", messages=[...])

Notes:
    - Works with both sync and async OpenAI SDK clients.
    - To mirror only a subset of routes (e.g. only the support-bot route),
      pass a `should_mirror=lambda kwargs: ...` predicate.
    - You can also mirror Anthropic clients (anthropic.Anthropic) — see
      attach_mirror_anthropic() at the bottom.
"""
from __future__ import annotations
import asyncio
import logging
import threading
import time
from typing import Any, Callable
import urllib.error
import urllib.request
import json

log = logging.getLogger("viren.mirror")

# --- Shared async loop running on a daemon thread --------------------------
# So we can fire-and-forget from any caller (sync or async) safely.

_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_LOCK = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    global _LOOP
    if _LOOP is not None:
        return _LOOP
    with _LOOP_LOCK:
        if _LOOP is None:
            loop = asyncio.new_event_loop()
            t = threading.Thread(target=loop.run_forever, daemon=True, name="viren-mirror-loop")
            t.start()
            _LOOP = loop
    return _LOOP


def _fire_and_forget(coro):
    """Schedule a coroutine on the background loop; never blocks the caller."""
    loop = _get_loop()
    asyncio.run_coroutine_threadsafe(coro, loop)


# --- The actual mirror call ------------------------------------------------

async def _mirror_call(
    gateway_url: str,
    gateway_key: str,
    pilot_id: str,
    payload: dict,
    timeout: float = 10.0,
) -> None:
    """Fire a single chat-completions call to the gateway. Swallows ALL errors."""
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=gateway_url.rstrip("/") + "/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {gateway_key}",
                "x-pilot-id": pilot_id,
            },
        )
        # Note: urllib is sync; we run it in an executor so the loop stays free.
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: urllib.request.urlopen(req, timeout=timeout).read(),
        )
    except Exception as e:
        # Mirror is best-effort. Never let it surface.
        log.debug("mirror dropped: %s", e)


def _build_payload(kwargs: dict, model_override: str | None) -> dict:
    """Take an OpenAI SDK call kwargs and return an OpenAI-compatible request body."""
    out = {
        "model": model_override or kwargs.get("model") or "auto",
        "messages": kwargs.get("messages") or [],
    }
    # Pass-through optional fields the gateway understands
    for k in ("temperature", "max_tokens", "top_p", "stop", "tools", "tool_choice",
              "response_format"):
        if k in kwargs:
            out[k] = kwargs[k]
    return out


# --- Public API: OpenAI client wrapper -------------------------------------

def attach_mirror(
    client: Any,
    *,
    gateway_url: str,
    gateway_key: str,
    pilot_id: str,
    model_override: str = "auto",
    should_mirror: Callable[[dict], bool] | None = None,
    sample_rate: float = 1.0,
) -> None:
    """
    Wrap `client.chat.completions.create` in place so every call also fires
    a mirror request to the gateway in the background.

    Args:
        client:         An openai.OpenAI or openai.AsyncOpenAI instance.
        gateway_url:    e.g. "https://viren-gw.your-vpc/v1"
        gateway_key:    The Bearer token we gave you (starts with "pilot-...").
        pilot_id:       Free-form string we use to group your pilot's data.
        model_override: What model to ask the gateway to use. Default "auto"
                        lets the gateway's classifier pick.
        should_mirror:  Optional predicate; mirrors only when it returns True.
        sample_rate:    Float 0.0-1.0. Mirror only this fraction of requests.
    """
    import random

    original_create = client.chat.completions.create

    # Detect sync vs async
    is_async = asyncio.iscoroutinefunction(original_create)

    def _maybe_mirror(call_kwargs: dict) -> None:
        if sample_rate < 1.0 and random.random() > sample_rate:
            return
        if should_mirror and not should_mirror(call_kwargs):
            return
        payload = _build_payload(call_kwargs, model_override)
        _fire_and_forget(_mirror_call(gateway_url, gateway_key, pilot_id, payload))

    if is_async:
        async def wrapped(**kwargs):
            _maybe_mirror(kwargs)
            return await original_create(**kwargs)
    else:
        def wrapped(**kwargs):
            _maybe_mirror(kwargs)
            return original_create(**kwargs)

    client.chat.completions.create = wrapped  # type: ignore[assignment]


# --- Optional: Anthropic SDK mirror ----------------------------------------

def attach_mirror_anthropic(
    client: Any,
    *,
    gateway_url: str,
    gateway_key: str,
    pilot_id: str,
    model_override: str = "auto",
    sample_rate: float = 1.0,
) -> None:
    """Same idea, but for an anthropic.Anthropic client.messages.create."""
    import random
    original = client.messages.create
    is_async = asyncio.iscoroutinefunction(original)

    def _to_openai_payload(kwargs: dict) -> dict:
        # Anthropic and OpenAI message formats are compatible enough for
        # the gateway, which accepts both. We just rename the fields.
        return {
            "model": model_override or kwargs.get("model") or "auto",
            "messages": kwargs.get("messages") or [],
            "max_tokens": kwargs.get("max_tokens", 1024),
            **{k: v for k, v in kwargs.items() if k in ("temperature", "top_p", "stop_sequences", "tools")},
        }

    def _maybe_mirror(call_kwargs: dict) -> None:
        if sample_rate < 1.0 and random.random() > sample_rate:
            return
        payload = _to_openai_payload(call_kwargs)
        _fire_and_forget(_mirror_call(gateway_url, gateway_key, pilot_id, payload))

    if is_async:
        async def wrapped(**kwargs):
            _maybe_mirror(kwargs)
            return await original(**kwargs)
    else:
        def wrapped(**kwargs):
            _maybe_mirror(kwargs)
            return original(**kwargs)

    client.messages.create = wrapped  # type: ignore[assignment]


# --- Demo --------------------------------------------------------------------
if __name__ == "__main__":
    # Demo with the OpenAI SDK. Requires: pip install openai
    import os
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "sk-dummy"))
    attach_mirror(
        client,
        gateway_url=os.environ.get("GATEWAY_URL", "http://localhost:8000/v1"),
        gateway_key=os.environ.get("GATEWAY_KEY", "dev-key"),
        pilot_id="demo",
    )
    print("Mirror attached. Making a normal call...")
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say hi in 5 words."}],
        max_tokens=20,
    )
    print("Prod response:", resp.choices[0].message.content)
    print("(Mirror is firing in the background — check the gateway logs.)")
    time.sleep(2)  # let the mirror complete before the process exits
