# ==============================================================================
# Tujuan       : Validate & migrate ke model 3B
# Usage        : python scripts/migrate_to_3b.py
# Catatan      : psutil opsional — kalau belum keinstall, RAM check di-skip
#                (pip install psutil untuk cek RAM akurat)
# ==============================================================================

import os
import shutil

CURRENT_MODEL = os.getenv("CHATBOT_MODEL_PATH", "models/qwen2.5-1.5b-k3.gguf")
NEW_MODEL = "models/qwen2.5-3b-instruct-q4_k_m.gguf"   # adjust filename


def check_resources():
    """Check RAM availability (butuh psutil)."""
    try:
        import psutil
    except ImportError:
        print("⚠️ psutil belum terinstall — skip RAM check (pip install psutil)")
        print("   Pastikan manual: 3B Q4_K_M butuh ~3.5GB RAM bebas.")
        return True

    ram_gb = psutil.virtual_memory().available / (1024 ** 3)
    print(f"Available RAM: {ram_gb:.1f} GB")
    if ram_gb < 3.5:
        print("⚠️ RAM kurang untuk 3B model. Stay di 1.5B atau tutup aplikasi lain.")
        return False
    return True


def check_disk():
    """Check disk space."""
    free_gb = shutil.disk_usage(".").free / (1024 ** 3)
    print(f"Free disk: {free_gb:.1f} GB")
    if free_gb < 5:
        print("⚠️ Disk space kurang (butuh ~2GB untuk download + 2GB buffer)")
        return False
    return True


def update_env():
    """Update .env path."""
    print("\n📝 Update .env:")
    print(f"   CHATBOT_MODEL_PATH={NEW_MODEL}")
    print(f"\n💡 Backup model lama dulu: copy {CURRENT_MODEL} -> {CURRENT_MODEL}.bak")
    print("💡 Download model dari Hugging Face:")
    print("   huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF qwen2.5-3b-instruct-q4_k_m.gguf --local-dir models/")


def main():
    print("=== Model Upgrade Checker ===\n")
    if check_resources() and check_disk():
        print("\n✅ System siap untuk upgrade")
        update_env()
    else:
        print("\n❌ Cancel upgrade")


if __name__ == "__main__":
    main()
