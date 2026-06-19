import subprocess, sys
try:
    import onnxruntime as ort
    print("onnxruntime version:", ort.__version__)
    print("providers:", ort.get_available_providers())
    print("CUDA available:", "CUDAExecutionProvider" in ort.get_available_providers())
except ImportError as e:
    print("onnxruntime not importable:", e)

r = subprocess.run(["pip", "show", "onnxruntime-gpu"], capture_output=True, text=True)
print("onnxruntime-gpu:", r.stdout.strip() or "NOT INSTALLED")
r2 = subprocess.run(["pip", "show", "onnxruntime"], capture_output=True, text=True)
print("onnxruntime:", r2.stdout.split("\n")[0] if r2.stdout else "NOT INSTALLED")
