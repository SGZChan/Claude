"""Download the default ~0.5B GGUF model (Qwen2.5-0.5B-Instruct, Q4_K_M, ~400 MB)."""
from pathlib import Path

from huggingface_hub import hf_hub_download

dest = Path("models")
dest.mkdir(exist_ok=True)
path = hf_hub_download("Qwen/Qwen2.5-0.5B-Instruct-GGUF", "qwen2.5-0.5b-instruct-q4_k_m.gguf", local_dir=dest)
print("saved to", path)
