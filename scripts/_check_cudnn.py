import glob
import os
import site

for sp in site.getsitepackages():
    for rel in ("nvidia/cudnn/lib", "nvidia/cublas/lib", "nvidia/cuda_runtime/lib"):
        p = os.path.join(sp, rel)
        if os.path.isdir(p):
            print(p)
            cudnn = os.path.join(p, "libcudnn.so.9")
            if os.path.isfile(cudnn):
                print("  libcudnn.so.9 OK")
