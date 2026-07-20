from pathlib import Path
p = Path("/home/gheno/citevision-v2/ai-engine/src/citevision_ai/pipeline.py")
b = p.read_bytes()
p.write_bytes(b.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
line = p.read_text().splitlines()[15]
print(line)
