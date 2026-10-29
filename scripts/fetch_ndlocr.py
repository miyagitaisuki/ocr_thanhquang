"""Tải NDLOCR-Lite (đúng commit đã ghim) vào vendor/ndlocr-lite."""
import subprocess, sys
from pathlib import Path

COMMIT = "e57f7c6bd9cfb3de5f12f008e71ad2122bd44bfd"
dest = Path(__file__).resolve().parents[1] / "vendor" / "ndlocr-lite"
if (dest / "src" / "ocr.py").is_file():
    print("Đã có", dest); sys.exit(0)
dest.parent.mkdir(exist_ok=True)
run = lambda *a, **k: subprocess.run(a, check=True, **k)
run("git", "clone", "--filter=blob:none", "https://github.com/ndl-lab/ndlocr-lite", str(dest))
run("git", "-C", str(dest), "checkout", COMMIT)
print("OK", dest)
