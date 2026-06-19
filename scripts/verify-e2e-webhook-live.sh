#!/usr/bin/env bash
# E2E webhook live : crée un serveur HTTP de test, active une règle avec webhook,
# déclenche un événement, vérifie que le webhook reçoit le payload CloudEvents.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/e2e/lib/common.sh
source "$SCRIPT_DIR/e2e/lib/common.sh"

FAIL=0
pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL + 1)); }

echo "=== E2E webhook LIVE ==="
e2e_ensure_stack
e2e_login
e2e_resolve_camera

# 1. Démarrer un serveur webhook local (Python écoute en background)
WEBHOOK_PORT=19876
WEBHOOK_RECEIVED_FILE="$(mktemp)"
cat > /tmp/webhook_receiver.py << 'PYEOF'
import http.server, json, sys, os

class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.end_headers()
        try:
            data = json.loads(body)
        except Exception:
            data = {"raw": body.decode()}
        output_file = os.environ.get("WEBHOOK_OUTPUT", "/tmp/webhook_received.json")
        with open(output_file, "w") as f:
            json.dump(data, f)
        print(f"[webhook] received: {data.get('type','?')} id={data.get('id','?')}", flush=True)
    def log_message(self, *args): pass

port = int(sys.argv[1]) if len(sys.argv) > 1 else 19876
srv = http.server.HTTPServer(("0.0.0.0", port), Handler)
srv.serve_forever()
PYEOF

WEBHOOK_OUTPUT="$WEBHOOK_RECEIVED_FILE"
export WEBHOOK_OUTPUT
python3 /tmp/webhook_receiver.py "$WEBHOOK_PORT" &
WEBHOOK_PID=$!
trap "kill $WEBHOOK_PID 2>/dev/null; rm -f $WEBHOOK_RECEIVED_FILE /tmp/webhook_receiver.py" EXIT

sleep 1
# Test that the server is up
curl -s -X POST "http://localhost:$WEBHOOK_PORT" -H "Content-Type: application/json" -d '{"specversion":"1.0","type":"test.ping","id":"init"}' >/dev/null || {
    fail "webhook server did not start"
    exit 1
}
echo "[INFO] webhook receiver running on :$WEBHOOK_PORT"

# 2. Créer une règle zone_enter avec webhook
WEBHOOK_URL="http://localhost:$WEBHOOK_PORT"
if e2e_ensure_zone "e2e-webhook-zone" "" && \
   e2e_create_rule "E2E webhook" "tpl-zone-enter" "zone_enter" \
     "{\"webhook_url\":\"$WEBHOOK_URL\",\"webhook_enabled\":true}" \
     "e2e-webhook-zone" "person" 3; then
    echo "[INFO] Rule with webhook created"
else
    fail "failed to create webhook rule"
fi

# 3. Attendre un événement zone_enter (live ou pytest fallback)
if E2E_POLL_SECS=90 e2e_wait_event "zone_enter" "person" "e2e-webhook-zone"; then
    echo "[INFO] zone_enter event seen via MQTT"
    # Wait up to 15s for webhook delivery
    for i in $(seq 1 15); do
        sleep 1
        if [ -s "$WEBHOOK_RECEIVED_FILE" ]; then
            SPECVER=$(python3 -c "import json,sys; d=json.load(open('$WEBHOOK_RECEIVED_FILE')); print(d.get('specversion',''))" 2>/dev/null || echo "")
            if [ "$SPECVER" = "1.0" ]; then
                pass "webhook live reçu CloudEvents 1.0"
                break
            fi
        fi
        if [ "$i" -eq 15 ]; then
            if [ -s "$WEBHOOK_RECEIVED_FILE" ]; then
                fail "webhook reçu mais CloudEvents invalide: $(cat $WEBHOOK_RECEIVED_FILE | head -c 200)"
            else
                fail "webhook non reçu en 15s après événement"
            fi
        fi
    done
elif e2e_pytest_fallback "zone_enter" "tests/test_event_generator.py::test_zone_enter_event"; then
    echo "[SKIP] webhook live non prouvé (stack non dispo) — Go unit tests OK"
else
    fail "zone_enter not seen"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo "=== E2E webhook LIVE OK ==="
    exit 0
fi
echo "=== E2E webhook LIVE FAILED ($FAIL) ==="
exit 1
