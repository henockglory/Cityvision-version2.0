# Ops — reprise en une commande (Sprint 3)

## Une commande après `wsl --shutdown` / crash

```bash
bash ~/citevision-v2/scripts/stack-up.sh
```

Enchaîne : dockerd natif → compose infra (+ Frigate) → heal streams → restart AI → `health_check_all`.

## Boot automatique WSL (une fois)

```bash
bash ~/citevision-v2/scripts/install-wsl-boot.sh
# depuis Windows :
wsl --shutdown
# rouvrir Ubuntu — dockerd + infra démarrent via /etc/wsl.conf
```

Log boot : `/tmp/citevision-wsl-boot.log`

## `/health` GPU (A.5)

Si `YOLO_DEVICE=cuda` et le provider actif n'est pas CUDA → **HTTP 503** avec
`status=gpu_required_inactive`, `gpu_active=false`.

Contournement explicite (déconseillé) : `ALLOW_CPU_HEALTH=1`.

## Interdit

Docker Desktop. Uniquement dockerd natif WSL (`scripts/_start_dockerd_wsl.sh`).
