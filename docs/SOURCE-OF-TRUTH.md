# Source de vérité — code & runtime (P.138)

> Référence unique et faisant autorité pour savoir **où vit le code** et **où il s'exécute**.
> Objectif : éviter qu'une modification faite côté Windows ne soit jamais prise en compte
> par le runtime WSL (cause historique de « je corrige mais rien ne change »).

## 1. Les emplacements

| Rôle | Chemin | Nature |
|------|--------|--------|
| **Dépôt de travail / ship** | `C:\Users\gheno\citevision-v2` — vu depuis WSL : `/mnt/c/Users/gheno/citevision-v2` | Arbre Cursor. **Éditer et committer ici**, puis pousser `origin` + `v2`. |
| **Miroir GitHub (installateur)** | `C:\Users\gheno\citevision` — `/mnt/c/Users/gheno/citevision` | Aligné sur `origin/main` après chaque ship. Ne pas y éditer en premier. |
| **Runtime d'exécution** | `~/citevision-v2` dans WSL `Ubuntu-24.04` | Copie déployée qui exécute backend, AI engine, rules-engine, frontend static `:5174`. |
| **Miroirs installateur / sandbox** | `C:\Citevision`, `C:\Users\gheno\citevision_optimized` | Alignés après ship (rsync + `git reset --hard origin/main`). |

**Règle d'or :** une modification n'est **« livrée »** que lorsqu'elle a été **synchronisée vers `~/citevision-v2`** puis que le service concerné a été **redémarré** (Start rebuild `frontend/dist` et `backend/bin/citevision-api` si les sources ont changé). Tant que ce n'est pas fait, le runtime exécute l'ancienne version.

Ne pas lancer `scripts/sync-all-targets.sh` depuis un runtime WSL périmé : il ferait `rsync --delete` **depuis** WSL vers Windows et effacerait les correctifs du dépôt de travail.

## 2. Distribution WSL de référence

- Distribution runtime : **`Ubuntu-24.04`** (voir `wsl.exe -l -v`).
- Ne pas utiliser l'autre distribution `Ubuntu` (héritage) pour le runtime démo.

## 3. Flux de synchronisation Windows → WSL

Le déploiement copie les fichiers du dépôt Windows vers le runtime. Références :

- `scripts/_deploy_and_install_ai.sh` — copie `ai-engine/src`, `shared/*.json`, scripts IA, puis
  `pip install -e ai-engine/.` et `install-ai-models.sh --fix`.
- `scripts/_fast_deploy.sh` — déploiement rapide (Docker infra + backend build + restart API/frontend).

> ⚠️ Ces scripts font aussi `sed -i 's/\r$//'` pour retirer les fins de ligne CRLF Windows :
> ne jamais exécuter directement les `.sh` du dépôt Windows dans WSL sans cette normalisation.

Remotes Git (tous les clones) :
- `origin` → `https://github.com/henockglory/Cityvision-version2.0.git`
- `v2` → `https://github.com/henockglory/Cityvision-v2.git`

## 4. Procédure standard après une modification de code

1. **Éditer** dans `C:\Users\gheno\citevision-v2` (dépôt de travail).
2. **Synchroniser** vers le runtime WSL `~/citevision-v2` (rsync Windows → WSL, **sans** `--delete` depuis un WSL périmé) :
   - Modèle IA / pipeline Python / `shared/*.json` → `bash scripts/_deploy_and_install_ai.sh`
   - Backend Go / frontend / infra → Start (`ensure-frontend` + `ensure-backend-bin`) ou `bash scripts/_fast_deploy.sh`
3. **Redémarrer** le service concerné (voir scripts `restart-*.sh`) — Start relance l'IA si `frigate_track_evidence.py` est plus récent que le process.
4. **Vérifier** via `/health` (backend 8081, AI 8001, rules 8010) et l'UI static (5174).

## 5. Ce qui NE vit PAS dans le dépôt (donc jamais « livrable » par git)

- **Vidéos de démo** (`Feux.mp4`, `Décompte des voitures.mp4`, `Ligne Continue.mp4`,
  `Port de Ceinture.mp4`) : téléversées via l'UI, stockées côté backend/MinIO — **pas dans git**.
  Après une réinstallation WSL / reset du stockage, elles doivent être **re-téléversées**.
- **Modèles IA** (`.onnx`, InsightFace `buffalo_l`, PaddleOCR) : installés par
  `scripts/install-ai-models.sh --fix`, jamais commités.
- **`.env` / `generated.env`** : générés par machine (profil matériel), jamais la source de vérité du code.

## 6. Ports runtime de référence

| Service | Port |
|---------|------|
| Backend API | 8081 |
| AI engine | 8001 |
| Rules engine | 8010 |
| Frontend (static product UI) | 5174 |
| go2rtc | 1984 |
| MailHog (UI) | 8025 |
