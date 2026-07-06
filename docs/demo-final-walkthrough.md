# Démo finale — parcours manuel (4 vidéos × 5 règles)

Checklist pour valider la chaîne complète **détection → alerte → preuves (clip + 2 images) → mail premium** avant branchement d’une vraie caméra.

## Prérequis

- Stack démarrée (backend, AI engine, rules-engine, MailHog, go2rtc)
- Vidéos démo restaurées : `bash scripts/restore-demo-after-reset.sh` si besoin
- Règles seedées : `bash scripts/seed-demo-rules.sh` (désactivées par défaut après audit)
- Sync spatial : `bash scripts/force-spatial-reload.sh`

Validation automatisée rapide :

```bash
bash scripts/demo-manual-checklist.sh
```

## Parcours (une règle à la fois)

| Étape | Action |
|-------|--------|
| 1 | `/rules` → section **Règles personnalisées** → activer **une** règle « Démo · … » |
| 2 | `/demo` → sélectionner la **vidéo correspondante** (voir tableau ci-dessous) |
| 3 | Attendre **30–90 s** → panneaux **Détections live** et **Alertes live** |
| 4 | Cliquer une ligne → **modal premium** (clip MP4 + vue d’ensemble + cible) |
| 5 | **Boîte e-mail test** (MailHog) → mail HTML CitéVision avec images inline |

### Mapping règle → vidéo

| Règle | Vidéo dans `/demo` | Preuves + mail |
|-------|-------------------|----------------|
| Démo · Excès de vitesse | Ligne Continue | Oui |
| Démo · Feu rouge | Feux | Oui |
| Démo · Téléphone au volant | Port de Ceinture | Oui |
| Démo · Non-port ceinture | Port de Ceinture | Oui |
| Démo · Comptage véhicules | Décompte | Compteur ligne uniquement |

Si la vidéo active ne correspond pas à la caméra de la règle, un bandeau d’avertissement apparaît avec **Changer → [vidéo]**.

## Après la démo : vraie caméra

1. Dupliquer une règle démo (bouton Copier sur `/rules`)
2. Dans l’éditeur : changer **caméra**, ajuster zone/ligne si nécessaire
3. Activer → même flux alertes / preuves / mails

## Validation exhaustive (5 règles)

```bash
bash scripts/validate-demo-five-sequential.sh
```

Les règles sont **désactivées** à la fin pour laisser la démo propre.

## Dépannage

| Problème | Action |
|----------|--------|
| 0 alerte après 90 s | `bash scripts/force-spatial-reload.sh` ; vérifier rules-engine `/health` (`active_rules=1`) |
| Preuves « Partielle (0/3) » | Règle inactive ou mauvaise vidéo ; activer la règle et attendre une alerte (pas seulement un événement brut) |
| Pas de mail | Vérifier MailHog `:8025` et `ALERT_EMAIL_TO` / `ADMIN_EMAIL` dans `.env` |
