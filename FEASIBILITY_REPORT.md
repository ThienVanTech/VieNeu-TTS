# BAO CAO DANH GIA TINH KHA THI: TRIEN KHAI NGHI-TTS API SERVICE TREN VIENEU-TTS

## 1. Tong quan

Bao cao nay danh gia tinh kha thi cua viec su dung codebase **VieNeu-TTS** (v2.4.3) de trien khai mot **API Service** theo dac ta ky thuat cua **NGHI-TTS API Service**. Muc tieu la xac dinh nhung gi da co san, nhung gi can bo sung, va muc do kho khan cho tung thanh phan.

---

## 2. Bang tong hop danh gia

| # | Yeu cau NGHI-TTS | Trang thai trong VieNeu-TTS | Muc do kha thi | Ghi chu |
|---|---|---|---|---|
| 2.1 | FastAPI Framework | **DA CO** | **CAO** | `apps/web_stream.py` da dung FastAPI + Uvicorn |
| 2.1 | POST /v1/tts/synthesize | **CAN BO SUNG** | **CAO** | Co san endpoint `/stream`, chi can tao them endpoint moi theo dung spec |
| 2.1 | Input JSON (text, lang, speed) | **CAN BO SUNG** | **CAO** | Hien tai chi nhan `text` va `voice_id`, can them `lang` va `speed` |
| 2.1 | Output audio file (Streaming/File Response) | **DA CO** | **CAO** | `StreamingResponse` WAV da duoc implement trong `web_stream.py` |
| 2.1 | Basic Authentication | **CHUA CO** | **CAO** | De them bang `fastapi.security.HTTPBasic`, doc tu ENV |
| 2.2 | config.yaml | **DA CO** | **CAO** | Da co `config.yaml` voi backbone_configs, codec_configs |
| 2.2 | Da ngon ngu (vi, en) | **DA CO** | **CAO** | Turbo v2 ho tro bilingual English-Vietnamese qua `sea-g2p` |
| 2.2 | model_path, voice_id, speed, format | **CAN BO SUNG** | **TRUNG BINH** | Da co model_path va voice_id; speed va output_format can them |
| 2.3 | asyncio.Queue (Task Queueing) | **CHUA CO** | **CAO** | De implement, VieNeu da dung asyncio/FastAPI |
| 2.3 | Singleton Worker Pattern | **CHUA CO** | **CAO** | TurboVieNeuTTS da la single-instance, chi can wrap bang queue |
| 2.3 | FIFO Processing | **CHUA CO** | **CAO** | asyncio.Queue mac dinh la FIFO |
| 2.4 | SQLite Caching (SQLAlchemy/aiosqlite) | **CHUA CO** | **CAO** | Can them dependency va implement |
| 2.4 | Hash-based cache lookup | **CHUA CO** | **CAO** | Logic don gian: hash(text+lang+speed) |
| 2.4 | last_used tracking | **CHUA CO** | **CAO** | Them truong vao DB schema |
| 2.5 | Auto-Cleanup (APScheduler) | **CHUA CO** | **CAO** | Can them APScheduler dependency |
| 3.1 | Docker (python:3.10-slim) | **DA CO (khac base)** | **CAO** | Da co Dockerfile, nhung dang dung nvidia/cuda base. Can tao them Dockerfile CPU-only |
| 3.1 | ffmpeg, libsndfile1 | **CAN BO SUNG** | **CAO** | Chua cai trong Dockerfile hien tai, de them |
| 3.1 | Volume mapping (models, storage) | **DA CO** | **CAO** | Da co volume mapping trong docker-compose |
| 3.2 | Postman Collection | **CHUA CO** | **CAO** | Can tao file JSON |
| + | Health Check (GET /health) | **CHUA CO** | **CAO** | 1 endpoint don gian |
| + | Logging (loguru) | **DA CO (dung logging)** | **CAO** | Dang dung `logging` module, chuyen sang `loguru` de |
| + | Rate Limiting | **CHUA CO** | **CAO** | Dung `slowapi` hoac middleware |

---

## 3. Phan tich chi tiet tung thanh phan

### 3.1. API & Authentication

**Hien trang:**
- `apps/web_stream.py` da la mot FastAPI app hoan chinh voi Uvicorn.
- Co cac endpoint: `GET /`, `GET /models`, `POST /set_model`, `GET /voices`, `GET /stream`, `POST /stream`, `POST /extract_url`.
- Chua co authentication.

**De xuat:**
- Tao file moi `apps/api_service.py` (hoac mo rong `web_stream.py`) voi endpoint `POST /v1/tts/synthesize`.
- Them `HTTPBasic` authentication doc `TTS_USERNAME` va `TTS_PASSWORD` tu ENV.
- **Do kho: THAP** - Chi can 20-30 dong code.

### 3.2. Quan ly cau hinh (config.yaml)

**Hien trang:**
- `config.yaml` da co cau truc tot voi `backbone_configs` va `codec_configs`.
- Moi backbone da co: `repo`, `supports_streaming`, `description`.

**Can bo sung them cho moi ngon ngu:**
```yaml
languages:
  vi:
    backbone: "VieNeu-TTS-v2-Turbo (CPU)"
    voice_id: "xuan_vinh"      # default voice
    default_speed: 1.0
    output_format: "wav"
  en:
    backbone: "VieNeu-TTS-v2-Turbo (CPU)"
    voice_id: "xuan_vinh"
    default_speed: 1.0
    output_format: "wav"
```

**Luu y:** VieNeu Turbo v2 da ho tro bilingual (vi + en) trong cung 1 model, nen khong can model rieng cho tung ngon ngu. Tuy nhien, `speed` parameter hien chua duoc TTS engine ho tro truc tiep - can implement post-processing (thay doi toc do audio sau khi synthesize).

**Do kho: THAP-TRUNG BINH**

### 3.3. Co che Hang doi (Task Queueing)

**Hien trang:**
- `TurboVieNeuTTS` va `VieNeuTTS` deu la single-instance, xu ly tuyen tinh.
- `web_stream.py` dung global `tts` instance nhung **KHONG** co queue, nghia la nhieu request dong thoi se gay race condition.

**De xuat:**
```
TTSWorker (Singleton):
  - asyncio.Queue() nhan request
  - 1 background task duy nhat lay tu queue va goi tts.infer()
  - Moi request duoc gan 1 asyncio.Future de await ket qua
```

**Do kho: TRUNG BINH** - Can hieu ro asyncio pattern. Khoang 50-80 dong code.

### 3.4. Caching & Database (SQLite)

**Hien trang:**
- **CHUA CO** bat ky co che caching nao. Moi request deu synthesize tu dau.

**De xuat:**
- Them dependency: `sqlalchemy`, `aiosqlite`
- Schema:
  ```
  Table: tts_cache
    id: INTEGER PRIMARY KEY
    hash: TEXT UNIQUE (SHA256 cua text+lang+speed)
    text: TEXT
    lang: TEXT
    speed: REAL
    file_path: TEXT
    created_at: DATETIME
    last_used: DATETIME
  ```
- Logic:
  1. Request den -> tinh hash
  2. Query DB: co hash + file ton tai? -> tra file, update last_used
  3. Khong co -> dua vao queue -> synthesize -> luu file -> insert DB -> tra file

**Do kho: TRUNG BINH** - Khoang 100-150 dong code.

### 3.5. Auto-Cleanup (APScheduler)

**Hien trang:** CHUA CO.

**De xuat:**
- Them dependency: `apscheduler`
- Tao cron job chay 00:00 hang ngay
- Logic: SELECT * FROM tts_cache WHERE last_used < now() - 30 days -> xoa file + xoa record

**Do kho: THAP** - Khoang 20-30 dong code.

### 3.6. Docker

**Hien trang:**
- Da co 3 Dockerfile: `Dockerfile.gpu` (dev/prod), `Dockerfile.serve` (LMDeploy remote).
- **CHUA CO** Dockerfile cho CPU-only API service.

**De xuat:**
- Tao `docker/Dockerfile.api` moi dua tren `python:3.10-slim` hoac `python:3.12-slim`.
- Cai dat: `ffmpeg`, `libsndfile1`, `espeak-ng`, va cac Python packages.
- Volume:
  - `./models:/app/models` (TTS models)
  - `./storage:/app/storage` (audio cache + SQLite DB)

**Luu y quan trong:** VieNeu Turbo v2 dung **GGUF** format (qua `llama-cpp-python`) va **ONNX** codec, ca hai deu chay duoc tren CPU ma khong can GPU. Day la diem manh lon so voi yeu cau NGHI-TTS "chay tren CPU".

**Do kho: TRUNG BINH**

### 3.7. Testing (Postman Collection)

**Hien trang:** Da co unit tests (pytest) nhung chua co Postman collection.

**De xuat:** Tao file `tests/postman_collection.json` voi:
- `POST /v1/tts/synthesize` (voi Basic Auth)
- `GET /health`
- Variables: `{{base_url}}`, `{{username}}`, `{{password}}`

**Do kho: THAP**

---

## 4. Danh gia Engine TTS: VieNeu vs NGHI-TTS

### 4.1. VieNeu Turbo v2 (Ung vien chinh cho CPU deployment)

| Tieu chi | VieNeu Turbo v2 | Ghi chu |
|---|---|---|
| **Format** | GGUF (backbone) + ONNX (codec) | Toi uu cho CPU |
| **Device** | CPU / Edge | **DAP UNG** |
| **Bilingual** | Vietnamese + English | **DAP UNG** (code-switching tu nhien) |
| **Voice Cloning** | Co (3-5 giay audio) | **VUOT YEU CAU** |
| **Streaming** | Co | **DAP UNG** |
| **Sample Rate** | 24 kHz | Cao |
| **Chat luong** | Trung binh-kha (thap hon GPU mode) | Cau ngan < 5 tu co the khong on dinh |
| **Toc do** | Nhanh tren CPU | Can benchmark cu the |

### 4.2. Han che cua VieNeu Turbo v2 so voi yeu cau

1. **Speed control**: VieNeu hien **KHONG** co tham so `speed` truc tiep. Can implement post-processing (time-stretching) bang `librosa` hoac `pydub`.

2. **Output format**: Mac dinh la WAV 24kHz. De ho tro MP3, can them `pydub` hoac `ffmpeg` de convert.

3. **Cau ngan**: VieNeu Turbo v2 co van de voi cau ngan < 5 tu. Can xu ly edge case nay (padding text, hoac reject).

4. **Model files**: VieNeu tu dong download model tu HuggingFace Hub. Neu muon offline hoan toan, can pre-download va mount volume.

---

## 5. Cac thanh phan bo sung (Goi y chuyen gia)

### 5.1. Health Check Endpoint

```
GET /health -> {"status": "ok", "model_loaded": true, "queue_size": 0}
```
**Do kho: THAP** - 5 dong code.

### 5.2. Logging

**Hien trang:** Da dung `logging` module (logger = logging.getLogger("Vieneu")).
**De xuat:** Chuyen sang `loguru` de co structured logging, rotation, va format dep hon.
**Do kho: THAP**

### 5.3. Rate Limiting

**De xuat:** Dung `slowapi` (wrapper cho `limits` library) tich hop vao FastAPI.
**Do kho: THAP** - 10-15 dong code.

---

## 6. Uoc luong cong viec

| Hang muc | Do kho | Uoc luong |
|---|---|---|
| Tao `apps/api_service.py` (FastAPI endpoint + Auth) | THAP | 2-3 gio |
| Mo rong `config.yaml` | THAP | 30 phut |
| Implement Task Queue (Singleton Worker) | TRUNG BINH | 3-4 gio |
| Implement SQLite Caching | TRUNG BINH | 4-5 gio |
| Auto-Cleanup (APScheduler) | THAP | 1-2 gio |
| Speed control (post-processing) | TRUNG BINH | 2-3 gio |
| MP3 output support | THAP | 1 gio |
| Dockerfile CPU-only | TRUNG BINH | 2-3 gio |
| Health Check, Logging, Rate Limiting | THAP | 1-2 gio |
| Postman Collection | THAP | 1 gio |
| Testing & Integration | TRUNG BINH | 3-4 gio |
| **TONG** | | **~20-28 gio** |

---

## 7. Ket luan

### VieNeu-TTS CO THE dap ung duoc yeu cau cua NGHI-TTS API Service.

**Ly do:**

1. **Engine TTS da san sang**: VieNeu Turbo v2 chay tren CPU voi format GGUF+ONNX, ho tro bilingual (vi+en), voice cloning, va streaming. Day chinh xac la nhung gi NGHI-TTS can.

2. **FastAPI da co san**: `apps/web_stream.py` da la mot FastAPI app hoat dong, chi can mo rong them cac thanh phan moi.

3. **Infrastructure da co**: Docker setup, model management (HuggingFace Hub), voice presets, text normalization, phonemization - tat ca da duoc implement va test.

4. **Nhung gi can bo sung** (Queue, Cache, Auth, Cleanup) deu la cac pattern pho bien trong FastAPI, de implement va co nhieu thu vien ho tro.

**Rui ro:**

1. **Chat luong audio cua Turbo v2 thap hon GPU mode** - Neu yeu cau chat luong cao, can GPU (nhung dieu nay trai voi yeu cau "chay tren CPU" cua NGHI-TTS).

2. **Speed control chua co san** - Can implement post-processing, co the anh huong chat luong audio.

3. **Cau ngan < 5 tu** co the khong on dinh voi Turbo v2.

**Khuyen nghi:** Tien hanh trien khai. Bat dau voi Turbo v2 (CPU) lam engine chinh, bo sung cac thanh phan API theo thu tu uu tien: Auth -> Queue -> Cache -> Cleanup -> Docker.

---

## 8. Kien truc de xuat

```
[Client] --> [FastAPI + Basic Auth]
                |
                v
         [Rate Limiter]
                |
                v
     [Hash Check (SQLite)]
         |            |
     [Cache HIT]   [Cache MISS]
         |            |
   [Return file]  [asyncio.Queue]
                      |
                      v
              [Singleton Worker]
              [TurboVieNeuTTS.infer()]
                      |
                      v
              [Save file + Insert DB]
                      |
                      v
              [Return file to client]

[APScheduler] --> [Cleanup old files + DB records daily]
[GET /health] --> [System status check]
```

---

*Bao cao duoc tao tu dong boi Copilot dua tren phan tich source code VieNeu-TTS v2.4.3*
*Ngay: 2026-04-17*
