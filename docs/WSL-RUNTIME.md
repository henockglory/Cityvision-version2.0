# Workspace runtime — WSL only (Sprint 0 / Décision 1)

**Runtime + édition de vérité** : ouvrir Cursor sur le dossier WSL :

```
\\wsl.localhost\Ubuntu-24.04\home\gheno\citevision-v2
```

ou via Remote-WSL : `/home/gheno/citevision-v2`.

`C:\Users\gheno\citevision` n'est plus le runtime. Si ce clone Windows existe encore, ne l'utiliser que comme miroir ponctuel — toute livraison se fait dans `~/citevision-v2`.

Avant chaque session de validation :

```bash
bash scripts/health_check_all.sh
```

Docker Desktop : **interdit**. Dockerd natif : `bash scripts/_start_dockerd_wsl.sh`.
