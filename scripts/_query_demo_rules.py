#!/usr/bin/env python3
import subprocess

subprocess.run(
    [
        "docker",
        "exec",
        "citevision-v2-postgres",
        "psql",
        "-U",
        "citevision",
        "-d",
        "citevision",
        "-c",
        "SELECT name, is_enabled FROM rules WHERE name LIKE 'Démo%' ORDER BY name;",
    ],
    check=False,
)
