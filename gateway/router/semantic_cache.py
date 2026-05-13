"""
Two-layer cache backed by Redis Stack:

  1. EXACT cache:    SET key=hash(prompt+params) -> response.  O(1), ~1ms.
  2. SEMANTIC cache: HNSW index over embeddings of normalised prompts.

Critical safety rules (see blueprint section 3):
  - Namespace by (tenant, model_class, system_hash, tool_hash, temp_bucket).
  - Skip writes for temperature > 0.3 unless caller opts in.
  - Skip writes when response includes tool_calls.
  - TTL is per-namespace; defaults short for safety.
  - Threshold is per-route; default 0.95 (conservative).
"""
from __future__ import annotations
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import redis
from redis.commands.search.field import VectorField, TagField, NumericField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query

from embeddings import embed, EMBED_DIM

INDEX_NAME = "semcache_idx"
KEY_PREFIX = "semcache:"


@dataclass
class CacheHit:
    response: dict
    similarity: float
    age_seconds: float
    source: str  # "exact" or "semantic"


def _ns_key(tenant: str, model_class: str, system_hash: str, tool_hash: str, temp_bucket: str) -> str:
    return f"{tenant}|{model_class}|{system_hash}|{tool_hash}|{temp_bucket}"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _temperature_bucket(t: float | None) -> str:
    if t is None:
        return "default"
    if t <= 0.05:
        return "deterministic"
    if t <= 0.3:
        return "low"
    return "high"


class SemanticCache:
    def __init__(self, url: str, ttl_seconds: int = 86400, threshold: float = 0.95):
        self.r = redis.Redis.from_url(url, decode_responses=False)
        self.ttl = ttl_seconds
        self.threshold = threshold
        self._ensure_index()

    def _ensure_index(self) -> None:
        try:
            self.r.ft(INDEX_NAME).info()
            return
        except redis.exceptions.ResponseError:
            pass

        schema = (
            VectorField(
                "embedding",
                "HNSW",
                {"TYPE": "FLOAT32", "DIM": EMBED_DIM, "DISTANCE_METRIC": "COSINE", "M": 16, "EF_CONSTRUCTION": 200},
            ),
            TagField("namespace"),
            NumericField("created_at"),
        )
        defn = IndexDefinition(prefix=[KEY_PREFIX], index_type=IndexType.HASH)
        self.r.ft(INDEX_NAME).create_index(schema, definition=defn)

    # --- public API --------------------------------------------------------

    def lookup(
        self,
        prompt_text: str,
        tenant: str,
        model_class: str,
        system_hash: str,
        tool_hash: str,
        temperature: float | None,
        threshold_override: float | None = None,
    ) -> CacheHit | None:
        ns = _ns_key(tenant, model_class, system_hash, tool_hash, _temperature_bucket(temperature))
        threshold = threshold_override if threshold_override is not None else self.threshold

        # 1. Exact lookup
        exact_key = KEY_PREFIX + "exact:" + _hash(ns + "::" + prompt_text)
        raw = self.r.get(exact_key)
        if raw:
            payload = json.loads(raw)
            return CacheHit(
                response=payload["response"],
                similarity=1.0,
                age_seconds=time.time() - payload["created_at"],
                source="exact",
            )

        # 2. Semantic KNN over the namespace
        vec = embed(prompt_text).tobytes()
        q = (
            Query(f"(@namespace:{{{ns}}})=>[KNN 1 @embedding $vec AS score]")
            .return_fields("payload", "score", "created_at")
            .dialect(2)
            .paging(0, 1)
        )
        try:
            res = self.r.ft(INDEX_NAME).search(q, query_params={"vec": vec})
        except redis.exceptions.ResponseError:
            return None
        if not res.docs:
            return None

        doc = res.docs[0]
        # Redis returns COSINE *distance* (1 - similarity). Convert.
        sim = 1.0 - float(doc.score)
        if sim < threshold:
            return None
        payload = json.loads(doc.payload)
        return CacheHit(
            response=payload["response"],
            similarity=sim,
            age_seconds=time.time() - float(doc.created_at),
            source="semantic",
        )

    def store(
        self,
        prompt_text: str,
        response: dict,
        tenant: str,
        model_class: str,
        system_hash: str,
        tool_hash: str,
        temperature: float | None,
        ttl_override: int | None = None,
    ) -> None:
        # Hard skips — never poison the cache.
        if temperature is not None and temperature > 0.3:
            return
        choice = (response.get("choices") or [{}])[0]
        if (choice.get("message") or {}).get("tool_calls"):
            return

        ns = _ns_key(tenant, model_class, system_hash, tool_hash, _temperature_bucket(temperature))
        ttl = ttl_override if ttl_override is not None else self.ttl
        now = time.time()

        # Exact write
        exact_key = KEY_PREFIX + "exact:" + _hash(ns + "::" + prompt_text)
        self.r.setex(exact_key, ttl, json.dumps({"response": response, "created_at": now}))

        # Semantic write
        vec = embed(prompt_text).tobytes()
        sem_key = KEY_PREFIX + "sem:" + _hash(ns + "::" + prompt_text + "::" + str(now))
        self.r.hset(
            sem_key,
            mapping={
                "embedding": vec,
                "namespace": ns,
                "created_at": now,
                "payload": json.dumps({"response": response, "created_at": now}),
            },
        )
        self.r.expire(sem_key, ttl)

    @staticmethod
    def hash_messages_system(messages: list[dict]) -> str:
        sys_msgs = [m.get("content", "") for m in messages if m.get("role") == "system"]
        return _hash("||".join(sys_msgs)) if sys_msgs else "nosys"

    @staticmethod
    def hash_tools(tools: list[dict] | None) -> str:
        if not tools:
            return "notools"
        return _hash(json.dumps(tools, sort_keys=True))

    @staticmethod
    def prompt_text(messages: list[dict]) -> str:
        # Cache key text = the user-visible turns. We exclude system because
        # system_hash already namespaces. This makes paraphrased user turns
        # collide as intended.
        parts = []
        for m in messages:
            if m.get("role") in ("user", "assistant"):
                c = m.get("content", "")
                if isinstance(c, str):
                    parts.append(f"{m['role']}: {c}")
        return "\n".join(parts)
