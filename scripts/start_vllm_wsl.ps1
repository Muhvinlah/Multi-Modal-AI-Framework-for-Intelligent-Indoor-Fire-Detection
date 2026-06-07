# start_vllm_wsl.ps1
# Jalankan vLLM di dalam WSL2 Ubuntu (vLLM tidak support Windows native).
# Model AWQ di-mount dari Windows via /mnt/d/...
#
# Usage (dari folder proyek):
#   .\scripts\start_vllm_wsl.ps1
#
# Prerequisite (cukup sekali, jalankan di terminal WSL2 langsung):
#   sudo apt-get install -y nvidia-cuda-toolkit build-essential

$PROJECT_WIN = (Get-Location).Path
$drive = $PROJECT_WIN[0].ToString().ToLower()
$rest = $PROJECT_WIN.Substring(2).Replace('\', '/')
$MODEL_WSL = "/mnt/$drive$rest/models/qwen2.5-3b-instruct-awq"

Write-Host "Starting vLLM in WSL2 Ubuntu..."
Write-Host "  Model : $MODEL_WSL"
Write-Host "  Port  : 8002"
Write-Host ""

$bashScript = @'
#!/bin/bash
set -e
source ~/venv_vllm/bin/activate

# Auto-detect CUDA_HOME untuk FlashInfer JIT
if [ -z "$CUDA_HOME" ]; then
    for p in /usr/local/cuda /usr/lib/cuda /usr/local/cuda-* ; do
        if [ -f "$p/bin/nvcc" ]; then
            export CUDA_HOME="$p"
            break
        fi
    done
    # Fallback: cari nvcc di PATH
    if [ -z "$CUDA_HOME" ] && command -v nvcc &>/dev/null; then
        export CUDA_HOME="$(dirname $(dirname $(which nvcc)))"
    fi
fi

if [ -n "$CUDA_HOME" ]; then
    export PATH="$CUDA_HOME/bin:$PATH"
    export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
    echo "CUDA_HOME: $CUDA_HOME  (nvcc: $(nvcc --version 2>&1 | grep release | head -1))"
else
    echo "WARNING: CUDA_HOME tidak ditemukan, FlashInfer JIT mungkin gagal"
    echo "  Fix: sudo apt-get install -y nvidia-cuda-toolkit"
fi

MODEL="__MODEL_PATH__"
if [ ! -f "$MODEL/config.json" ]; then
    echo "ERROR: AWQ model tidak ditemukan di $MODEL"
    exit 1
fi
echo "Model OK: $MODEL"
echo ""

exec vllm serve "$MODEL" \
    --served-model-name qwen-k3 \
    --port 8002 \
    --quantization awq \
    --dtype float16 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.50 \
    --max-num-seqs 2 \
    --enforce-eager \
    --trust-remote-code
'@

$bashScript = $bashScript.Replace('__MODEL_PATH__', $MODEL_WSL)

# Hapus \r agar format berubah dari CRLF (Windows) menjadi LF (Linux)
$bashScript = $bashScript -replace "`r`n", "`n"

$tmpFile = "$env:TEMP\start_vllm_tmp.sh"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($tmpFile, $bashScript, $utf8NoBom)

$tmpDrive = $tmpFile[0].ToString().ToLower()
$tmpRest = $tmpFile.Substring(2).Replace('\', '/')
$tmpWSL = "/mnt/$tmpDrive$tmpRest"

wsl bash "$tmpWSL"
