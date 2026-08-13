# Contrat webhook intégrateurs

Les alertes routées par e-mail ou webhook partagent le même enrichissement métier (`evidence_snapshot`, `plate_number`, `face_label`, etc.).  
Configuration UI : **Paramètres → Routage alertes** (presets n8n / Make / Zapier / chat).  
Échantillon JSON exact : `GET /api/v1/orgs/{org}/integrations/webhook/sample?preset=n8n&kind=routing`.

## Deux phases de livraison (routing)

Le routage auto envoie **deux webhooks HTTP distincts** (même URL / même règles de matching) :

| `webhook_phase` | Quand | Contenu typique |
|-----------------|--------|-----------------|
| `create` | À la création de l’alerte | Métadonnées alerte ; `evidence_status` souvent `pending` ; snapshot incomplet |
| `evidence_complete` | Premier passage de l’evidence à `complete` | Snapshot enrichi avec URLs clip/images ; `evidence_status=complete` |

- **E-mail SMTP** : uniquement à la phase `create` (pas de double mail).
- **Forward manuel** (UI alerte) : `webhook_phase=manual_forward`.
- Un 200 HTTP sur `create` **sans** clip n’est **pas** un DoD preuves : pour un workflow n8n « preuves prêtes », filtrez sur `webhook_phase=evidence_complete` (ou `evidence_status=complete`).

Les preuves voyagent **en URL** dans `evidence_snapshot` (pas en binaire dans le POST). Le workflow doit ensuite `GET` ces URL avec auth API / session selon votre déploiement.

## Enveloppe CloudEvents (défaut activé)

`WEBHOOK_CLOUDEVENTS=0` désactive l'enveloppe. Presets chat (Slack / Teams / Discord) utilisent leur propre forme de corps (pas CloudEvents).

```json
{
  "specversion": "1.0",
  "type": "com.citevision.alert.v1",
  "source": "/orgs/{org_id}/citevision",
  "id": "{alert_id}",
  "time": "2026-08-13T12:00:00Z",
  "datacontenttype": "application/json",
  "data": {
    "org_id": "...",
    "alert_id": "...",
    "title": "...",
    "severity": "high",
    "status": "open",
    "event_type": "zone_presence",
    "webhook_phase": "evidence_complete",
    "evidence_status": "complete",
    "alert_correlation_id": "corr-...",
    "created_at": "2026-08-13T11:59:50Z",
    "updated_at": "2026-08-13T12:00:00Z",
    "plate_number": "",
    "face_label": "",
    "camera_id": "...",
    "rule_name": "...",
    "routing_rule": "...",
    "integration_preset": "n8n",
    "evidence_snapshot": {
      "evidence_status": "complete",
      "package": {
        "images": [{ "role": "scene", "url": "https://.../evidence/asset?key=..." }],
        "clip": { "url": "https://.../evidence/asset?key=...", "duration_sec": 6 }
      }
    }
  }
}
```

Champs utiles pour n8n / Make / Zapier : `webhook_phase`, `evidence_status`, `alert_correlation_id`, `status`, horodatages, `evidence_snapshot`.

## Action règle `webhook` (rules-engine)

Distinct du routage auto : action de règle → `POST` interne `InternalWebhook` → même chemin durci (SSRF, retries, DLQ, HMAC optionnel).  
Le `integration_preset` / `preset` de la config d’action est honoré (`PostWebhookPreset`).  
Échec HTTP (4xx/5xx après retries) → l’action est **non exécutée** (pas de faux succès).

## Idempotence livraison

En-tête `X-CiteVision-Delivery-Id` : UUID stable par tentative de livraison (réutilisé sur les retries).  
Chaque phase (`create` / `evidence_complete` / `manual_forward`) est une livraison distincte.

## Signature (optionnel)

Si `WEBHOOK_SIGNING_SECRET` est défini : en-tête `X-CiteVision-Signature: sha256=<hmac>`.  
L’UI Paramètres → Routage indique si la signature est active.

## Retries

- `WEBHOOK_MAX_ATTEMPTS` (défaut 3)
- Backoff linéaire 500 ms × numéro de tentative
- Échec final → ligne JSON dans `logs/routing-dlq.jsonl` (`WEBHOOK_DLQ_PATH`)
- SSRF : hôtes privés bloqués sauf `WEBHOOK_ALLOW_PRIVATE=1` (lab / n8n local)

## Presets UX

n8n, Make, Zapier : champ `integration_preset` dans `data` si configuré sur la règle de routage.  
Tester sans sauver : `POST .../integrations/webhook/test` (payload de test, `test: true`).

## Tests

```bash
bash scripts/verify-e2e-webhook-cloudevents.sh
bash scripts/verify-routing-rules.sh
```
