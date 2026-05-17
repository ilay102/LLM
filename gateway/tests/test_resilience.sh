#!/usr/bin/env bash
# Manual resilience test: verifies the gateway never 5xx when Redis is down.
#
# Prerequisites: docker compose up --build -d is already running.
# Run from the gateway/ directory:  bash tests/test_resilience.sh

set -euo pipefail

BASE_URL="http://localhost:8000/v1"
KEY="${GATEWAY_MASTER_KEY:-dev-key-change-me}"
PROMPT="Classify this sentence as positive or negative: 'The food was awful.'"

pass() { echo "  [PASS] $*"; }
fail() { echo "  [FAIL] $*"; exit 1; }

call_gateway() {
    curl -s -o /tmp/gw_resp.json -w "%{http_code}" \
        -X POST "$BASE_URL/chat/completions" \
        -H "Authorization: Bearer $KEY" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"auto\",\"messages\":[{\"role\":\"user\",\"content\":\"$PROMPT\"}],\"max_tokens\":50}"
}

echo ""
echo "=== Phase 1: baseline — warm the cache ==="

echo "Call 1 (cold — expect live model response):"
STATUS=$(call_gateway)
[ "$STATUS" = "200" ] || fail "Expected 200, got $STATUS"
ID=$(python3 -c "import json,sys; print(json.load(open('/tmp/gw_resp.json')).get('id',''))")
echo "  HTTP $STATUS  id=$ID"
[[ "$ID" == cached-* ]] && fail "Expected a live response on first call, got cached"
pass "Live response returned"

echo "Call 2 (warm — expect cache hit):"
STATUS=$(call_gateway)
[ "$STATUS" = "200" ] || fail "Expected 200, got $STATUS"
ID=$(python3 -c "import json,sys; print(json.load(open('/tmp/gw_resp.json')).get('id',''))")
echo "  HTTP $STATUS  id=$ID"
[[ "$ID" == cached-* ]] || fail "Expected cached-* id, got: $ID"
pass "Cache hit confirmed (id=$ID)"

echo ""
echo "=== Phase 2: kill Redis — all calls must still return 200 ==="

docker compose stop redis
echo "Redis stopped."

for i in $(seq 3 7); do
    echo "Call $i (Redis down — expect 200 no cache):"
    STATUS=$(call_gateway)
    [ "$STATUS" = "200" ] || fail "Expected 200, got $STATUS (gateway returned 5xx with Redis down!)"
    ID=$(python3 -c "import json,sys; print(json.load(open('/tmp/gw_resp.json')).get('id',''))")
    echo "  HTTP $STATUS  id=$ID"
    [[ "$ID" == cached-* ]] && fail "Got a cache hit while Redis is stopped — impossible"
    pass "Live response (no cache)"
done

echo ""
echo "=== Phase 3: restore Redis — cache recovers within 35s ==="

docker compose start redis
echo "Redis restarted. Waiting 35s for probe loop to reconnect..."
sleep 35

echo "Call 8 (cold after recovery — expect live model):"
STATUS=$(call_gateway)
[ "$STATUS" = "200" ] || fail "Expected 200, got $STATUS"
ID=$(python3 -c "import json,sys; print(json.load(open('/tmp/gw_resp.json')).get('id',''))")
echo "  HTTP $STATUS  id=$ID"
pass "Post-recovery live call OK"

echo "Call 9 (warm after recovery — expect cache hit again):"
STATUS=$(call_gateway)
[ "$STATUS" = "200" ] || fail "Expected 200, got $STATUS"
ID=$(python3 -c "import json,sys; print(json.load(open('/tmp/gw_resp.json')).get('id',''))")
echo "  HTTP $STATUS  id=$ID"
[[ "$ID" == cached-* ]] || fail "Expected cache hit after recovery, got: $ID"
pass "Cache restored after reconnect (id=$ID)"

echo ""
echo "=== All checks passed. Gateway is fail-open. ==="
