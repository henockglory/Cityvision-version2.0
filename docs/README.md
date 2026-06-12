# Citévision 2.0 — Documentation

Plateforme de vidéosurveillance intelligente modulaire (React / Go / C++ / Python).

## Démarrage rapide

```bash
# WSL Ubuntu 24.04 (recommandé)
cd /home/gheno/citevision
bash scripts/setup-wsl.sh
docker compose up -d
bash scripts/start-all.sh
```

Windows natif (fallback) :

```powershell
cd C:\Users\gheno\citevision
docker compose up -d
```

Frontend : http://localhost:5173  
API : http://localhost:8080/api/v1  
AI Engine : http://localhost:8000  

**Connexion par défaut** : `admin@citevision.local` / `Citevision123!`

## Index

| Document | Description |
|----------|-------------|
| [PROMPT-AGENT.md](PROMPT-AGENT.md) | Prompt maître pour agents IA |
| [STATE.md](STATE.md) | État d'avancement et reprise |
| [DECISIONS.md](DECISIONS.md) | Arbitrages techniques figés |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Architecture multi-services |
| [PORTS.md](PORTS.md) | Ports réseau |
| [INSTALL.md](INSTALL.md) | Installation from scratch |
| [OPERATIONS.md](OPERATIONS.md) | Exploitation et maintenance |

## Validation

```bash
bash scripts/validate-l1.sh   # … validate-l13.sh
bash scripts/validate-final.sh
bash scripts/run-all-tests.sh
```

## Caméra de test

Configurer via `.env` uniquement (`TEST_CAMERA_IP`, `TEST_CAMERA_USER`, `TEST_CAMERA_PASSWORD`).  
Ne jamais hardcoder l'IP dans le code source.
