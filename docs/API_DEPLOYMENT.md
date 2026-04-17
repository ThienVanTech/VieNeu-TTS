# VieNeu-TTS API Service - Huong dan trien khai Local

Huong dan trien khai day du he thong VieNeu-TTS API Service tren may local (khong can GPU, khong can internet sau khi setup xong).

---

## Muc luc

1. [Yeu cau he thong](#1-yeu-cau-he-thong)
2. [Cai dat tu source](#2-cai-dat-tu-source)
3. [Tai model ve may](#3-tai-model-ve-may)
4. [Cau hinh](#4-cau-hinh)
5. [Khoi chay API](#5-khoi-chay-api)
6. [Test thu API](#6-test-thu-api)
7. [Trien khai bang Docker](#7-trien-khai-bang-docker)
8. [Mo ta API chi tiet](#8-mo-ta-api-chi-tiet)
9. [Cau truc thu muc](#9-cau-truc-thu-muc)
10. [Xu ly loi thuong gap](#10-xu-ly-loi-thuong-gap)

---

## 1. Yeu cau he thong

| Thanh phan | Yeu cau toi thieu | Khuyen nghi |
|---|---|---|
| **OS** | Ubuntu 20.04+ / Windows 10+ / macOS 12+ | Ubuntu 22.04 |
| **Python** | 3.10+ | 3.12 |
| **RAM** | 4 GB | 8 GB+ |
| **CPU** | 4 cores | 8 cores+ (model chay tren CPU) |
| **Disk** | 5 GB (model + cache) | 10 GB+ |
| **ffmpeg** | Can thiet cho output MP3 | `apt install ffmpeg` |
| **espeak-ng** | Can thiet cho phonemization | `apt install espeak-ng` |

> **Luu y**: He thong nay chay hoan toan tren CPU, **khong can GPU**.

---

## 2. Cai dat tu source

### 2.1. Clone repository

```bash
git clone https://github.com/ThienVanTech/VieNeu-TTS.git
cd VieNeu-TTS
```

### 2.2. Cai dat uv (package manager)

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2.3. Cai dat dependencies

```bash
# Tao virtual environment va cai dat tat ca dependencies
uv sync

# Cai them cac package can thiet cho API service
uv pip install "fastapi[standard]" slowapi apscheduler
```

### 2.4. Cai dat system packages (Linux)

```bash
sudo apt update
sudo apt install -y ffmpeg espeak-ng libespeak-ng1 libsndfile1
```

**macOS:**
```bash
brew install ffmpeg espeak-ng libsndfile
```

**Windows:** Tai ffmpeg tu https://ffmpeg.org/download.html va them vao PATH.

---

## 3. Tai model ve may

VieNeu-TTS su dung 2 loai model: **Backbone** (GGUF) va **Codec** (ONNX). Lan dau chay, model se tu dong download tu HuggingFace Hub. Tuy nhien, de **trien khai offline hoan toan**, ban nen tai truoc.

### 3.1. Tai tu dong (khuyen nghi cho lan dau)

Chi can chay API server, model se tu download:

```bash
uv run vieneu-api
```

Model se duoc luu tai `~/.cache/huggingface/hub/`. Sau khi tai xong, ban co the ngat mang va server van hoat dong binh thuong.

### 3.2. Tai thu cong (cho moi truong offline)

```bash
# Cai dat huggingface-cli
uv pip install huggingface-hub[cli]

# Tai Backbone model (GGUF - ~600MB)
huggingface-cli download pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF \
    --local-dir ./models/backbone

# Tai Codec model (ONNX - ~50MB)
huggingface-cli download pnnbao-ump/VieNeu-Codec \
    --local-dir ./models/codec
```

Sau khi tai, cap nhat `config.yaml` de tro den duong dan local:

```yaml
api_service:
  backbone_repo: "./models/backbone"
  device: "cpu"
```

### 3.3. Cau truc thu muc model sau khi tai

```
models/
  backbone/
    vieneu-tts-v2-turbo.gguf    # Backbone model (~600MB)
    voices.json                  # Preset voices
  codec/
    vieneu_decoder.onnx          # Decoder (~50MB)
    vieneu_encoder.onnx          # Encoder (~20MB)
```

---

## 4. Cau hinh

### 4.1. Tao file .env

```bash
cp .env.example .env
```

Chinh sua `.env`:

```env
# Thong tin xac thuc API
TTS_USERNAME=admin
TTS_PASSWORD=your_secure_password_here

# Server
TTS_HOST=0.0.0.0
TTS_PORT=8000

# Rate limiting (so request toi da moi phut)
TTS_RATE_LIMIT=30/minute

# Cache
TTS_CACHE_DIR=storage/audio_cache
TTS_DB_PATH=storage/tts_cache.db
TTS_CLEANUP_DAYS=30
```

### 4.2. Cau hinh model trong config.yaml

File `config.yaml` da co san cau hinh mac dinh. Chi can chinh neu muon dung model local:

```yaml
api_service:
  # Dung HuggingFace repo (tu dong tai):
  backbone_repo: "pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF"

  # Hoac dung duong dan local:
  # backbone_repo: "./models/backbone"

  device: "cpu"

  # Cai dat tham so generation (tuong ung voi giao dien web)
  generation:
    temperature: 0.4          # Do sang tao (0.1-1.5)
    top_k: 50                 # Top-K sampling (1-200)
    max_chars_per_chunk: 256  # Do dai toi da moi doan (128-512)

  languages:
    vi:
      default_voice_id: ""      # de trong = dung voice mac dinh (voice dau tien tu voices.json)
      default_speed: 1.0
      output_format: "wav"
    en:
      default_voice_id: ""
      default_speed: 1.0
      output_format: "wav"
```

> **Luu y ve voice mac dinh**: Khi `default_voice_id` de trong, he thong se dung voice dau tien tu file `voices.json` (duoc tai kem model). Danh sach voice co the xem qua endpoint `GET /v1/tts/voices`.

> **Luu y ve tham so generation**: Cac tham so `temperature`, `top_k`, `max_chars_per_chunk` tuong ung voi cac cai dat trong giao dien Gradio web (Temperature, Max Chars per Chunk). Gia tri mac dinh da duoc toi uu cho CPU Turbo v2.

---

## 5. Khoi chay API

### 5.1. Chay truc tiep

```bash
# Su dung CLI entry point
uv run vieneu-api

# Hoac chay file truc tiep
uv run python apps/api_service.py
```

Server se khoi dong tai `http://0.0.0.0:8000`.

**Log khi khoi dong thanh cong:**
```
Loading TTS model: pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF on cpu
TTS model loaded and cached in memory
TTS worker started
APScheduler started (daily cache cleanup at 00:00)
Starting VieNeu-TTS API on 0.0.0.0:8000
```

> **Quan trong**: Model duoc load 1 lan duy nhat khi khoi dong server va giu trong RAM. Moi request sau do deu dung model da cache, khong load lai.

### 5.2. Chay voi bien moi truong tuy chinh

```bash
TTS_USERNAME=myuser TTS_PASSWORD=mypass TTS_PORT=9000 uv run vieneu-api
```

---

## 6. Test thu API

### 6.1. Kiem tra Health

```bash
curl http://localhost:8000/health
```

Ket qua:
```json
{
  "status": "ok",
  "model_loaded": true,
  "queue_size": 0,
  "cache_db": "storage/tts_cache.db",
  "uptime_seconds": 42.5
}
```

### 6.2. Tao giong noi (WAV)

```bash
curl -X POST http://localhost:8000/v1/tts/synthesize \
  -u admin:admin \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Xin chao, day la bai test giong noi tieng Viet.",
    "lang": "vi",
    "speed": 1.0,
    "output_format": "wav",
    "is_load_from_cache": true
  }' \
  --output output.wav
```

### 6.3. Tao giong noi (MP3, toc do nhanh)

```bash
curl -X POST http://localhost:8000/v1/tts/synthesize \
  -u admin:admin \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Chao buoi sang!",
    "lang": "vi",
    "speed": 1.5,
    "output_format": "mp3",
    "is_load_from_cache": false
  }' \
  --output output.mp3
```

### 6.4. Tao giong noi tieng Anh

```bash
curl -X POST http://localhost:8000/v1/tts/synthesize \
  -u admin:admin \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello, this is a test of the English voice.",
    "lang": "en",
    "speed": 1.0,
    "output_format": "wav",
    "is_load_from_cache": true
  }' \
  --output output_en.wav
```

### 6.5. Xem danh sach voices

```bash
curl -u admin:admin http://localhost:8000/v1/tts/voices
```

### 6.6. Test bang Postman

Import file `tests/postman_collection.json` vao Postman. Cau hinh bien moi truong:

| Variable | Value |
|---|---|
| `base_url` | `http://localhost:8000` |
| `username` | `admin` |
| `password` | `admin` |

---

## 7. Trien khai bang Docker

### 7.1. Chuan bi model local (bat buoc cho moi truong khong co mang)

Truoc khi build Docker image, tai model ve may:

```bash
# Cai dat huggingface-cli
uv pip install huggingface-hub[cli]

# Tai Backbone model (GGUF - ~600MB)
huggingface-cli download pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF \
    --local-dir ./models/backbone

# Tai Codec model (ONNX - ~50MB)
huggingface-cli download pnnbao-ump/VieNeu-Codec \
    --local-dir ./models/codec
```

Sau khi tai xong, cau truc thu muc:

```
models/
  backbone/
    vieneu-tts-v2-turbo.gguf    # Backbone model (~600MB)
    voices.json                  # Preset voices
  codec/
    vieneu_decoder.onnx          # Decoder (~50MB)
    vieneu_encoder.onnx          # Encoder (~20MB)
```

### 7.2. Cau hinh .env cho Docker

```bash
cp .env.example .env
```

Chinh sua `.env`:

```env
TTS_USERNAME=admin
TTS_PASSWORD=your_secure_password_here

# Su dung model local (bat buoc khi khong co mang)
TTS_BACKBONE_REPO=/app/models/backbone

# Default voice (de trong = dung voice dau tien tu voices.json)
# TTS_DEFAULT_VOICE=

# Generation parameters
TTS_TEMPERATURE=0.4
TTS_MAX_CHARS_PER_CHUNK=256
```

### 7.3. Build image

```bash
docker compose -f docker/docker-compose.api.yml build
```

> **Luu y**: Lenh build se tu dong copy thu muc `models/` vao image. Neu ban chua tai model, container se tu dong download tu HuggingFace khi khoi dong (can mang).

### 7.4. Chay container

```bash
docker compose -f docker/docker-compose.api.yml up -d
```

### 7.5. Kiem tra logs

```bash
docker logs -f vieneu-tts-api
```

### 7.6. Dung container

```bash
docker compose -f docker/docker-compose.api.yml down
```

### 7.7. Volume mapping

| Host | Container | Mo ta |
|---|---|---|
| `./storage/` | `/app/storage` | Audio cache + SQLite DB (bind mount, truy cap truc tiep tu host) |
| `./models/` | `/app/models` | Model files local (bind mount) |
| Docker volume `huggingface_cache` | `/root/.cache/huggingface` | HuggingFace cache (chi khi download online) |

> **Bind mount**: Thu muc `storage/` duoc mount truc tiep tu host, ban co the truy cap file audio va database tu ben ngoai container.

### 7.8. Chay kem Gradio Web UI (so sanh ket qua)

De chay Gradio web UI song song voi API service (can GPU):

```bash
docker compose -f docker/docker-compose.api.yml --profile web up -d
```

Web UI se co tai `http://localhost:7860`. Gradio cung co trang API docs tai:
```
http://localhost:7860/?view=api
```

---

## 8. Mo ta API chi tiet

### POST /v1/tts/synthesize

Tao giong noi tu van ban.

**Authentication:** Basic Auth (bat buoc)

**Request body (JSON):**

| Truong | Kieu | Bat buoc | Mac dinh | Mo ta |
|---|---|---|---|---|
| `text` | string | Co | - | Van ban can chuyen thanh giong noi (1-5000 ky tu) |
| `lang` | string | Khong | `"vi"` | Ngon ngu: `"vi"` hoac `"en"` |
| `speed` | float | Khong | `1.0` | Toc do doc: 0.5 (cham) den 2.0 (nhanh). Audio duoc xu ly post-processing sau khi gen. |
| `voice_id` | string | Khong | `null` | ID cua giong doc. De null = dung voice mac dinh |
| `output_format` | string | Khong | `"wav"` | Dinh dang output: `"wav"` hoac `"mp3"` |
| `is_load_from_cache` | bool | Khong | `true` | `true`: tra ve file da cache neu co. `false`: luon tao moi, thay the file cache cu. |
| `temperature` | float | Khong | `0.4` | Do sang tao (0.1-1.5). Cao = da dang nhung de loi. Thap = on dinh. |
| `top_k` | int | Khong | `50` | Top-K sampling (1-200). |
| `max_chars_per_chunk` | int | Khong | `256` | Do dai toi da moi doan xu ly (128-512). |

**Response:**
- Thanh cong: File audio (WAV hoac MP3) voi header `X-Cache: HIT` hoac `X-Cache: MISS`
- Loi: JSON `{"detail": "..."}` voi HTTP status code tuong ung

**Vi du request:**
```json
{
  "text": "Xin chao Viet Nam",
  "lang": "vi",
  "speed": 1.2,
  "voice_id": null,
  "output_format": "wav",
  "is_load_from_cache": true,
  "temperature": 0.4,
  "top_k": 50,
  "max_chars_per_chunk": 256
}
```

### GET /health

Kiem tra trang thai server (khong can xac thuc).

**Response:**
```json
{
  "status": "ok",
  "model_loaded": true,
  "queue_size": 0,
  "cache_db": "storage/tts_cache.db",
  "uptime_seconds": 120.5
}
```

### GET /v1/tts/voices

Danh sach cac giong doc co san (can xac thuc).

**Response:**
```json
[
  {"id": "xuan_vinh", "description": "Xuan Vinh - Nam Bac"},
  {"id": "ngoc_huyen", "description": "Ngoc Huyen - Nu Bac"}
]
```

---

## 9. Cau truc thu muc

```
VieNeu-TTS/
  apps/
    api_service.py          # FastAPI app chinh
    tts_cache.py            # SQLite cache layer
    tts_worker.py           # Async queue + singleton worker + speed post-processing
    web_stream.py           # (Co san) Gradio streaming app
  config.yaml               # Cau hinh chung
  docker/
    Dockerfile.api           # Dockerfile CPU-only cho API service
    docker-compose.api.yml   # Docker Compose cho API
  storage/                   # (Tu dong tao khi chay)
    audio_cache/             # File audio da gen
    tts_cache.db             # SQLite database
  models/                    # (Tuy chon) Model local
    backbone/
    codec/
  tests/
    test_api_service.py      # Unit tests cho API
    postman_collection.json  # Postman test collection
  .env                       # Bien moi truong (khong commit)
  .env.example               # Mau bien moi truong
```

---

## 10. Xu ly loi thuong gap

### Model download bi loi mang

```
ConnectionError: Could not reach HuggingFace Hub
```

**Giai phap:** Tai model thu cong (xem muc 3.2), sau do tro `backbone_repo` trong `config.yaml` den thu muc local.

### ffmpeg not found (khi dung output MP3)

```
RuntimeError: ffmpeg failed: ...
```

**Giai phap:**
```bash
# Linux
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows: tai tu https://ffmpeg.org va them vao PATH
```

### espeak-ng not found

```
RuntimeError: espeak-ng library not found
```

**Giai phap:**
```bash
sudo apt install espeak-ng libespeak-ng1

# Hoac set bien moi truong
export PHONEMIZER_ESPEAK_LIBRARY=/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1
```

### Port bi chiem

```
OSError: [Errno 98] Address already in use
```

**Giai phap:** Doi port trong `.env`:
```env
TTS_PORT=9000
```

### RAM khong du

Model GGUF can khoang 1-2GB RAM. Neu may co it hon 4GB RAM, co the gap loi OOM.

**Giai phap:** Dung model Q4 (nho hon) thay vi model mac dinh:
```yaml
api_service:
  backbone_repo: "pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf"
```

---

*Tai lieu nay duoc tao tu dong boi Copilot cho du an VieNeu-TTS v2.4.3*
