# Ops diagnostics (P.135 / Sprint 4)

Scripts formerly under `scripts/_fix_*` and `scripts/_diag_*`.

## Rules

- **Read-only by default** — inspect API/DB/logs; do not rewrite zones, rules, or camera geometry.
- **No automatic DB writes** — zone/rule corrections go through ZoneEditor / UI or an explicitly human-validated seed.
- Set `ALLOW_DB_WRITE=1` only for a one-shot, human-approved repair script (document why in the run notes).

These tools are **outside** the runtime critical path (A.6).
