#!/usr/bin/env bash
# Read-only guard: first-party PowerShell must stay PS 5.1-safe.
# Fails on: PowerShell-level &&, non-ASCII (except UTF-8 BOM), hardcoded /home/gheno runtime,
# or /mnt/* used as runtime target outside sync SRC comments.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
FAIL=0

mapfile -t FILES < <(
  find launcher installer/windows scripts -maxdepth 2 -type f -name '*.ps1' 2>/dev/null \
    | grep -vE 'vendor/|/node_modules/' \
    | sort -u
)

if ((${#FILES[@]} == 0)); then
  echo "[FAIL] no first-party .ps1 found under launcher/ installer/windows/ scripts/"
  exit 1
fi

echo "=== check-ps1-ps51-safe (${#FILES[@]} files) ==="

for f in "${FILES[@]}"; do
  # Strip UTF-8 BOM for scan
  content="$(python3 - "$f" <<'PY'
import sys
p = sys.argv[1]
raw = open(p, "rb").read()
if raw.startswith(b"\xef\xbb\xbf"):
    raw = raw[3:]
sys.stdout.buffer.write(raw)
PY
)"

  # Non-ASCII bytes in file body
  if printf '%s' "$content" | python3 -c 'import sys; d=sys.stdin.buffer.read(); sys.exit(0 if all(b<128 for b in d) else 1)'; then
    :
  else
    echo "[FAIL] non-ASCII in $f"
    FAIL=$((FAIL + 1))
  fi

  # PowerShell-level && outside comments / bash -lc strings is hard to parse perfectly;
  # flag lines that look like PS statement chaining: ) && or } && or " && or end of cmd &&
  while IFS= read -r line; do
    trimmed="${line#"${line%%[![:space:]]*}"}"
    [[ "$trimmed" == \#* ]] && continue
    if [[ "$trimmed" =~ \)[[:space:]]*\&\& ]] || [[ "$trimmed" =~ \}[[:space:]]*\&\& ]] || [[ "$trimmed" =~ \"[[:space:]]*\&\&[[:space:]]*\$ ]]; then
      echo "[FAIL] PowerShell && chain in $f :: $trimmed"
      FAIL=$((FAIL + 1))
    fi
  done <<< "$content"

  if grep -nE '/home/gheno/citevision-v2' "$f" >/dev/null 2>&1; then
    # Resolver may mention $HOME/citevision-v2; hardcode user path is forbidden.
    echo "[FAIL] hardcoded /home/gheno/citevision-v2 in $f — use Resolve-CiteVisionWslRoot"
    FAIL=$((FAIL + 1))
  fi

  # Runtime under /mnt in start/stop/watchdog/NSSM-ish scripts (allow sync SRC mentions in sync-*.ps1 / bootstrap)
  base="$(basename "$f")"
  case "$base" in
    sync-to-wsl*|sync-demo*|sync-from*|bootstrap.ps1|check-ps1*|Resolve-*)
      ;;
    *)
      if grep -nE 'cd[[:space:]]+[\"'\'']?/mnt/|AppParameters.* /mnt/|WslRoot[[:space:]]*=[[:space:]]*[\"'\'']/mnt/' "$f" >/dev/null 2>&1; then
        echo "[FAIL] /mnt runtime target in $f"
        FAIL=$((FAIL + 1))
      fi
      ;;
  esac
done

if (( FAIL > 0 )); then
  echo "RESULT: FAIL ($FAIL)"
  exit 1
fi
echo "RESULT: OK"
exit 0
