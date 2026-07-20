# Source de vérité — code & runtime (P.138)

> Référence unique et faisant autorité pour savoir **où vit le code** et **où il s'exécute**.
> Objectif : éviter qu'une modification faite côté Windows ne soit jamais prise en compte
> par le runtime WSL (cause historique de « je corrige mais rien ne change »).

## 1. Les deux emplacements

| Rôle | Chemin | Nature |
|------|--------|--------|
| **Source de vérité du code** (git) | `C:\Users\gheno\citevision` — vu depuis WSL : `/mnt/c/Users/gheno/citevision` | Dépôt Git. **Toute modification de code se fait ici.** |
| **Runtime d'exécution** | `~/citevision-v2` dans WSL `Ubuntu-24.04` | Copie déployée qui exécute réellement backend, AI engine, rules-engine, frontend. |

**Règle d'or :** une modification n'est **« livrée »** que lorsqu'elle a été **synchronisée vers `~/citevision-v2`** puis que le service concerné a été **redémarré**. Tant que ce n'est pas fait, le runtime exécute l'ancienne version.

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

## 4. Procédure standard après une modification de code

1. **Éditer** dans `C:\Users\gheno\citevision` (dépôt Git).
2. **Synchroniser** vers le runtime :
   - Modèle IA / pipeline Python / `shared/*.json` → `bash scripts/_deploy_and_install_ai.sh`
   - Backend Go / frontend / infra → `bash scripts/_fast_deploy.sh` (ou build + `restart-api-frontend.sh`)
3. **Redémarrer** le service concerné (voir scripts `restart-*.sh`).
4. **Vérifier** via `/health` (backend 8081, AI 8001, rules 8010) et l'UI (5174).

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
| Frontend (Vite) | 5174 |
| go2rtc | 1984 |
| MailHog (UI) | 8025 |
