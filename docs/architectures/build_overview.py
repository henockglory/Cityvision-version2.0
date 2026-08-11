#!/usr/bin/env python3
"""Generate docs/architectures/overview.html — product overview (tech, rules, comparison, credits)."""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RULES = json.loads((ROOT / "_rules.json").read_text(encoding="utf-8"))

TECH = [
    ("Go (Golang)", "Langage", "Gin/Chi routers, sqlc/pgx, MQTT clients, goroutines", "backend/", "API REST, orchestration règles, persistance alertes, bridge Frigate, jobs preuve", "Concurrence native, binaires uniques, perf réseau pour flux temps réel"),
    ("TypeScript", "Langage", "strict TS, Zod-like validation patterns", "frontend/src", "Typage fort UI métier (zones, règles, alertes)", "Moins d'erreurs runtime côté console opérateur"),
    ("JavaScript (ESM)", "Langage", "Vite bundling", "frontend tooling", "Build & modules front", "Écosystème Vite/React mature"),
    ("Python 3", "Langage", "FastAPI/uvicorn, asyncio, pytest", "ai-engine/", "Inférence IA, composition preuves, OCR/VLM, health GPU", "Écosystème ML (ONNX, OpenCV, Gemini SDK)"),
    ("SQL (PostgreSQL dialect)", "Langage / data", "migrations versionnées, JSONB", "backend/migrations, queries", "Schéma zones/rules/alerts/evidence", "Source de vérité relationnelle + flexibilité JSONB"),
    ("Bash / PowerShell", "Ops", "WSL scripts, Start-CiteVision.ps1", "scripts/, launcher/", "Bring-up stack, health, validate_rule, sync miroirs", "Runtime unique WSL + UX Windows propre"),
    ("React 18", "Frontend", "Vite, React Router, hooks modernes", "frontend/", "Console opérateur, ZoneEditor, alertes, catalogue", "Composants riches pour cartographie zones + preuves"),
    ("Vite", "Frontend tooling", "HMR, env inject", "frontend/", "Dev server :5174 et build prod", "Itération UI rapide pendant validation démo"),
    ("HTML / CSS", "UI docs", "Fraunces + Manrope, CSS variables", "docs/architectures/", "Documentation premium offline-friendly", "Présentation métier sans stack front lourde"),
    ("Mermaid", "Diagrammes", "CDN mermaid@11", "docs/architectures/index.html", "Schémas architecture interactifs", "Lisibilité ops/produit sans outil propriétaire"),
    ("YOLOv8 / Ultralytics", "IA vision", "ONNX Runtime CUDA", "ai-engine detectors", "Détection personnes/véhicules/objets", "État de l'art détection temps réel + export ONNX GPU"),
    ("ONNX Runtime", "IA runtime", "CUDA EP, CPU fallback", "ai-engine inference", "Exécution modèles optimisés", "Portabilité GPU/CPU + perf mesurable via /health"),
    ("CUDA / NVIDIA", "IA accélération", "drivers WSL, TensorRT-ready path", "hôte GPU + containers", "Inférence accélérée (priorité GPU)", "Latence démo & débit multi-caméras"),
    ("OpenCV", "IA vision", "cv2 crops, blur/darkness metrics", "ai-engine evidence/quality", "Pré-traitement images, qualité flux", "Standard industrie vision"),
    ("InsightFace / ArcFace", "IA identité", "embeddings visage", "pipeline face", "Reconnaissance / watchlist", "Embeddings robustes pour matching liste"),
    ("Frigate Face / Face API", "IA identité", "crops Frigate + fusion", "bridge Frigate → AI", "Candidats visage depuis NVR", "Réutilise crops déjà produits par le NVR"),
    ("PaddleOCR / OCR plaque", "IA OCR", "pipeline plaque + validation", "ai-engine plate/", "Lecture plaques routières", "Bon rapport précision/perf pour LPR terrain"),
    ("Google Gemini (VLM)", "IA multimodale", "Gemini Flash/Lite API", "cabin rules (ceinture, téléphone)", "Analyse habitacle quand CV classique est fragile", "Raisonnement scène cabine + refus honnête (no violation)"),
    ("Frigate NVR", "Vidéo / NVR", "MQTT events, go2rtc, zones Frigate", "infra/frigate-config", "Ingest RTSP, tracking, clips, events", "NVR open-source GPU-aware, MQTT natif"),
    ("go2rtc", "Vidéo streaming", "RTSP/WebRTC restream", "avec Frigate", "Restream caméras démo/live", "Faible latence multi-clients"),
    ("FFmpeg", "Vidéo", "transcode, subclip 6s", "backend demo + evidence", "Clips preuve, préparation flux", "Standard encodage/découpe"),
    ("MQTT (Eclipse Mosquitto)", "Messaging", "topics Frigate/events", "infra + bridge", "Bus événements détection → règles", "Découplage NVR / AI / rules"),
    ("PostgreSQL", "Base de données", "JSONB, indexes, migrations", "stack Docker/WSL", "Org, caméras, zones, rules, alerts, users", "ACID + JSONB pour payloads preuve"),
    ("Redis", "Cache / files", "queues légères / locks (si activé)", "infra", "Coordination jobs courts", "Faible latence pour état éphémère"),
    ("MinIO", "Object storage S3", "buckets evidence clips/images", "infra MinIO", "Stockage preuves (clip, scene, subject, plate)", "S3-compatible local, coût maîtrisé, pas de lock-in cloud"),
    ("Docker / dockerd WSL", "Runtime containers", "compose stacks Frigate/MinIO/PG", "WSL natif (pas Docker Desktop)", "Services infra isolés", "Reproductibilité + GPU pass-through WSL"),
    ("Linux (WSL2 Ubuntu)", "OS runtime", "systemd/user services scripts", "~/citevision-v2", "Runtime de vérité unique", "Un filesystem, une vérité ops (R.1)"),
    ("Windows 11 + PowerShell", "OS client", "Start-CiteVision.ps1 launcher", "launcher/", "Point d'entrée opérateur Windows", "UX locale sans exposer chemins lab"),
    ("REST / JSON APIs", "Intégration", "OpenAPI-ish handlers Go", "backend HTTP", "Contrat UI ↔ moteur", "Interop simple, debugable"),
    ("WebSocket / SSE (UI live)", "Intégration", "feeds alertes/status", "frontend ↔ backend", "Mise à jour console quasi temps réel", "Opérateur voit la chaîne sans refresh"),
    ("Mail (SMTP / Mailhog démo)", "Notification", "templates mail premium", "alerting path", "Alerte e-mail avec preuves", "Boucle validation A.3 (Mailhog en lab)"),
    ("Git / GitHub", "Qualité", "origin + v2 remotes", "repos Cityvision-*", "Versioning dual-mirror", "Continuité produit + archive v2"),
    ("pytest / Go test", "Qualité", "unit + integration evidence", "ai-engine/tests, backend/*_test.go", "Non-régression binders/OCR/transcode", "Preuves de comportement avant smoke"),
    ("validate_rule.sh / health_check", "Qualité ops", "DoD 1–6 + artefacts UI", "scripts/", "Validation infalsifiable par règle", "PASS = artefact, pas claim verbal"),
]

# archetype -> base use-case seeds (7 each), specialized by keyword overrides
ARCH_CASES: dict[str, list[str]] = {
    "face": [
        "Contrôle d'accès bâtiment administratif — visage vs liste autorisée à l'entrée principale.",
        "Alerte watchlist aéroport / gare — correspondance sur flux caméra hall.",
        "Sécurité événement sportif — détection personne signalée près des tribunes.",
        "Site industriel — badge + visage pour zone haute sécurité.",
        "Banque / agence — visage inconnu en dehors des horaires d'ouverture.",
        "Hôpital — corrélation identité soignant / zone restreinte pharmacie.",
        "Enquête post-incident — timeline des détections visage autour d'un créneau critique.",
    ],
    "cabin": [
        "Contrôle routier urbain — téléphone au volant en approche carrefour.",
        "Corridor scolaire — ceinture non bouclée aux abords d'une école.",
        "Flotte entreprise — audit conformité conducteurs sur axe périurbain.",
        "Péage / barrière — vérification cabine avant ouverture file rapide.",
        "Police municipale — dossier preuve (clip + crop) pour contravention.",
        "Campagne sensibilisation — statistiques anonymisées violations cabine.",
        "Zone travaux — conduite à risque (téléphone) près d'ouvriers.",
    ],
    "measure": [
        "Avenue 50 km/h — excès mesuré entre deux lignes de référence.",
        "Zone 30 résidentielle — alerte vitesse + plaque pour médiation.",
        "Approche carrefour — arrêt brusque suspect (risque collision).",
        "Voie bus — véhicule trop lent créant un bouchon artificiel.",
        "Périphérique urbain — dépassement seuil dynamique heure de pointe.",
        "Parking souterrain — vitesse anormale dans rampe étroite.",
        "Chantier temporaire — non-respect limitation provisoire signalée.",
    ],
    "dual_signal": [
        "Carrefour à feux — franchissement au rouge avec plaque + clip 6 s.",
        "Passage piéton protégé — véhicule qui grille le rouge face aux écoliers.",
        "Boulevard à plusieurs files — file de droite qui anticipe le vert.",
        "Priorité pompiers — audit a posteriori des franchissements dangereux.",
        "Smart corridor — corrélation feu rouge + vitesse dans la même scène.",
        "Litige assurance — package preuve horodaté pour sinistre carrefour.",
        "Campagne sécurité — heatmaps des carrefours les plus transgressés.",
    ],
    "geometry": [
        "Périmètre usine — présence en zone interdite hors badge.",
        "Hall gare — loitering prolongé près des consignes à bagages.",
        "Parking VIP — véhicule arrêté trop longtemps sur voie pompiers.",
        "École — piéton/enfant dans voie véhicules à la sortie des classes.",
        "Data center — absence prolongée d'un agent attendu en zone ronde.",
        "Centre commercial — flânerie suspecte près entrée secours.",
        "Site portuaire — sortie non autorisée d'une zone douanière.",
    ],
    "line": [
        "Comptage entrée magasin — franchissement ligne porte principale.",
        "Sens interdit — croisement ligne dans le mauvais sens.",
        "Ligne continue routière — dépassement dangereux matérialisé.",
        "Quai métro — franchissement ligne sécurité bord de quai.",
        "Entrepôt — passage ligne jaune engins vs piétons.",
        "Stade — flux bidirectionnel portes A/B pour régulation foule.",
        "Frontière de zone — audit des croisements pendant la nuit.",
    ],
    "aggregate": [
        "Place publique — densité foule au-delà du seuil d'évacuation.",
        "Carrefour — nombre de véhicules déclenchant plan de feux adapté.",
        "Manifestation — seuil foule atteint près d'un bâtiment sensible.",
        "Parking — saturation places → message déport vers parking B.",
        "Festival — congestion accès créant risque de bousculade.",
        "Hôpital urgences — file véhicules trop dense sur dépose-minute.",
        "Tunnel urbain — embouteillage détecté pour alerte exploitation.",
    ],
    "plate": [
        "Liste blanche parking employés — ouverture barrière automatique.",
        "Liste noire véhicule volé — alerte temps réel + preuve OCR.",
        "Zone piétonne — plaque détectée = véhicule non autorisé.",
        "Flotte logistique — récurrence anormale d'une même plaque.",
        "Douane / port — plaque inconnue hors registre du jour.",
        "Contrôle pollution — corrélation plaque + zone ZFE.",
        "Enquête — historique des passages d'une plaque sur N caméras.",
    ],
    "objects": [
        "Gare — bagage abandonné près d'un banc pendant > N minutes.",
        "Musée — objet retiré d'un socle hors procédure.",
        "Aéroport — disparition chariot/équipement en zone stérile.",
        "Entrepôt — palette déplacée hors créneau inventaire.",
        "Mairie — colis suspect laissé devant entrée publique.",
        "Chantier — outil critique retiré de zone outillage.",
        "Centre commercial — sac abandonné déclenchant protocole évacuation partielle.",
    ],
    "quality": [
        "Caméra vandalisme — flou soudain → ticket maintenance prioritaire.",
        "Nuit sans IR — obscurité anormale sur axe critique.",
        "Brouillard / pluie — baisse qualité → bascule politique preuve.",
        "Sabotage optique — spray/peinture détecté via métriques blur.",
        "Mauvais focus PTZ — alerte qualité avant perte de conformité.",
        "Perte d'éclairage rue — darkness prolongée sur carrefour.",
        "Audit SLA caméra — disponibilité optique mesurée, pas seulement uptime IP.",
    ],
    "composite": [
        "Intrusion après heures — présence + hors plage horaire + zone sensible.",
        "Site industriel — corrélation identité + franchissement périmètre.",
        "Pipeline trafic — voiture → plaque → vitesse dans un seul dossier.",
        "Règle N-sur-M — N conditions observées sur M caméras avant alerte.",
        "OU logique — l'un des signaux (ligne OU zone) suffit en mode garde.",
        "Corrélation multi-sources — face + plaque sur le même créneau.",
        "Scénario VIP — ensemble de règles pour parcours sécurisé temporaire.",
    ],
    "relational": [
        "Covoiturage frauduleux — plusieurs personnes autour d'un seul véhicule en file HOV.",
        "Agression potentielle — proximité anormale personne/véhicule parking isolé.",
        "Vol à la portière — personne collée à véhicule arrêté moteur allumé.",
        "Dépose scolaire — trop de piétons autour d'un même véhicule file.",
        "Livraison suspecte — interaction prolongée personne–utilitaire zone résidentielle.",
        "Parking relais — regroupement inhabituel autour d'un véhicule la nuit.",
        "Contrôle frontière — corrélation occupants / véhicule déclaré.",
    ],
}

KEYWORD_CASES: dict[str, list[str]] = {
    "vitesse": ARCH_CASES["measure"],
    "feu": ARCH_CASES["dual_signal"],
    "ceinture": ARCH_CASES["cabin"],
    "téléphone": ARCH_CASES["cabin"],
    "telephone": ARCH_CASES["cabin"],
    "plaque": ARCH_CASES["plate"],
    "visage": ARCH_CASES["face"],
    "face": ARCH_CASES["face"],
    "foule": ARCH_CASES["aggregate"],
    "embouteillage": ARCH_CASES["aggregate"],
    "stationnement": [
        "Voie pompiers — véhicule arrêté bloquant l'accès secours.",
        "Arrêt minute gare — dépassement durée autorisée.",
        "Place PMR — occupation par véhicule non habilité.",
        "Double file centre-ville — gêne bus et vélos.",
        "Trottoir — roues sur passage piéton / bateau.",
        "Zone livraison — hors créneau horaire autorisé.",
        "Devant hydrant — stationnement critique pour pompiers.",
    ],
    "intrusion": ARCH_CASES["geometry"],
    "loitering": ARCH_CASES["geometry"],
    "objet": ARCH_CASES["objects"],
}


def cases_for(rule: dict) -> list[str]:
    name = (rule.get("name") or "").lower()
    arch = rule.get("archetype") or "geometry"
    for key, cases in KEYWORD_CASES.items():
        if key in name:
            return cases[:7]
    base = ARCH_CASES.get(arch, ARCH_CASES["geometry"])
    # lightly specialize first item with rule name
    out = list(base[:7])
    out[0] = f"{rule.get('name')} — cas terrain typique : {out[0][0].lower() + out[0][1:]}"
    return out


COMPARISON = [
    (
        "Chaîne zone → IA → règle → preuve",
        "CitéVision",
        "Égale / partielle",
        "CitéVision meilleure",
        "CitéVision impose preuves (clip, images, plaque si routier) avant statut final ; Genetec/SmartCity ont souvent alerte + vidéo, moins le package preuve métier unifié.",
    ),
    (
        "Catalogue règles transparent (real / partial / beta)",
        "CitéVision",
        "Partiel",
        "CitéVision meilleure",
        "Badges d'honnêteté produit : pas de « supported: true » sur heuristique fragile. Concurrentes affichent parfois des modules marketing plus larges que le terrain.",
    ),
    (
        "NVR multi-caméras RTSP / enregistrement",
        "À niveau (via Frigate)",
        "Genetec leader échelle",
        "À niveau sur périmètre démo/PME",
        "Genetec domine très grands déploiements, certifications et support global. CitéVision est à niveau sur ingest, restream, événements pour sites ciblés.",
    ),
    (
        "Contrôle d'accès physique + badge enterprise",
        "Partiel / intégrable",
        "Genetec meilleure",
        "Égale si intégré",
        "Genetec Security Center est une référence ACS+VMS. CitéVision se concentre vidéo intelligente + preuves ; l'ACS peut être branché mais n'est pas le cœur historique.",
    ),
    (
        "Règles cabine (ceinture, téléphone) via VLM",
        "CitéVision",
        "Rare / add-on",
        "CitéVision meilleure",
        "Pipeline Gemini cabin + fail-closed preuves est un différenciateur produit fort face aux suites VMS classiques.",
    ),
    (
        "Mesure vitesse + feu rouge + plaque dans un même dossier",
        "CitéVision",
        "Modules séparés fréquents",
        "CitéVision meilleure sur cohérence dossier",
        "Un seul pipeline d'orchestration et d'evidence_status ; moins de silos module vitesse vs module LPR.",
    ),
    (
        "Édition zones / lignes par l'opérateur (pas hardcodé)",
        "CitéVision",
        "Oui (outils carte)",
        "À niveau",
        "ZoneEditor + DB : géométrie jamais figée dans le code. Genetec/SmartCity offrent aussi des outils carte matures — parité fonctionnelle, avantage CitéVision sur discipline produit (A.1).",
    ),
    (
        "Déploiement local souverain (WSL/GPU on-prem, MinIO)",
        "CitéVision",
        "Possible mais plus lourd",
        "CitéVision meilleure pour lab/gov locaux",
        "Stack reproductible sans Docker Desktop, object storage local, runtime unique — adapté POC souverains et démos terrain.",
    ),
    (
        "Cartographie smart-city IoT large (capteurs hors vidéo)",
        "Focus vidéo+règles",
        "SmartCity souvent plus large",
        "SmartCity peut être devant sur IoT hétérogène",
        "CitéVision assume un focus preuve vidéo. Une plateforme SmartCity générique peut agréger capteurs air/énergie ; CitéVision gagne sur la profondeur vidéo métier.",
    ),
    (
        "Coût d'entrée / time-to-demo",
        "CitéVision",
        "Genetec plus élevé",
        "CitéVision meilleure",
        "Start guidé, validate_rule, caméras démo : cycle de preuve rapide pour décideurs.",
    ),
    (
        "Échelle mondiale, certifications, réseau partenaires",
        "En construction",
        "Genetec leader",
        "Genetec meilleure aujourd'hui",
        "Honnêteté : décennies d'écosystème Genetec. CitéVision vise excellence architecture preuve et collaboration Hologram 2026, pas une revendication de couverture mondiale égale.",
    ),
    (
        "Auto-heal / readiness métier avant « prêt »",
        "CitéVision",
        "Monitoring classique",
        "CitéVision meilleure sur readiness démo",
        "Business readiness (LIVE, zones, bridge, GPU) bloquante au Start — moins de fausses démos « vertes ».",
    ),
    (
        "Alerting e-mail premium avec pièces preuve",
        "CitéVision",
        "À niveau possible",
        "À niveau / CitéVision plus opinionated",
        "Mail + preuves exigées par politique produit ; Genetec a des notifications riches, CitéVision les couple au DoD preuve.",
    ),
    (
        "Openness / inspectabilité du pipeline",
        "CitéVision",
        "Plus fermé",
        "CitéVision meilleure",
        "Contrats JSON, scripts health/validate, logs cause missing evidence — auditabilité ingénieur forte.",
    ),
]


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def render_tech_rows() -> str:
    rows = []
    for tech, family, ext, where, role, why in TECH:
        rows.append(
            "<tr>"
            f"<td><strong>{esc(tech)}</strong><div class='sub'>{esc(family)}</div></td>"
            f"<td>{esc(ext)}</td>"
            f"<td><code>{esc(where)}</code></td>"
            f"<td>{esc(role)}</td>"
            f"<td>{esc(why)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_rules(*, open_all: bool = False) -> str:
    blocks = []
    for i, rule in enumerate(RULES, 1):
        rid = rule.get("id") or f"rule-{i}"
        name = rule.get("name") or rid
        arch = rule.get("archetype") or "—"
        et = rule.get("event_type") or "—"
        lis = "".join(f"<li>{esc(c)}</li>" for c in cases_for(rule))
        blocks.append(
            f"""
<details class="rule" id="{esc(rid)}"{' open' if open_all else ''}>
  <summary>
    <span class="rn">{i:02d}. {esc(name)}</span>
    <span class="rmeta"><span class="chip">{esc(arch)}</span><code>{esc(et)}</code></span>
  </summary>
  <ol class="usecases">{lis}</ol>
</details>"""
        )
    return "\n".join(blocks)


def render_comparison() -> str:
    rows = []
    for topic, cv, gen, smart, note in COMPARISON:
        rows.append(
            "<tr>"
            f"<td><strong>{esc(topic)}</strong></td>"
            f"<td>{esc(cv)}</td>"
            f"<td>{esc(gen)}</td>"
            f"<td>{esc(smart)}</td>"
            f"<td class='note'>{esc(note)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


CSS = r"""
:root {
  --bg0: #0b1012; --bg1: #12181a; --bg2: #1a2226;
  --ink: #e8efe9; --muted: #9aaba3; --faint: #6a7a74;
  --accent: #d4a574; --accent-soft: rgba(212,165,116,.14);
  --teal: #4a9b84; --ok: #7cbc8f; --danger: #c97b6a;
  --line: rgba(232,239,233,.08); --shadow: 0 24px 60px rgba(0,0,0,.45);
  --radius: 18px; --font: "Manrope", sans-serif; --display: "Fraunces", Georgia, serif;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0; font-family: var(--font); color: var(--ink);
  background:
    radial-gradient(1200px 600px at 8% -8%, rgba(74,155,132,.2), transparent 55%),
    radial-gradient(900px 500px at 92% 5%, rgba(212,165,116,.14), transparent 50%),
    radial-gradient(700px 400px at 50% 100%, rgba(74,155,132,.08), transparent 60%),
    linear-gradient(180deg, #0d1315 0%, var(--bg0) 40%, #0a0e10 100%);
  min-height: 100vh; line-height: 1.55;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.shell { width: min(1180px, calc(100% - 2rem)); margin: 0 auto; padding: 0 0 5rem; }
.hero { padding: 3.5rem 0 2.5rem; border-bottom: 1px solid var(--line); margin-bottom: 2.5rem; animation: rise .7s ease both; }
.brand {
  font-family: var(--display); font-size: clamp(2.4rem, 5vw, 3.6rem); font-weight: 700;
  letter-spacing: -.03em; margin: 0 0 .35rem;
  background: linear-gradient(120deg, #f3ebe0 10%, var(--accent) 55%, #8fd0b8 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.hero h1 {
  font-family: var(--display); font-size: clamp(1.35rem, 2.5vw, 1.75rem);
  font-weight: 500; margin: 0 0 1rem; color: var(--ink); max-width: 40ch;
}
.hero-lead { max-width: 68ch; color: var(--muted); font-size: 1.05rem; margin: 0 0 1.5rem; }
.hero-meta { display: flex; flex-wrap: wrap; gap: .6rem; }
.pill {
  display: inline-flex; align-items: center; gap: .4rem; padding: .35rem .75rem;
  border-radius: 999px; border: 1px solid var(--line); background: rgba(255,255,255,.03);
  color: var(--muted); font-size: .8rem; font-weight: 600;
}
.pill strong { color: var(--accent); font-weight: 700; }
.toc {
  position: sticky; top: .65rem; z-index: 40; backdrop-filter: blur(14px);
  background: rgba(11,16,18,.92); border: 1px solid var(--line); border-radius: 14px;
  padding: 0; margin-bottom: 1.75rem; box-shadow: var(--shadow);
  animation: rise .8s .08s ease both; overflow: hidden;
}
.toc-bar {
  display: flex; align-items: center; justify-content: space-between; gap: .75rem;
  padding: .55rem .85rem; cursor: pointer; user-select: none; border: 0; width: 100%;
  background: transparent; color: inherit; font: inherit; text-align: left;
}
.toc-bar:hover { background: rgba(255,255,255,.03); }
.toc-bar:focus-visible { outline: 2px solid var(--teal); outline-offset: -2px; }
.toc-bar-left { display: flex; align-items: center; gap: .65rem; min-width: 0; }
.toc-title { font-size: .72rem; text-transform: uppercase; letter-spacing: .12em; color: var(--faint); margin: 0; font-weight: 700; }
.toc-hint { font-size: .78rem; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.toc-toggle {
  flex-shrink: 0; display: inline-flex; align-items: center; gap: .4rem;
  padding: .28rem .65rem; border-radius: 999px; border: 1px solid rgba(74,155,132,.35);
  background: rgba(74,155,132,.12); color: #b8e0d0; font-size: .72rem; font-weight: 700;
  letter-spacing: .04em; text-transform: uppercase;
}
.toc-chevron {
  display: inline-block; width: .55rem; height: .55rem; border-right: 2px solid currentColor;
  border-bottom: 2px solid currentColor; transform: rotate(45deg); transition: transform .2s ease; margin-top: -.15rem;
}
.toc:not(.is-collapsed) .toc-chevron { transform: rotate(-135deg); margin-top: .15rem; }
.toc-panel {
  padding: 0 1rem .9rem; border-top: 1px solid var(--line);
  max-height: min(55vh, 420px); overflow: auto;
  transition: max-height .28s ease, opacity .2s ease, padding .2s ease;
}
.toc.is-collapsed .toc-panel {
  max-height: 0; opacity: 0; padding-top: 0; padding-bottom: 0;
  border-top-color: transparent; overflow: hidden; pointer-events: none;
}
.toc-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: .25rem .85rem; padding-top: .65rem;
}
.toc a {
  color: var(--muted); font-size: .84rem; font-weight: 500; text-decoration: none;
  padding: .15rem 0; border-bottom: 1px solid transparent;
}
.toc a:hover { color: var(--ink); border-bottom-color: var(--teal); text-decoration: none; }
.toc .grp { color: var(--accent); font-weight: 700; font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; margin-top: .35rem; grid-column: 1 / -1; }
.section-head { margin: 3rem 0 1.25rem; animation: rise .6s ease both; }
.section-head .eyebrow {
  font-size: .75rem; text-transform: uppercase; letter-spacing: .14em;
  color: var(--teal); font-weight: 700; margin: 0 0 .4rem;
}
.section-head h2 {
  font-family: var(--display); font-size: clamp(1.6rem, 3vw, 2.1rem);
  margin: 0 0 .6rem; letter-spacing: -.02em;
}
.section-head p { margin: 0; color: var(--muted); max-width: 72ch; }
.table-wrap {
  background: linear-gradient(145deg, var(--bg2), var(--bg1));
  border: 1px solid var(--line); border-radius: var(--radius);
  overflow: auto; margin-bottom: 2rem; box-shadow: var(--shadow);
}
table.rich { width: 100%; border-collapse: collapse; font-size: .86rem; min-width: 920px; }
table.rich th, table.rich td {
  padding: .75rem .9rem; text-align: left; border-bottom: 1px solid var(--line); vertical-align: top;
}
table.rich th {
  background: rgba(74,155,132,.14); color: var(--accent); font-size: .7rem;
  text-transform: uppercase; letter-spacing: .07em; position: sticky; top: 0; z-index: 1;
}
table.rich tr:last-child td { border-bottom: 0; }
table.rich tr:hover td { background: rgba(255,255,255,.02); }
table.rich .sub { color: var(--faint); font-size: .75rem; font-weight: 600; margin-top: .2rem; }
table.rich code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .8em;
  color: #b8e0d0; background: rgba(74,155,132,.12); padding: .08rem .3rem; border-radius: 5px;
}
table.rich td.note { color: var(--muted); font-size: .82rem; }
.rule {
  background: var(--bg1); border: 1px solid var(--line); border-radius: 14px;
  margin-bottom: .65rem; overflow: hidden; transition: border-color .2s;
}
.rule[open] { border-color: rgba(74,155,132,.4); }
.rule summary {
  list-style: none; cursor: pointer; display: flex; flex-wrap: wrap; align-items: center;
  justify-content: space-between; gap: .6rem; padding: .85rem 1.1rem;
  background: linear-gradient(90deg, var(--accent-soft), transparent 50%);
}
.rule summary::-webkit-details-marker { display: none; }
.rule summary:hover { background: rgba(255,255,255,.03); }
.rn { font-weight: 700; font-size: .95rem; }
.rmeta { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }
.chip {
  font-size: .72rem; font-weight: 700; padding: .22rem .5rem; border-radius: 8px;
  background: rgba(74,155,132,.14); color: #b8e0d0; border: 1px solid rgba(74,155,132,.25);
}
.usecases {
  margin: 0; padding: .2rem 1.25rem 1.1rem 2.2rem; color: var(--muted); font-size: .9rem;
}
.usecases li { margin: .35rem 0; }
.usecases li::marker { color: var(--accent); font-weight: 700; }
.principle {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: .85rem; margin: 1.25rem 0 1.75rem;
}
.principle article {
  padding: 1.1rem; border-radius: 14px; border: 1px solid var(--line);
  background: rgba(255,255,255,.03);
}
.principle h3 { margin: 0 0 .4rem; font-size: .95rem; color: var(--accent); }
.principle p { margin: 0; font-size: .88rem; color: var(--muted); }
.about {
  display: grid; grid-template-columns: 1.2fr .8fr; gap: 1.25rem; margin-bottom: 2rem;
}
@media (max-width: 820px) { .about { grid-template-columns: 1fr; } }
.about-card {
  background: linear-gradient(160deg, rgba(74,155,132,.12), rgba(212,165,116,.08) 55%, var(--bg1));
  border: 1px solid var(--line); border-radius: var(--radius); padding: 1.5rem 1.6rem;
  box-shadow: var(--shadow);
}
.about-card h3 {
  font-family: var(--display); font-size: 1.45rem; margin: 0 0 .75rem; letter-spacing: -.02em;
}
.about-card p { color: var(--muted); margin: 0 0 .85rem; font-size: .95rem; }
.about-card p:last-child { margin-bottom: 0; }
.about-card strong { color: var(--ink); }
.legend {
  display: flex; flex-wrap: wrap; gap: .5rem; margin: 0 0 1rem;
}
.legend span {
  font-size: .75rem; font-weight: 600; padding: .3rem .65rem; border-radius: 999px;
  border: 1px solid var(--line); color: var(--muted);
}
.legend .win { border-color: rgba(124,188,143,.45); color: #b8e0c8; background: rgba(124,188,143,.1); }
.legend .eq { border-color: rgba(212,165,116,.4); color: #e8c9a8; background: var(--accent-soft); }
.legend .them { border-color: rgba(201,123,106,.4); color: #e0b4aa; background: rgba(201,123,106,.1); }
.toolbar {
  display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; margin: 0 0 1rem;
}
.toolbar button {
  border: 1px solid rgba(74,155,132,.35); background: rgba(74,155,132,.12);
  color: #b8e0d0; border-radius: 999px; padding: .4rem .85rem; font: inherit;
  font-size: .78rem; font-weight: 700; cursor: pointer;
}
.toolbar button:hover { background: rgba(74,155,132,.22); }
.toolbar input {
  flex: 1; min-width: 180px; border-radius: 999px; border: 1px solid var(--line);
  background: rgba(255,255,255,.04); color: var(--ink); padding: .45rem 1rem; font: inherit;
}
footer {
  margin-top: 3.5rem; padding-top: 1.5rem; border-top: 1px solid var(--line);
  color: var(--faint); font-size: .85rem;
}
@keyframes rise {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: none; }
}

/* PDF / print — full-bleed pages, no white frame */
@page {
  size: A4 landscape;
  margin: 0;
}
@media print {
  html, body {
    background: #0b1012 !important;
    color: var(--ink) !important;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
    margin: 0 !important;
    padding: 0 !important;
    width: 100% !important;
    min-height: 100% !important;
  }
  /* paint dark canvas edge-to-edge (avoids white paper gutters) */
  body::before {
    content: "";
    position: fixed;
    inset: 0;
    z-index: -1;
    background: #0b1012 !important;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }
  * {
    box-shadow: none !important;
    animation: none !important;
    transition: none !important;
    backdrop-filter: none !important;
  }
  .shell {
    width: 100% !important;
    max-width: none !important;
    margin: 0 !important;
    padding: 8mm 10mm 10mm !important;
  }
  .toc, .toolbar { display: none !important; }
  .hero { padding: 0 0 8mm !important; margin-bottom: 6mm !important; break-after: avoid; }
  .brand {
    -webkit-background-clip: border-box !important;
    background: none !important;
    color: #e8c9a8 !important;
    font-size: 22pt !important;
  }
  .hero h1 { font-size: 13pt !important; max-width: none !important; }
  .hero-lead { font-size: 9.5pt !important; max-width: none !important; }
  .section-head { margin: 7mm 0 3mm !important; break-after: avoid; }
  .section-head h2 { font-size: 14pt !important; }
  .section-head p { font-size: 9pt !important; max-width: none !important; }
  .principle { gap: 3mm !important; margin: 3mm 0 5mm !important; }
  .principle article { break-inside: avoid; padding: 3mm !important; }
  .table-wrap {
    overflow: visible !important;
    box-shadow: none !important;
    margin-bottom: 5mm !important;
    border-radius: 6px !important;
  }
  table.rich {
    min-width: 0 !important;
    width: 100% !important;
    table-layout: fixed !important;
    font-size: 7.4pt !important;
  }
  table.rich th, table.rich td {
    padding: 2.2mm 2mm !important;
    overflow-wrap: anywhere !important;
    word-break: break-word !important;
    hyphens: auto;
    vertical-align: top !important;
    position: static !important;
  }
  table.rich th { font-size: 6.6pt !important; }
  table.rich .sub { font-size: 6.5pt !important; }
  table.rich td.note { font-size: 7pt !important; }
  table.rich code {
    white-space: normal !important;
    word-break: break-all !important;
    font-size: 6.8pt !important;
  }
  /* column weights — tech table (5) & comparison (5) */
  #tech table.rich th:nth-child(1), #tech table.rich td:nth-child(1) { width: 16%; }
  #tech table.rich th:nth-child(2), #tech table.rich td:nth-child(2) { width: 18%; }
  #tech table.rich th:nth-child(3), #tech table.rich td:nth-child(3) { width: 14%; }
  #tech table.rich th:nth-child(4), #tech table.rich td:nth-child(4) { width: 26%; }
  #tech table.rich th:nth-child(5), #tech table.rich td:nth-child(5) { width: 26%; }
  #compare table.rich th:nth-child(1), #compare table.rich td:nth-child(1) { width: 16%; }
  #compare table.rich th:nth-child(2), #compare table.rich td:nth-child(2) { width: 12%; }
  #compare table.rich th:nth-child(3), #compare table.rich td:nth-child(3) { width: 12%; }
  #compare table.rich th:nth-child(4), #compare table.rich td:nth-child(4) { width: 14%; }
  #compare table.rich th:nth-child(5), #compare table.rich td:nth-child(5) { width: 46%; }
  table.rich tr { break-inside: avoid; page-break-inside: avoid; }
  .rule {
    break-inside: auto;
    page-break-inside: auto;
    margin-bottom: 2.5mm !important;
    border-radius: 6px !important;
    overflow: visible !important;
  }
  .rule summary {
    display: block !important;
    padding: 2.5mm 3mm !important;
    break-after: avoid;
    page-break-after: avoid;
  }
  .rn { font-size: 9pt !important; }
  .usecases {
    padding: 0 3mm 2.5mm 7mm !important;
    font-size: 8pt !important;
  }
  .usecases li { margin: 1mm 0 !important; }
  .about { grid-template-columns: 1fr 1fr !important; gap: 4mm !important; }
  .about-card { break-inside: avoid; padding: 4mm !important; box-shadow: none !important; }
  .about-card h3 { font-size: 12pt !important; }
  .about-card p { font-size: 8.5pt !important; }
  .legend { margin-bottom: 3mm !important; }
  footer { font-size: 8pt !important; margin-top: 6mm !important; }
  a { text-decoration: none !important; }
}
"""

JS = r"""
(function () {
  var toc = document.getElementById("toc");
  var btn = document.getElementById("tocToggle");
  var panel = document.getElementById("tocPanel");
  var label = document.getElementById("tocToggleLabel");
  var hint = document.getElementById("tocHint");
  if (toc && btn && panel) {
    function setOpen(open) {
      toc.classList.toggle("is-collapsed", !open);
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) panel.removeAttribute("hidden");
      else panel.setAttribute("hidden", "");
      if (label) label.textContent = open ? "Réduire" : "Ouvrir";
      if (hint) {
        hint.textContent = open
          ? "Sommaire ouvert — cliquer pour réduire"
          : "Sommaire réduit — cliquer pour ouvrir";
      }
      try { localStorage.setItem("citevision-arch-toc-open", open ? "1" : "0"); } catch (e) {}
    }
    var preferOpen = false;
    try { preferOpen = localStorage.getItem("citevision-arch-toc-open") === "1"; } catch (e) {}
    setOpen(preferOpen);
    btn.addEventListener("click", function () {
      setOpen(toc.classList.contains("is-collapsed"));
    });
    panel.addEventListener("click", function (ev) {
      var a = ev.target.closest("a");
      if (!a) return;
      setOpen(false);
    });
  }

  var q = document.getElementById("ruleFilter");
  var rules = Array.prototype.slice.call(document.querySelectorAll("details.rule"));
  function applyFilter() {
    var v = (q && q.value || "").trim().toLowerCase();
    rules.forEach(function (el) {
      var text = el.textContent.toLowerCase();
      el.style.display = !v || text.indexOf(v) !== -1 ? "" : "none";
    });
  }
  if (q) q.addEventListener("input", applyFilter);

  var openAll = document.getElementById("openAllRules");
  var closeAll = document.getElementById("closeAllRules");
  if (openAll) openAll.addEventListener("click", function () {
    rules.forEach(function (el) { if (el.style.display !== "none") el.open = true; });
  });
  if (closeAll) closeAll.addEventListener("click", function () {
    rules.forEach(function (el) { el.open = false; });
  });
})();
"""


def build_html(*, open_all: bool = False) -> str:
    n_rules = len(RULES)
    n_tech = len(TECH)
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CitéVision — Vue d’ensemble produit, technologies &amp; règles</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,700&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <style>
{CSS}
  </style>
</head>
<body>
  <div class="shell">
    <header class="hero">
      <p class="brand">CitéVision</p>
      <h1>Vue d’ensemble — technologies, règles &amp; positionnement</h1>
      <p class="hero-lead">
        Page pratique pour présenter la solution de façon combinée&nbsp;: stack exhaustive,
        catalogue de règles avec cas d’usage terrain, comparaison honnête face à Genetec et aux
        plateformes Smart City, et genèse produit 2026. Chaîne de vérité&nbsp;:
        <em>zone → IA → règle → preuve</em>.
      </p>
      <div class="hero-meta">
        <span class="pill"><strong>{n_tech}</strong> technologies</span>
        <span class="pill"><strong>{n_rules}</strong> règles × 7 cas</span>
        <span class="pill">Comparaison Genetec · Smart City</span>
        <span class="pill"><a href="index.html">Architectures →</a></span>
        <span class="pill"><a href="CiteVision-Overview.pdf">PDF →</a></span>
      </div>
    </header>

    <nav class="toc is-collapsed" id="toc" aria-label="Sommaire">
      <button type="button" class="toc-bar" id="tocToggle" aria-expanded="false" aria-controls="tocPanel">
        <span class="toc-bar-left">
          <span class="toc-title">Navigation</span>
          <span class="toc-hint" id="tocHint">Sommaire réduit — cliquer pour ouvrir</span>
        </span>
        <span class="toc-toggle">
          <span id="tocToggleLabel">Ouvrir</span>
          <span class="toc-chevron" aria-hidden="true"></span>
        </span>
      </button>
      <div class="toc-panel" id="tocPanel" hidden>
        <div class="toc-grid">
          <span class="grp">Pages</span>
          <a href="index.html">Architectures (diagrammes)</a>
          <a href="overview.html">Cette vue d’ensemble</a>
          <a href="CiteVision-Overview.pdf">Version PDF</a>
          <span class="grp">Sections</span>
          <a href="#intro">Lire d’abord</a>
          <a href="#tech">Technologies</a>
          <a href="#rules">Règles &amp; cas d’usage</a>
          <a href="#compare">CitéVision vs concurrents</a>
          <a href="#credits">Glory Henock · Hologram</a>
        </div>
      </div>
    </nav>

    <section id="intro">
      <div class="section-head">
        <p class="eyebrow">01 — Intention</p>
        <h2>Une page pour décider, expliquer, vendre sans bluffer</h2>
        <p>
          Destinée aux décideurs, intégrateurs et équipes ops&nbsp;: inventaire technique réel,
          règles actionnables avec exemples quotidiens, et positionnement concurrentiel
          où CitéVision est meilleure <em>ou</em> à niveau — sans nier les forces Genetec
          (échelle enterprise, ACS) ni la largeur IoT des suites Smart City.
        </p>
      </div>
      <div class="principle">
        <article><h3>Preuve avant « validé »</h3><p>Alerte finale seulement si le package preuve est complet — sinon missing explicite.</p></article>
        <article><h3>Zones jamais hardcodées</h3><p>Polygones et lignes vivent dans l’éditeur / la DB, pas dans des scripts de secours.</p></article>
        <article><h3>GPU d’abord</h3><p>CUDA/ONNX prioritaires ; le CPU reste dernier recours, exposé dans /health.</p></article>
        <article><h3>Catalogue véridique</h3><p>Chaque option UI correspond à un événement réel, avec badge real / partial / beta.</p></article>
      </div>
    </section>

    <section id="tech">
      <div class="section-head">
        <p class="eyebrow">02 — Stack</p>
        <h2>Technologies exhaustives de CitéVision</h2>
        <p>
          Langages, frameworks, IA, bases, object storage, NVR, messaging et ops.
          Colonnes enrichies&nbsp;: extensions, lieu d’usage, rôle, motivation du choix.
        </p>
      </div>
      <div class="table-wrap">
        <table class="rich">
          <thead>
            <tr>
              <th>Technologie</th>
              <th>Extensions / frameworks</th>
              <th>Où utilisée</th>
              <th>Rôle dans la solution</th>
              <th>Motivation du choix</th>
            </tr>
          </thead>
          <tbody>
{render_tech_rows()}
          </tbody>
        </table>
      </div>
    </section>

    <section id="rules">
      <div class="section-head">
        <p class="eyebrow">03 — Catalogue</p>
        <h2>{n_rules} règles — 7 cas d’usage chacune</h2>
        <p>
          Cas quotidiens, pratiques et critiques (sécurité, mobilité, sites sensibles).
          Ouvrir une règle pour afficher sa palette d’exemples. Filtrer par nom ou archétype.
        </p>
      </div>
      <div class="toolbar">
        <input id="ruleFilter" type="search" placeholder="Filtrer (ex. plaque, cabin, intrusion…)" />
        <button type="button" id="openAllRules">Tout ouvrir</button>
        <button type="button" id="closeAllRules">Tout fermer</button>
      </div>
{render_rules(open_all=open_all)}
    </section>

    <section id="compare">
      <div class="section-head">
        <p class="eyebrow">04 — Positionnement</p>
        <h2>CitéVision · Genetec · Smart City — parallèle honnête</h2>
        <p>
          Lecture orientée « où CitéVision gagne ou égale ». Les cases où un concurrent reste
          structurellement plus fort (échelle mondiale Genetec, IoT large Smart City) sont assumées.
        </p>
      </div>
      <div class="legend">
        <span class="win">CitéVision en avance</span>
        <span class="eq">À niveau / parité</span>
        <span class="them">Concurrent structurellement plus fort</span>
      </div>
      <div class="table-wrap">
        <table class="rich">
          <thead>
            <tr>
              <th>Critère</th>
              <th>CitéVision</th>
              <th>Genetec</th>
              <th>Smart City (générique)</th>
              <th>Lecture</th>
            </tr>
          </thead>
          <tbody>
{render_comparison()}
          </tbody>
        </table>
      </div>
    </section>

    <section id="credits">
      <div class="section-head">
        <p class="eyebrow">05 — Genèse 2026</p>
        <h2>Développeur &amp; collaboration entreprise</h2>
        <p>Contexte humain derrière l’architecture zone → IA → règle → preuve.</p>
      </div>
      <div class="about">
        <div class="about-card">
          <h3>Glory Henock</h3>
          <p>
            <strong>Glory Henock</strong> est le développeur principal de CitéVision&nbsp;:
            conception de la chaîne d’orchestration, exigence de preuves infalsifiables,
            runtime WSL unique, catalogue de règles et console opérateur.
          </p>
          <p>
            Son travail en 2026 vise une plateforme vidéo intelligente où chaque alerte
            « validée » est défendable&nbsp;: géométrie réelle, inférence GPU, règle métier,
            puis package preuve (clip, images, plaque si routier) — sans raccourci marketing.
          </p>
          <p>
            Contact technique / repos&nbsp;:
            <a href="https://github.com/henockglory" target="_blank" rel="noopener">github.com/henockglory</a>
          </p>
        </div>
        <div class="about-card">
          <h3>Hologram Identification Service</h3>
          <p>
            CitéVision est développée en <strong>étroite collaboration</strong> avec
            <strong>Hologram Identification Service</strong> en <strong>2026</strong>&nbsp;:
            ancrage terrain identification / sécurité, exigences preuves, et cadrage produit
            pour des déploiements réalistes (mobilité, sites sensibles, collectivités).
          </p>
          <p>
            Cette collaboration oriente les priorités&nbsp;: honnêteté du catalogue,
            readiness métier au démarrage, et dossiers d’alerte exploitables par des opérateurs
            — pas seulement des logs MQTT.
          </p>
        </div>
      </div>
    </section>

    <footer>
      <p>
        CitéVision — vue d’ensemble produit ({n_tech} technologies, {n_rules} règles).
        Voir aussi <a href="index.html">Architectures métier &amp; produit</a>,
        <a href="CiteVision-Architectures.pptx">le deck PowerPoint</a>
        et <a href="CiteVision-Overview.pdf">la version PDF</a>.
        Généré via <code>build_overview.py</code> à partir du contrat d’orchestration.
      </p>
    </footer>
  </div>
  <script>
{JS}
  </script>
</body>
</html>
"""


def main() -> None:
    out = ROOT / "overview.html"
    out.write_text(build_html(open_all=False), encoding="utf-8", newline="\n")
    print(f"Wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
