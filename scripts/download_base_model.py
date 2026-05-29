"""
Download Qwen/Qwen2.5-3B-Instruct dari HuggingFace ke disk lokal.
Output: models/qwen2.5-3b-base-hf/

Install deps (di venv_awq):
    pip install huggingface_hub
"""
import os
from huggingface_hub import snapshot_download

OUTPUT_DIR = "./models/qwen2.5-3b-base-hf"

if os.path.exists(OUTPUT_DIR) and os.listdir(OUTPUT_DIR):
    print(f"Model sudah ada di {OUTPUT_DIR}, skip download")
else:
    print("Downloading Qwen/Qwen2.5-3B-Instruct...")
    snapshot_download(
        repo_id="Qwen/Qwen2.5-3B-Instruct",
        local_dir=OUTPUT_DIR,
        ignore_patterns=["*.pt", "original/*"],  # skip raw checkpoint files
    )
    print(f"Download selesai: {OUTPUT_DIR}")
