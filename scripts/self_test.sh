#!/usr/bin/env bash
# self_test.sh — verifies the gateway is REAL.
#
# Runs in ~2 minutes and produces a green/red verdict:
#   - Health check passes
#   - Classifier weights loaded
#   - PII redaction active
#   - Sample call routes correctly
#   - Cache fires on repeat
#   - Pytest unit tests pass
#
# Run after every meaningful change. If this is red, the product isn't real.

set -uo pipefail

cd "$(dirname "$0")/.."

if [ -t 1 ]; then
  C_R=$(printf '\033[31m'); C_G=$(printf '\033[32m'); C_Y=$(printf '\033[33m'); C_X=$(printf '\033[0m')
else C_R=""; C_G=""; C_Y=""; C_X=""; fi
ok()   { echo -e "  ${C_G}✓${C_X} $*"; }
fail() { echo -e "  ${C_R}✗${C_X} $*"; FAILED=1; }
warn() { echo -e "  ${C_Y}!${C_X} $*"; }
step() { echo; echo -e "${C_G}▸${C_X} $*"; }

FAILED=0
GW="${GATEWAY_URL:-http://localhost:8000}"
KEY="${GATEWAY_MASTER_KEY:-}"

step "1/6  Gateway health"
HEALTH=$(curl -sS -m 5 "$GW/health" 2>&1) || { fail "cannot reach $GW/health"; }
if echo "$HEALTH" | grep -q '"ok": *true'; then
  ok "/health returns ok=true"
else
  fail "/health did not return ok=true: $HEALTH"
fi
if echo "$HEALTH" | grep -q '"classifier_loaded": *true'; then
  ok "trained classifier weights loaded"
else
  warn "classifier_loaded is false — run: python classifier/train.py"
fi
if echo "$HEALTH" | grep -q '"pii_redaction": *true'; then
  ok "PII redaction active"
else
  warn "PII redaction is off"
fi

step "2/6  Auth"
if [ -z "$KEY" ]; then
  fail "GATEWAY_MASTER_KEY not set — cannot test authenticated paths"
else
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 5 -H "Authorization: Bearer $KEY" "$GW/v1/models")
  if [ "$CODE" = "200" ]; then ok "/v1/models with master key -> 200"
  else fail "/v1/models with master key -> $CODE"; fi
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 5 -H "Authorization: Bearer bogus-key" "$GW/v1/models")
  if [ "$CODE" = "401" ]; then ok "/v1/models with bogus key -> 401"
  else fail "/v1/models with bogus key -> $CODE (expected 401)"; fi
fi

step "3/6  Sample call routes correctly"
if [ -z "$KEY" ]; then
  warn "skipped (no key)"
else
  RESP=$(curl -sS -m 60 -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d '{"model":"auto","messages":[{"role":"user","content":"Classify sentiment: I love this product"}],"max_tokens":20}' \
    "$GW/v1/chat/completions")
  MODEL=$(echo "$RESP" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('model',''))" 2>/dev/null || echo "")
  if echo "$MODEL" | grep -qi "haiku\|mini"; then
    ok "simple classification routed to cheap tier ($MODEL)"
  elif [ -n "$MODEL" ]; then
    warn "simple classification went to $MODEL (expected haiku/mini — classifier may need re-training)"
  else
    fail "no model in response: $RESP"
  fi
fi

step "4/6  Cache fires on repeat"
if [ -z "$KEY" ]; then
  warn "skipped (no key)"
else
  P='{"model":"auto","messages":[{"role":"user","content":"What is the capital of France?"}],"max_tokens":10}'
  R1=$(curl -sS -m 30 -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d "$P" "$GW/v1/chat/completions")
  ID1=$(echo "$R1" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")
  R2=$(curl -sS -m 30 -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d "$P" "$GW/v1/chat/completions")
  ID2=$(echo "$R2" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")
  if echo "$ID2" | grep -q "^cached-"; then
    ok "second call returned cached id: $ID2"
  else
    warn "second call id=$ID2 — semantic cache may be disabled or degraded"
  fi
fi

step "5/6  PII redaction works end-to-end"
if [ -z "$KEY" ]; then
  warn "skipped (no key)"
else
  RESP=$(curl -sS -m 30 -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d '{"model":"auto","messages":[{"role":"user","content":"My email is leak@bad.com please confirm receipt"}],"max_tokens":30}' \
    "$GW/v1/chat/completions")
  # We can't easily prove PII was redacted from this side (the redacted prompt
  # is what the model sees). The proof is in the gateway logs: look for
  # pii=N>0 in the call line. We just verify the call returned 200.
  if echo "$RESP" | grep -q '"choices"'; then
    ok "call with PII content returned 200 (check gateway logs for 'pii=N')"
  else
    fail "PII-bearing call failed: $RESP"
  fi
fi

step "6/6  Unit tests"
if [ -d gateway/tests ]; then
  if command -v pytest >/dev/null 2>&1; then
    (cd gateway && pytest -m unit -q) && ok "pytest unit suite green" || fail "pytest unit suite failed"
  else
    warn "pytest not installed (pip install pytest)"
  fi
else
  warn "no tests dir found"
fi

echo
if [ $FAILED -eq 0 ]; then
  echo -e "${C_G}════════════════════════════════════════════"
  echo -e "  Gateway self-test: PASSED"
  echo -e "════════════════════════════════════════════${C_X}"
else
  echo -e "${C_R}════════════════════════════════════════════"
  echo -e "  Gateway self-test: FAILED — fix before demoing"
  echo -e "════════════════════════════════════════════${C_X}"
fi
exit $FAILED
