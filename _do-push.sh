#!/usr/bin/env bash
# Push complet vers les 2 repos GitHub
set -e

PAT="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"
REPO1="https://${PAT}@github.com/henockglory/Cityvision-v2.git"
REPO2="https://${PAT}@github.com/henockglory/Cityvision-version2.0.git"

cd /mnt/c/Users/gheno/citevision-v2

echo "[1/4] Configuring git..."
git config user.email "heegyboanerges@gmail.com"
git config user.name "henockglory"
git config core.autocrlf false

echo "[2/4] Staging all files..."
git add -A --force
git status --short | wc -l

echo "[3/4] Committing..."
git commit -m "feat: premium installer pipeline + hardware elasticity + fresh-run UX

- Complete installer: WSL2 bootstrap, Python auto-install, Docker setup
- Hardware elasticity: GPU tier detection applied to app config
- Installer UI: EyeLogo SVG, cv-* design system, no emojis, SVG icons
- Fix subprocess blocking (CREATE_NO_WINDOW, DEVNULL, PYTHONIOENCODING)
- Fix WSL path conversion C:\\ -> /mnt/c/
- Add heartbeat SSE every 2s during long steps
- Add Step 4 Launch: runs start-linux.sh, polls port 5174
- Add sentinel to skip pip install after first run
- Fix NameError _subprocess in launch_stream
- Fresh user experience: DB reset, admin credentials
- sync-to-citevision.bat for one-click sync
- Comprehensive .gitignore cleanup" 2>/dev/null || echo "Nothing new to commit"

echo "[4/4] Pushing..."
git remote set-url origin "$REPO1" 2>/dev/null || git remote add origin "$REPO1"
git push -u origin HEAD:main --force
echo "Pushed to Cityvision-v2"

git remote set-url backup "$REPO2" 2>/dev/null || git remote add backup "$REPO2"
git push backup HEAD:main --force
echo "Pushed to Cityvision-version2.0"

echo "DONE"
