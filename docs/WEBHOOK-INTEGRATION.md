# Contrat webhook intégrateurs (Phase E)

Les alertes routées par e-mail ou webhook utilisent le même enrichissement (`evidence_snapshot`, `plate_number`, `face_label`).

## Enveloppe CloudEvents (défaut activé)

`WEBHOOK_CLOUDEVENTS=0` désactive l'enveloppe.

```json
{
  "specversion": "1.0",
  "type": "com.citevision.alert.v1",
  "source": "/orgs/{org_id}/citevision",
  "id": "{alert_id}",
  "time": "2026-06-16T12:00:00Z",
  "datacontenttype": "application/json",
  "data": {
    "org_id": "...",
    "alert_id": "...",
    "title": "...",
    "severity": "high",
    "event_type": "zone_presence",
    "plate_number": "",
    "face_label": "",
    "evidence_snapshot": {},
    "routing_rule": "..."
  }
}
```

## Idempotence livraison

En-tête `X-CiteVision-Delivery-Id` : UUID stable par tentative de livraison (réutilisé sur les retries).

## Retries

- `WEBHOOK_MAX_ATTEMPTS` (défaut 3)
- Backoff linéaire 500 ms × numéro de tentative
- Échec final → ligne JSON dans `logs/routing-dlq.jsonl` (`WEBHOOK_DLQ_PATH`)

## Presets UX

n8n, Make, Zapier : champ `integration_preset` dans `data` si configuré sur la règle de routage.

## Tests

```bash
bash scripts/verify-e2e-webhook-cloudevents.sh
bash scripts/verify-routing-rules.sh
```
