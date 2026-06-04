# Sistem Deteksi Kebakaran — Multi-Modal AI

Sistem deteksi kebakaran berbasis IoT + AI yang menggabungkan ESP32 (sensor gas MQ), Computer Vision (YOLOv11), LSTM anomaly detection, XGBoost sensor fusion, dan Chatbot K3 offline menggunakan LLM lokal (Qwen 2.5 AWQ via vLLM).

**Tim:** Ervin, Akmal, Jascon, Farhan — PBL Semester 6

---

## Arsitektur Sistem

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   ESP32     │────▶│  Dashboard       │────▶│  Chatbot Service │
│ 6x Sensor   │     │  FastAPI :8000   │◀────│  FastAPI :8001   │
│ MQ Gas      │     │  YOLO + LSTM     │     │  RAG + Intent    │
└─────────────┘     │  XGBoost Fusion  │     │  Tool Calling    │
                    └──────────────────┘     └────────┬─────────┘
                                                       │ OpenAI API compat
                                             ┌─────────▼─────────┐
                                             │  vLLM Server      │
                                             │  :8002            │
                                             │  Qwen2.5-3B AWQ   │
                                             └───────────────────┘
```

| Service | Port | Teknologi | Deskripsi |
|---------|------|-----------|-----------|
| Dashboard | 8000 | FastAPI | Sensor, kamera RTSP, YOLO, LSTM, WebSocket |
| Chatbot Service | 8001 | FastAPI | Intent routing, RAG, tool calling, circuit breaker |
| vLLM | 8002 | vLLM OpenAI-compat | Qwen 2.5-3B AWQ inference |

---

## Persyaratan Hardware

| Komponen | Minimum | Rekomendasi |
|----------|---------|-------------|
| GPU | NVIDIA RTX 3060 6 GB | RTX 3060 Ti 8 GB+ |
| RAM | 16 GB | 32 GB |
| Disk | 20 GB free | 40 GB free |
| OS | Ubuntu 20.04+ / WSL2 | Ubuntu 22.04 LTS |
| CUDA | 12.1 | 12.4 |

> **Windows:** vLLM tidak support Windows native. Wajib gunakan **WSL2** (Ubuntu) untuk menjalankan vLLM. Dashboard dan chatbot service bisa jalan di Windows Python biasa.

---

## Struktur Proyek

```
sistem_deteksi_kebakaran/
├── main.py                      # Entry point Dashboard (FastAPI :8000)
├── app/
│   ├── ai_engine.py             # YOLO + XGBoost + Decision Fusion
│   ├── lstm_anomaly.py          # LSTM autoencoder anomaly detection
│   ├── camera.py                # Manager multi-kamera RTSP
│   ├── sensor.py                # Endpoint data sensor ESP32
│   ├── chatbot_proxy.py         # Circuit-breaker proxy ke chatbot_service
│   ├── internal_api.py          # API internal (sensor snapshot dll)
│   ├── auth.py                  # Login / JWT
│   ├── feedback.py              # Feedback loop (SQLite)
│   ├── notification.py          # Telegram alert
│   ├── pdf_export.py            # Export laporan PDF
│   ├── websocket_handler.py     # WebSocket real-time monitoring
│   └── config.py                # Konfigurasi global + state dinamis
├── chatbot_service/             # Chatbot microservice (FastAPI :8001)
│   ├── main.py                  # Entry point chatbot service
│   ├── config.py                # Config terpusat (env vars)
│   ├── llm_engine.py            # Klien ke vLLM (openai-compat)
│   ├── rag_engine.py            # Hybrid RAG: BM25 + dense + rerank
│   ├── intent_router.py         # Intent classifier
│   ├── chat_tools.py            # Tool calling dispatcher
│   ├── prompt_builder.py        # Prompt assembly
│   ├── conversation.py          # History + auto-summary
│   └── requirements.txt         # Dependensi chatbot service
├── models/                      # Model AI (sebagian git-ignored)
│   ├── best.pt                  # YOLOv11 deteksi api/asap
│   ├── fire_detection_rf.pkl    # XGBoost sensor prediction
│   ├── scaler.pkl               # StandardScaler fitur sensor
│   ├── lstm_anomaly.keras       # LSTM autoencoder
│   ├── lstm_scaler.pkl          # Scaler LSTM
│   ├── lstm_threshold.json      # Threshold normalisasi LSTM
│   └── qwen2.5-3b-base-awq/     # AWQ model (git-ignored, ~2 GB)
├── scripts/
│   ├── start_all.sh             # Start semua service (Linux/WSL2)
│   ├── stop_all.sh              # Stop semua service
│   ├── smoke_test_e2e.sh        # End-to-end smoke test
│   ├── start_vllm.sh            # Start vLLM (Linux/WSL2)
│   ├── start_vllm_wsl.ps1       # Start vLLM via WSL2 (Windows PowerShell)
│   ├── download_base_model.py   # Download Qwen2.5-3B dari HuggingFace
│   ├── quantize_to_awq.py       # Quantize ke AWQ (venv_awq)
│   └── requirements_awq.txt     # Dependensi quantize (venv terpisah)
├── esp32/fire_sensor/
│   └── fire_sensor.ino          # Firmware ESP32 (Captive Portal + NVS)
├── docs/                        # PDF panduan K3 untuk RAG
│   ├── *.pdf
│   └── faq/system.md
├── templates/index.html         # Dashboard UI
├── static/js/dashboard.js       # Frontend logic
├── ingest_pdf.py                # Ingest PDF → ChromaDB + BM25
├── ingest_faq.py                # Ingest FAQ → ChromaDB + BM25
├── eval_chatbot.py              # Evaluasi recall chatbot
├── requirements.txt             # Dependensi dashboard
├── .env.example                 # Template env dashboard
├── .env.chatbot.example         # Template env chatbot service
└── docker-compose.yml           # Alternatif deploy via Docker
```

---

## Setup Dari Awal (Fresh Install)

Ikuti langkah-langkah di bawah secara berurutan.

### Langkah 1 — Clone & Persiapan Python

```bash
git clone <repo-url>
cd sistem_deteksi_kebakaran

# Python 3.10–3.12 (disarankan 3.11)
python --version   # pastikan >= 3.10

# Buat virtual environment utama
python -m venv venv

# Aktivasi
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Linux/WSL2:
source venv/bin/activate
```

### Langkah 2 — Install Dependensi Dashboard

```bash
pip install -r requirements.txt
```

Untuk fitur kamera RTSP (opsional):
```bash
pip install opencv-python-headless
```

### Langkah 3 — Install Dependensi Chatbot Service

```bash
pip install -r chatbot_service/requirements.txt
```

### Langkah 4 — Download Model AI

Model AI tidak disertakan di repo karena ukurannya besar.

#### 4a. Model Sensor & YOLO (wajib)

| File | Taruh di | Keterangan |
|------|----------|------------|
| `best.pt` | `models/` | YOLOv11 deteksi api & asap |
| `fire_detection_rf.pkl` | `models/` | XGBoost sensor prediction |
| `scaler.pkl` | `models/` | StandardScaler fitur sensor |
| `lstm_anomaly.keras` | `models/` | LSTM autoencoder anomaly |
| `lstm_scaler.pkl` | `models/` | Scaler LSTM |

#### 4b. Model AWQ untuk vLLM (wajib untuk chatbot)

Model ini perlu digenerate sendiri (~30-40 menit, sekali jalan):

```bash
# Buat venv TERPISAH khusus untuk quantize — jangan campur dengan venv utama
python -m venv venv_awq

# Windows:
.\venv_awq\Scripts\Activate.ps1
# Linux/WSL2:
source venv_awq/bin/activate

pip install -r scripts/requirements_awq.txt

# Download model base dari HuggingFace (~6.5 GB)
python scripts/download_base_model.py

# Quantize ke AWQ (~30-40 menit, output ~2 GB di models/qwen2.5-3b-base-awq/)
python scripts/quantize_to_awq.py

deactivate
# venv_awq bisa dihapus setelah quantize selesai
```

> **Catatan:** Proses quantize butuh NVIDIA GPU + CUDA. Jalankan di mesin yang sama atau salin folder `models/qwen2.5-3b-base-awq/` ke server target.

### Langkah 5 — Setup RAG Knowledge Base

RAG menggunakan ChromaDB (vector DB) + BM25 (keyword search). Jalankan sekali saat pertama kali, atau ulang jika dokumen berubah.

```bash
# Aktifkan venv utama dulu
# Windows: .\venv\Scripts\Activate.ps1
# Linux:   source venv/bin/activate

# Download embedding model (~440 MB, sekali jalan)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base'); print('OK')"

# Ingest PDF panduan K3 → ChromaDB + BM25 (PDF ada di docs/)
python ingest_pdf.py

# Ingest FAQ markdown → merge ke BM25 yang sama
python ingest_faq.py
```

> Jika ganti `EMBEDDING_MODEL_NAME`, wajib hapus `chroma_db_native/` dan `models/bm25_index.pkl` lalu ulangi ingest.

Untuk memakai re-ranker (opsional, +568 MB RAM, akurasi lebih baik):
```bash
python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-v2-m3'); print('OK')"
```

### Langkah 6 — Konfigurasi Environment

#### 6a. Dashboard (`.env`)

```bash
cp .env.example .env
```

Edit `.env`:

```ini
# WAJIB diisi:
SECRET_KEY=ganti-dengan-string-acak-panjang
TELEGRAM_TOKEN=your_bot_token
CHAT_ID=your_chat_id

# API key internal (dipakai dashboard ↔ chatbot service)
DASHBOARD_API_KEY=ganti-dengan-string-acak

# Opsional (nilai default sudah cukup):
# EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-base
# RERANKER_MODEL_NAME=BAAI/bge-reranker-v2-m3
# CHATBOT_SERVICE_URL=http://localhost:8001
```

#### 6b. Chatbot Service (`.env.chatbot`)

```bash
cp .env.chatbot.example .env.chatbot
```

Edit `.env.chatbot`:

```ini
VLLM_BASE_URL=http://localhost:8002/v1
VLLM_API_KEY=EMPTY
CHATBOT_MODEL_NAME=qwen-k3

DASHBOARD_BASE_URL=http://localhost:8000
DASHBOARD_API_KEY=ganti-dengan-string-yang-sama-dengan-dashboard

CHATBOT_PORT=8001
```

> **Penting:** `DASHBOARD_API_KEY` di `.env` dan `.env.chatbot` harus identik.

---

## Menjalankan Sistem

### Pilihan A — Linux / WSL2 (Rekomendasi)

Satu perintah untuk start semua service sekaligus:

```bash
# Dari root proyek (venv sudah aktif)
bash scripts/start_all.sh
```

Sistem akan start berurutan: **vLLM → chatbot service → dashboard**.

Buka browser: **http://localhost:8000**

Untuk stop:
```bash
bash scripts/stop_all.sh
```

Monitor log real-time:
```bash
tail -f logs/vllm.log logs/chatbot.log logs/dashboard.log
```

---

### Pilihan B — Windows (PowerShell + WSL2)

vLLM tidak support Windows native — wajib pakai WSL2 untuk vLLM. Dashboard dan chatbot service tetap jalan di Windows Python biasa.

#### Persiapan WSL2 (sekali jalan)

1. **Install WSL2** (jika belum):
   ```powershell
   wsl --install
   # Restart, lalu set Ubuntu sebagai default
   wsl --set-default Ubuntu
   ```

2. **Setup Python di WSL2:**
   ```bash
   # Di dalam WSL2 terminal
   sudo apt-get update
   sudo apt-get install -y python3-pip python3.12-venv
   python3 -m venv ~/venv_vllm
   curl -sS https://bootstrap.pypa.io/get-pip.py | ~/venv_vllm/bin/python3
   ~/venv_vllm/bin/pip install vllm
   ```

3. **Install CUDA toolkit & compiler di WSL2** (untuk FlashInfer JIT):
   ```bash
   # Di dalam WSL2 terminal (buka langsung dari Start Menu, bukan PowerShell)
   sudo apt-get install -y nvidia-cuda-toolkit build-essential
   nvcc --version   # verifikasi nvcc
   c++ --version    # verifikasi g++ (linker CUDA extension)
   ```

4. **Salin model AWQ ke lokasi yang bisa diakses WSL2:**
   Model di `D:\...\models\qwen2.5-3b-base-awq\` otomatis terbaca oleh WSL2 via `/mnt/d/...` — tidak perlu disalin.

#### Menjalankan Service

Buka **3 terminal terpisah** di Windows:

**Terminal 1 — vLLM (via WSL2):**
```powershell
cd D:\sem 6\PBL sem 6\SDK\sistem_deteksi_kebakaran
.\scripts\start_vllm_wsl.ps1
```
Tunggu sampai muncul:
```
INFO:     Uvicorn running on http://0.0.0.0:8002
```

**Terminal 2 — Chatbot Service (Windows Python):**
```powershell
cd D:\sem 6\PBL sem 6\SDK\sistem_deteksi_kebakaran
.\venv\Scripts\Activate.ps1
uvicorn chatbot_service.main:app --host 0.0.0.0 --port 8001 --env-file .env.chatbot
```

**Terminal 3 — Dashboard (Windows Python):**
```powershell
cd D:\sem 6\PBL sem 6\SDK\sistem_deteksi_kebakaran
.\venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8000
```

Buka browser: **http://localhost:8000**

---

### Pilihan C — Docker Compose (Alternatif)

```bash
# Pastikan NVIDIA Container Toolkit sudah terinstall
docker compose up -d

# Cek status
docker compose ps
docker compose logs -f

# Stop
docker compose down
```

> Docker Compose menggunakan image vLLM resmi dari NVIDIA. Membutuhkan Docker Engine 20.10+ dengan NVIDIA GPU support.

---

## Verifikasi Sistem Berjalan

### Smoke Test Otomatis

```bash
# Jalankan setelah semua service up (Linux/WSL2)
bash scripts/smoke_test_e2e.sh
```

Ekspektasi output:
```
=== Smoke Test E2E ===
[T1] vLLM running...
  PASS: vLLM model registered as qwen-k3
[T2] Chatbot LLM connected...
  PASS: Chatbot reports llm:true
[T3] Dashboard proxy reachable...
  PASS: Dashboard proxy available:true
[T4a] Smalltalk response...
  PASS: Smalltalk pendek (X kata)
[T4b] Detail K3 response...
  PASS: Detail K3 panjang (X kata)
[T5] Circuit breaker...
  PASS: Circuit breaker open — HTTP 503 dalam Xms
=== Result: 6 passed, 0 failed ===
```

### Cek Manual (curl)

```bash
# Health check semua service
curl http://localhost:8002/v1/models          # vLLM
curl http://localhost:8001/health             # chatbot service
curl http://localhost:8000/api/chat/health    # dashboard proxy

# Test chat
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"pertanyaan": "apa prosedur evakuasi kebakaran?"}'
```

### Monitor GPU

```bash
# Linux/WSL2
watch -n 1 nvidia-smi

# Windows PowerShell
while ($true) { nvidia-smi; Start-Sleep 1; Clear-Host }
```

Target VRAM saat semua service jalan:
- vLLM: ~2.7 GB (45% dari 6 GB)
- Dashboard (YOLO + LSTM): ~1.2 GB (20% dari 6 GB)
- Total: < 4.5 GB → headroom ~1.5 GB

---

## Konfigurasi ESP32

### Wiring Sensor

| Sensor | GPIO | Gas Target | Supply |
|--------|------|------------|--------|
| MQ-4 | GPIO32 | Metana (CH₄) | 5V |
| MQ-5 | GPIO33 | LPG | 5V |
| MQ-135 | GPIO34 | Kualitas Udara | 5V |
| MQ-2 | GPIO35 | Gas Mudah Terbakar | 5V |
| MQ-7 | GPIO36 | Karbon Monoksida | 5V |
| MQ-3 | GPIO39 | Alkohol | 5V |

ADC ESP32: 12-bit (0–4095), tegangan referensi 3.3V. Supply sensor 5V, pin ADC dibaca 3.3V (gunakan resistor pembagi jika perlu).

### Upload Firmware

1. Buka `esp32/fire_sensor/fire_sensor.ino` di **Arduino IDE 2.x**.
2. Install board: **ESP32 Dev Module** via Board Manager.
3. Install library: **ArduinoJson**, **Preferences** via Library Manager.
4. Pilih port COM yang benar.
5. Upload firmware.

### Konfigurasi via Captive Portal

Pertama kali atau setelah reset:

1. ESP32 broadcast WiFi AP: **FireSensor_XXXX** (tanpa password).
2. Hubungkan ke AP tersebut — browser otomatis buka halaman konfigurasi.
3. Isi:
   - **WiFi SSID** dan **Password**
   - **Server URL**: `http://<ip-server>:8000` (gunakan IP LAN, bukan localhost)
   - **Camera ID**: nama unik untuk ESP32 ini (contoh: `esp32-lab-a`)
4. Klik **Save** → ESP32 restart dan mulai kirim data ke server.

**Reset konfigurasi:** Tahan tombol **BOOT** 5 detik saat ESP32 menyala.

---

## Detail Konfigurasi Lanjutan

### Environment Variables Lengkap

#### `.env` (Dashboard)

| Variable | Default | Keterangan |
|----------|---------|------------|
| `SECRET_KEY` | — | **WAJIB** — JWT signing key |
| `TELEGRAM_TOKEN` | — | Token bot Telegram |
| `CHAT_ID` | — | Chat ID Telegram tujuan notifikasi |
| `DASHBOARD_API_KEY` | `""` | API key internal (dashboard ↔ chatbot) |
| `CHATBOT_SERVICE_URL` | `http://localhost:8001` | URL chatbot service |
| `CHATBOT_TIMEOUT` | `120` | Timeout request ke chatbot (detik) |
| `EMBEDDING_MODEL_NAME` | `intfloat/multilingual-e5-base` | Model embedding RAG |
| `RERANKER_MODEL_NAME` | `""` | Model re-ranker (kosong = disable) |
| `RAG_BM25_WEIGHT` | `0.4` | Bobot BM25 dalam hybrid search |
| `RAG_DENSE_WEIGHT` | `0.6` | Bobot dense embedding |
| `ENVIRONMENT` | `development` | Set ke `production` untuk mode produksi |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Host yang diizinkan (production mode) |
| `ANTHROPIC_API_KEY` | — | Opsional — hanya untuk generate_synthetic.py |

#### `.env.chatbot` (Chatbot Service)

| Variable | Default | Keterangan |
|----------|---------|------------|
| `VLLM_BASE_URL` | `http://localhost:8002/v1` | URL vLLM server |
| `VLLM_API_KEY` | `EMPTY` | API key vLLM (default tidak butuh key) |
| `CHATBOT_MODEL_NAME` | `qwen-k3` | Nama model yang didaftarkan di vLLM |
| `DASHBOARD_BASE_URL` | `http://localhost:8000` | URL dashboard untuk tool calling |
| `DASHBOARD_API_KEY` | `""` | Harus sama dengan dashboard |
| `CHATBOT_PORT` | `8001` | Port chatbot service |
| `CHROMA_DB_PATH` | `./chroma_db_native` | Path ChromaDB |
| `BM25_INDEX_PATH` | `models/bm25_index.pkl` | Path index BM25 |

### Parameter vLLM (RTX 3060 6 GB)

Konfigurasi di `scripts/start_vllm.sh` (Linux) atau `scripts/start_vllm_wsl.ps1` (Windows):

```bash
--gpu-memory-utilization 0.45   # 2.7 GB dari 6 GB untuk vLLM
--max-model-len 2048             # Context window
--max-num-seqs 4                 # Max request concurrent
--enable-prefix-caching          # Cache system prompt (percepat request ke-2+)
--enforce-eager                  # Disable CUDA graph capture (hemat VRAM)
--quantization awq               # Quantization format
--dtype float16
```

Jika GPU OOM:
1. Kurangi `--gpu-memory-utilization` ke `0.40`
2. Kurangi `--max-model-len` ke `1536`
3. Jika masih OOM: pindah YOLO ke CPU — edit `app/ai_engine.py`, tambahkan `device="cpu"` saat load model YOLO

---

## Deployment Produksi

### Checklist Sebelum Production

- [ ] `SECRET_KEY` diset ke nilai acak panjang (bukan default)
- [ ] `DASHBOARD_API_KEY` diset dan identik di `.env` dan `.env.chatbot`
- [ ] `TELEGRAM_TOKEN` dan `CHAT_ID` valid
- [ ] `ENVIRONMENT=production` di `.env`
- [ ] `ALLOWED_HOSTS` diset ke domain/IP server
- [ ] Port 8000 dibuka di firewall (8001 dan 8002 internal saja)
- [ ] Model AWQ tersedia di `models/qwen2.5-3b-base-awq/`
- [ ] RAG sudah di-ingest (`chroma_db_native/` dan `models/bm25_index.pkl` ada)
- [ ] `nvidia-smi` menunjukkan GPU terdeteksi

### Menjalankan dengan Systemd (Linux Production)

Buat file service untuk setiap komponen:

```bash
# /etc/systemd/system/fire-vllm.service
[Unit]
Description=Fire Detection vLLM
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/sistem_deteksi_kebakaran
ExecStart=/bin/bash /opt/sistem_deteksi_kebakaran/scripts/start_vllm.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable fire-vllm fire-chatbot fire-dashboard
sudo systemctl start fire-vllm

# Cek status
sudo systemctl status fire-vllm
journalctl -u fire-vllm -f
```

### Reverse Proxy Nginx (Opsional)

Untuk expose hanya port 80/443 ke luar:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 120s;
    }
}
```

Port 8001 (chatbot) dan 8002 (vLLM) tidak perlu diekspos ke luar — keduanya hanya diakses internal oleh dashboard.

---

## Troubleshooting

### vLLM tidak mau start

**Error: `No module named 'vllm._C'`**
- vLLM tidak support Windows native.
- Solusi: gunakan WSL2 (Pilihan B) atau Docker.

**Error: `Could not find nvcc`**
- CUDA toolkit belum terinstall di WSL2.
- Solusi:
  ```bash
  # Di terminal WSL2 langsung (bukan PowerShell background)
  sudo apt-get update
  sudo apt-get install -y nvidia-cuda-toolkit build-essential
  nvcc --version   # cek nvcc
  c++ --version    # cek g++ (linker)
  ```

**Error: `c++: not found` / `ninja build failed` saat FlashInfer JIT**
- `nvcc` ada tapi `g++` (C++ linker) belum terinstall.
- Solusi:
  ```bash
  sudo apt-get install -y build-essential
  c++ --version   # verifikasi
  ```
- Kemudian hapus cache FlashInfer agar di-build ulang:
  ```bash
  rm -rf ~/.cache/flashinfer/
  ```

**Error: `No module named 'torch._inductor.custom_graph_pass'`**
- PyTorch versi lama (< 2.6.0). vLLM 0.21.0 butuh PyTorch ≥ 2.6.0.
- Solusi:
  ```bash
  pip install torch==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
  ```

**Error: `CUDA out of memory`**
- Solusi: kurangi `--gpu-memory-utilization` ke `0.40`, atau `--max-model-len` ke `1536`.

### Chatbot tidak merespons

**Dashboard menampilkan "Chatbot sedang offline"**
- Cek apakah chatbot service jalan: `curl http://localhost:8001/health`
- Cek apakah vLLM jalan: `curl http://localhost:8002/v1/models`
- Lihat log: `tail -f logs/chatbot.log`

**`"llm": false` di health check**
- vLLM belum ready. Tunggu beberapa menit setelah start vLLM.
- Pastikan `VLLM_BASE_URL` di `.env.chatbot` sudah benar.
- Pastikan `CHATBOT_MODEL_NAME=qwen-k3` (nama yang didaftarkan di vLLM).

### RAG tidak menemukan dokumen relevan

```bash
# Rebuild RAG dari awal
rm -rf chroma_db_native/ models/bm25_index.pkl
python ingest_pdf.py
python ingest_faq.py
```

### Sensor ESP32 tidak muncul di dashboard

- Pastikan ESP32 dan server dalam jaringan yang sama.
- Pastikan Server URL di Captive Portal menggunakan **IP LAN** (contoh: `http://192.168.1.10:8000`), bukan `localhost`.
- Cek endpoint: `curl http://localhost:8000/api/sensor/latest`

### `sudo: timed out` di WSL2

- Jangan jalankan sudo dari PowerShell background job.
- Buka terminal WSL2 langsung (klik "Ubuntu" di Start Menu atau `wsl` di terminal baru).

---

## Pengembangan & Training

### Feedback Loop

Setiap jawaban chatbot ada tombol 👍/👎 yang tersimpan ke SQLite:

```bash
# Analisis pola jawaban buruk
python scripts/analyze_feedback.py

# Export untuk review
curl http://localhost:8000/api/feedback/export > feedback_export.json
```

Loop perbaikan mingguan:
```bash
python scripts/analyze_feedback.py           # lihat pola error
# tulis koreksi ke data/corrections.jsonl
python scripts/build_training_data.py        # gabung semua sumber
# upload ke Kaggle → re-run notebook fine-tune → ganti model
```

### Fine-Tuning Chatbot

#### Qwen 2.5 3B (Rekomendasi — Kaggle)

1. Upload `models/train_chatbot/Finetune_K3_Qwen_1.5B_Kaggle.ipynb` ke Kaggle.
2. Setting: GPU T4 x2, Internet = On.
3. Tambah Secret: `HF_TOKEN` = HuggingFace token.
4. Jalankan sampai selesai.
5. Download model → salin ke `models/qwen2.5-3b-base-awq/`.

### Evaluasi Chatbot

```bash
# Server harus jalan dulu
python eval_chatbot.py

# Output: recall per-kategori di eval/results/results_<timestamp>.json
# Target: recall >= 70%
```

### Training Model Sensor

1. Kumpulkan data via `datagather/app.py` (Flask app terpisah).
2. Buka `models/train_sensor/Train_Sensor_Model.ipynb` di Google Colab.
3. Upload `dataset_sensor.csv`.
4. Download `fire_detection_rf.pkl` + `scaler.pkl` → taruh di `models/`.

---

## Konversi RAW ADC → PPM (Referensi)

Backend mengkonversi nilai ADC ESP32 ke PPM menggunakan rumus power-law dari datasheet sensor MQ:

```
Vout = (RAW_ADC / 4095) × 3.3 V
ratio = (5V - Vout) / Vout        # proporsional dengan Rs/RL
PPM   = a × ratio^b               # kurva datasheet (log-log fit)
```

| Sensor | GPIO | Gas | a | b |
|--------|------|-----|---|---|
| MQ-4 | 32 | Metana (CH₄) | 1012.7 | -2.786 |
| MQ-5 | 33 | LPG | 1000.5 | -2.186 |
| MQ-135 | 34 | Kualitas Udara | 110.47 | -2.862 |
| MQ-2 | 35 | Gas Mudah Terbakar | 574.25 | -2.222 |
| MQ-7 | 36 | CO | 99.042 | -1.518 |
| MQ-3 | 39 | Alkohol | 0.3934 | -1.504 |

Rumus di `app/ai_engine.py` dan notebook training identik untuk konsistensi.

---

## Lisensi & Kredit

Dikembangkan sebagai proyek PBL (Project Based Learning) Semester 6.

Model:
- [Qwen2.5-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct) — Alibaba Cloud
- [YOLOv11](https://github.com/ultralytics/ultralytics) — Ultralytics
- [multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base) — Microsoft
