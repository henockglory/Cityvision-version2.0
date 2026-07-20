# GPU NVIDIA sous WSL2 (RTX 4050)

CitéVision utilise **CUDA par défaut** pour l'inférence YOLO (`YOLO_DEVICE=cuda`).

## Prérequis

1. **Driver NVIDIA Windows** récent (support WSL2 CUDA) — [nvidia.com/drivers](https://www.nvidia.com/drivers)
2. **WSL2** avec Ubuntu 22.04/24.04
3. Vérifier dans WSL :

```bash
nvidia-smi
```

Si la commande échoue, mettez à jour le driver Windows et redémarrez.

## Installation AI Engine avec CUDA

```bash
cd ~/citevision-v2
bash scripts/sync-to-wsl.sh
bash scripts/export-yolo-onnx.sh
bash scripts/start-linux.sh
```

Le venv installe `onnxruntime-gpu`. Vérification :

```bash
bash scripts/validate-gpu.sh
curl -s http://localhost:8001/health/gpu | python3 -m json.tool
```

Attendu : `yolo_cuda: true`, `benchmark_fps` ≥ 15.

## Dépannage

| Symptôme | Action |
|----------|--------|
| `CUDAExecutionProvider unavailable` | `pip install onnxruntime-gpu` dans `ai-engine/.venv` |
| FPS CPU ~5–10 | Confirmer `nvidia-smi` dans WSL |
| Modèle absent | `bash scripts/export-yolo-onnx.sh` |
| Vidéo lente | Copier `benedicte.mp4` vers `data/videos/` (ext4), pas `/mnt/c/` |

## Variables d'environnement

Voir `ai-engine/.env.example` :

- `YOLO_DEVICE=cuda`
- `CUDA_VISIBLE_DEVICES=0`
- `YOLO_MIN_FPS=15`
