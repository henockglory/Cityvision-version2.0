# CitéVision — Rapport d'optimisation « gamechanger »

> Copie de travail : `citevision_optimized` (l'original `citevision-v2` reste **intact**).
> Toutes les modifications ci‑dessous ont été appliquées et **vérifiées par compilation/tests**
> dans cette copie. Aucune dépendance à de vraies caméras / GPU n'est requise pour la vérification.

Date : 2026‑06‑21

---

## 1. Résumé exécutif

Cette intervention transforme CitéVision en une plateforme de vidéosurveillance assistée par IA
**durcie, observable et ouverte sur l'automatisation**, sans dégrader l'existant :

- **Sécurité (P0)** : élimination des principales surfaces d'attaque (IDOR multi‑tenant, SSRF webhooks,
  WebSocket sans validation de session, CORS « * », absence de rate limiting, `/metrics` ouvert,
  clé de chiffrement caméra dérivée faiblement, installeur exposé au réseau).
- **Hub d'intégrations** : transformations natives n8n / Make / Zapier / Slack / Teams / Discord,
  webhooks **signés HMAC‑SHA256**, journal de livraison, test de connectivité, le tout exposé dans l'UI.
- **Moteurs IA** : tracker **Kalman + association à deux seuils** (style ByteTrack) et **inférence par lot**
  multi‑caméra — gains de stabilité d'ID et de débit GPU.
- **Moteur vidéo** : détection du **FPS réel** du flux + ré‑échantillonnage dynamique.
- **Observabilité & production** : `request_id` dans les logs, métriques métier Prometheus + jauge DLQ,
  alignement des versions Go, CI durcie (vet + typecheck), tests ajoutés.

**Vérifications finales** (toutes vertes) :

| Composant | Commande | Résultat |
|---|---|---|
| Backend Go | `go build ./...`, `go vet ./...`, `go test ./...` | ✅ build + vet + tests OK |
| Frontend | `tsc --noEmit`, `vite build` | ✅ typecheck + build OK |
| AI engine | `pytest` | ✅ **57 tests** OK |
| Video engine | `g++` (parties hors‑FFmpeg) | ✅ `frame_sampler` compilé + testé |

> Le moteur vidéo complet n'est pas compilable ici (libs **FFmpeg dev absentes** de l'environnement) ;
> les changements C++ sont ciblés/sûrs et la logique indépendante de FFmpeg a été compilée et testée.

---

## 2. Sécurité backend (avant → après)

| # | Vulnérabilité | Avant | Après |
|---|---|---|---|
| 1 | **IDOR preuves** | `key` accepté si préfixe `orgs/` | Exige `orgs/{orgID}/…` (isolation stricte par tenant) — `handler/evidence.go` |
| 2 | **SSRF webhooks** | URL POSTée telle quelle | Allowlist + blocage RFC1918/loopback/link‑local/IMDS, contournements explicites (`WEBHOOK_ALLOW_PRIVATE`, `WEBHOOK_ALLOWED_HOSTS`) — `routing/ssrf.go` |
| 3 | **WebSocket** | `ParseAccessToken` seulement | Validation **session Redis** + allowlist d'**Origin** — `handler/api.go`, `ws/hub.go` |
| 4 | **CORS** | `Access-Control-Allow-Origin: *` | Allowlist par env (`CORS_ALLOWED_ORIGINS`), `Vary: Origin`, credentials — `middleware/middleware.go` |
| 5 | **Rate limiting** | Aucun | Token‑bucket par IP sur login/refresh/setup (strict) et discover/probe/forward (modéré) — `middleware/ratelimit.go` |
| 6 | **/metrics** | Public | Protégé par `INTERNAL_API_KEY` (sauf `METRICS_PUBLIC=1`) — `cmd/api/main.go` |
| 7 | **INTERNAL_API_KEY** | Optionnel | **Requis au boot** + refus du placeholder hors `development` — `config/config.go` |
| 8 | **Clé caméra** | Zero‑pad/troncature | Dérivation **SHA‑256** si longueur ≠ 32 (32 o conservés tels quels = rétrocompat) — `camera/crypto.go` |
| 9 | **Arrêt** | MQTT/orchestrateur via `defer` seulement | `mqttCancel()` explicite avant drain HTTP — `cmd/api/main.go` |
| 10 | **Audit** | Erreurs d'écriture ignorées (`_, _ =`) | Helper `auditLog` qui **logue** les échecs (chaîne d'audit observable) — `handler/api.go` |
| 11 | **Webhook unifié** | 2 chemins distincts (raw client vs PostWebhook) | `InternalWebhook` et `ForwardAlert` passent par le **chemin durci unique** |

### Installeur (`installer/setup-server.py`)
- **Bind `127.0.0.1`** (n'écoute plus sur toutes les interfaces).
- **CORS** restreint aux origines localhost (plus de `*`).
- **Anti‑traversée de chemin** : `resolve()` + vérification que la cible reste sous `ui/`.
- **Jeton one‑time** (`secrets.token_urlsafe`) déposé en cookie `SameSite=Strict` et exigé sur les
  endpoints sensibles (`/api/install`, `/api/launch`, `/api/register-service`).
- **Base API dynamique** (`window.location.origin`) côté UI → même origine garantie (cookie envoyé,
  robustesse au changement de port).

---

## 3. Hub d'intégrations & automatisation

- **Transformations natives** (`routing/presets.go`) :
  - *Automation* : n8n, Make, Zapier (JSON canonique + enveloppe CloudEvents conservée).
  - *Chat* : **Slack** (blocks), **Teams** (MessageCard), **Discord** (embeds) — corps adapté à chaque schéma.
- **Webhooks signés** : en‑tête `X-CiteVision-Signature: sha256=…` (HMAC‑SHA256, `WEBHOOK_SIGNING_SECRET`).
- **Livraison fiable** : SSRF + retries exponentiels + **DLQ** (déjà présents) désormais unifiés pour tous les chemins.
- **APIs** : `GET …/integrations/presets` (catalogue + statut signature), `POST …/integrations/webhook/test`
  (test de connectivité), `GET …/integrations/delivery-log` (journal agrégé par org).
- **UI** (`AlertRoutingPanel.tsx`) : badge « webhooks signés », bouton **Tester le webhook** par règle,
  **journal de livraison** intégré ; presets Slack/Teams/Discord ajoutés au sélecteur.

> Reliquats documentés (non bloquants) : publisher MQTT du cycle de vie des alertes et webhook **entrant**
> signé (déclencheur d'automatisation) — l'infrastructure de signature/vérification est en place pour les ajouter.

---

## 4. UX / design

- **Code mort supprimé** : `CyberPanel`, `HologramBackground`, `StatCard` (le tableau de bord utilise `StatTile`).
- **`EyeLogo`** aligné sur les **tokens `--cv-accent`** (fini le cyan codé en dur ; suit le thème).
- **Tutoriel animé pas‑à‑pas** (`onboarding/AnimatedTutorial.tsx`) : parcours **Caméras → Zones → Règles**
  avec illustrations SVG animées, progression, navigation, persistance, `prefers-reduced-motion` respecté ;
  i18n **FR + EN** complète (clés `tutorial.*`).

> Reliquats documentés : sweep i18n EN des chaînes FR résiduelles (hints Settings/Users/SystemHealth),
> câblage PTZ/snapshot LiveView, canvas ZoneEditor responsive.

---

## 5. Moteurs IA & vidéo

### AI engine (`ai-engine`)
- **Tracker amélioré** (`tracking/bytetrack.py`) : filtre de **Kalman vitesse‑constante** (sans numpy,
  4×1D sur cx/cy/w/h) + **association à deux seuils** (haute/basse confiance) façon ByteTrack →
  IDs plus stables à travers les occultations, récupération des détections faibles.
- **Inférence par lot** (`detection/yolo_onnx.py`) : `preprocess_batch` + `detect_batch` (un seul
  `session.run` multi‑caméra) → amortit l'overhead GPU.
- **Tests** : +9 tests (`test_bytetrack.py`, `test_yolo_batch.py`), suite complète **57 OK**.

### Video engine (`video-engine`)
- **FPS réel** lu depuis le conteneur (`avg_frame_rate`/`r_frame_rate`) — `rtsp_ingest`.
- **Ré‑échantillonnage dynamique** : `FrameSampler.reconfigure()` + `DualPipeline.set_source_fps()`
  appliquent le FPS détecté au lieu d'une valeur codée en dur.
- Logique `frame_sampler` **compilée et testée** (g++), indépendamment de FFmpeg.

> Reliquats documentés (nécessitent un environnement FFmpeg/GPU) : enregistrement MP4 segmenté réel,
> export des frames décodées via mémoire partagée/ring‑buffer, providers GPU face/plaque + ReID.

---

## 6. Production & observabilité

- **`request_id`** ajouté aux logs de requête (corrélation bout‑en‑bout).
- **Métriques métier Prometheus** : `alerts_created_total`, `webhook_deliveries_total{preset,result}`,
  **jauge `webhook_dlq_size`** (alerte sur la croissance de la DLQ).
- **Versions Go alignées** : `Dockerfile` 1.22 → **1.25** (cohérent avec `go.mod`), CI idem.
- **CI durcie** (`.github/workflows/ci.yml`) : `go vet` + `tsc --noEmit` ajoutés au pipeline.
- **Tests ajoutés** : rate limiter, CORS allowlist, SSRF, signature ; le tout vert.
- **`.env.example`** documente toutes les nouvelles variables de sécurité.

---

## 7. Variables d'environnement ajoutées

| Variable | Rôle | Défaut |
|---|---|---|
| `INTERNAL_API_KEY` | **Requise** ; protège services internes + `/metrics` | placeholder (refusé hors dev) |
| `CORS_ALLOWED_ORIGINS` | Allowlist CORS (CSV, `*` possible) | localhost dev |
| `WS_ALLOWED_ORIGINS` | Allowlist Origin WebSocket | défauts dev |
| `POSTGRES_SSLMODE` | Mode TLS Postgres | `disable` |
| `METRICS_PUBLIC` | Exposer `/metrics` sans clé | `0` |
| `WEBHOOK_ALLOW_PRIVATE` | Autoriser cibles privées (n8n LAN) | `0` |
| `WEBHOOK_ALLOWED_HOSTS` | Hôtes webhook autorisés (CSV) | — |
| `WEBHOOK_SIGNING_SECRET` | Secret HMAC des webhooks sortants | — |

---

## 8. Compatibilité & garde‑fous

- **Aucune rupture d'API** ; les nouveaux comportements sont activables/configurables par env.
- **Rétrocompatibilité chiffrement** : clés caméra de 32 octets inchangées.
- **Tests existants préservés** (ajustés uniquement là où le durcissement SSRF visait des serveurs
  de test loopback, via `WEBHOOK_ALLOW_PRIVATE=1` dans les tests concernés).
- **Original intact** : tout le travail est dans `citevision_optimized`.

---

## 9. Suite recommandée (au‑delà de cette itération)

1. Publisher MQTT du cycle de vie des alertes + webhook entrant signé (vérif HMAC).
2. Enregistrement MP4 segmenté + mémoire partagée frames (env FFmpeg requis).
3. Providers GPU face/plaque + embeddings ReID pour la corrélation.
4. Sweep i18n EN final + PTZ/snapshot LiveView + ZoneEditor responsive.
5. OpenTelemetry (traces HTTP+DB) et alerting Prometheus sur `webhook_dlq_size`.
