from pathlib import Path

paths = [
    Path("/home/gheno/citevision-v2/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py"),
    Path("/mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py"),
]
for p in paths:
    t = p.read_text(encoding="utf-8")
    t = t.replace("import urllib.errorr", "import urllib.error")
    # Fix truncated import without touching a correct urllib.error line.
    lines = t.splitlines(True)
    out = []
    for line in lines:
        if line.replace("\r\n", "\n").replace("\r", "\n").strip() == "import urllib.erro":
            out.append("import urllib.error\n")
        else:
            out.append(line.replace("\r\n", "\n").replace("\r", "\n"))
    p.write_text("".join(out), encoding="utf-8", newline="\n")
    print(p, repr(p.read_text(encoding="utf-8").splitlines()[11]))
