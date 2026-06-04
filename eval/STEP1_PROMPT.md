# STEP 1 — Isolated gate for the two SAFE wins (paste to Claude Code in Codespace)

Goal: confirm prefix caching + tier stickiness improve cost without hurting
quality, with the (parked) LLM verifier OFF. ~$4 in API. Then we stop.

```
Run the isolated SAFE-wins gate. Branch v0.3.4-conversation has prefix caching
+ stickiness, and the verifier now defaults to "heuristic" (safe, no extra LLM
call). We are testing prefix-cache + stickiness ONLY — verifier stays heuristic.

1. git fetch origin && git checkout v0.3.4-conversation && git pull
2. In gateway/.env make sure: VERIFIER_MODE=heuristic
3. cd gateway && docker compose up --build -d && sleep 90
   curl -s http://localhost:8000/health | python3 -m json.tool
4. pip install --user pytest-asyncio==0.24.0 && pytest -m unit -q   # all green?

5. Baseline = current v0.2.2 behavior numbers we already have (87.4% / 80.0%).
   Now run THIS build on the full corpus:
   docker compose -f gateway/docker-compose.yml exec -T redis redis-cli FLUSHDB
   GATEWAY_URL=http://localhost:8000/v1 GATEWAY_KEY="$GATEWAY_MASTER_KEY" \
     ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
     python3 scripts/eval_corpus.py --limit 60 --results scripts/eval_safe.jsonl

6. Run it a SECOND time WITHOUT flushing (so the prefix cache is warm) to see
   the cache benefit on the RAG/long-system-prompt rows:
   GATEWAY_URL=http://localhost:8000/v1 GATEWAY_KEY="$GATEWAY_MASTER_KEY" \
     ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
     python3 scripts/eval_corpus.py --limit 60 --results scripts/eval_safe_warm.jsonl

7. 3-judge ensemble on the cold run:
   ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" OPENAI_API_KEY="$OPENAI_API_KEY" \
     python3 scripts/judge_ensemble.py --results scripts/eval_safe.jsonl \
       --label v0.3-safe --out-report scripts/q_safe.html

8. Report:
   - majority W-T (vs 80.0% baseline) — must be >= 78% (within noise, no regression)
   - total cost cold vs warm — warm should be LOWER (prefix cache working)
   - any errors on non-Anthropic rows (would mean cache_control leaked)
   - cheap-tier p95 latency (should be normal — no verifier grader call)

DECISION:
  MERGE (v0.3-quality -> v0.3.2-prefix-cache -> v0.3.4-conversation -> main, tag
  v0.3.0) IF: W-T within 2pp of 80% AND warm-run cost < cold-run cost AND zero
  non-Anthropic errors.
  Otherwise PARK and keep v0.2.2.

Do not ask — run it, report the numbers, make the call per the criteria, and if
it passes, do the merge + tag + push. Also refresh COMPARISON.md with the row.
```

## After this gate — you are done improving for the event

- If it passes: product is cheaper + safer, tagged v0.3.0, poster cost number
  can go up.
- If it doesn't: v0.2.2 ships unchanged. Either way, **stop synthetic evals**
  and move to the "ready & functional" checklist in EVENT_READINESS.md.
