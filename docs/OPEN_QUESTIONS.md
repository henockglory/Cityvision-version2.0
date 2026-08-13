# Open Questions

1. **Backend language** — Go (v1 parity) vs split microservices?
2. **Auth provider** — Self-hosted JWT vs OIDC (Keycloak)?
3. **Multi-tenancy model** — Row-level org_id vs schema-per-tenant?
4. **Recording retention** — MinIO lifecycle policy defaults?
5. **ONVIF discovery** — Phase 2 or Phase 3?
6. **go2rtc deployment** — Sidecar vs embedded in video-engine?
7. **Face watchlist storage** — Postgres pgvector vs dedicated vector DB?
8. ~~**Alert delivery** — MQTT only vs webhook + email?~~ **Résolu** — MQTT = bus événements/alertes internes ; livraison externe = routage SMTP (create-only) + webhook dual-phase (`create` / `evidence_complete`) + action règle webhook. Voir [WEBHOOK-INTEGRATION.md](WEBHOOK-INTEGRATION.md).
9. **Rule authoring UI** — Visual flow builder vs JSON editor?
10. **Camera credential encryption** — AES key rotation strategy?

See [CLARIFICATIONS.md](CLARIFICATIONS.md) for defaults applied until decided.
