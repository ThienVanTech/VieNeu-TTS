"""VieNeu-TTS API Service.

High-performance FastAPI service for text-to-speech synthesis powered by
VieNeu Turbo v2.  Features include Basic Authentication, an async task
queue (singleton worker), SQLite-backed audio caching, daily auto-cleanup
via APScheduler, speed control (post-processing), and MP3 output support.

Usage::

    # Start the server
    uv run apps/api_service.py

    # Or via the CLI entry point
    vieneu-api
"""

import asyncio
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import uvicorn
import yaml
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from apps.tts_cache import TTSCache
from apps.tts_worker import TTSRequest, TTSWorker

logger = logging.getLogger("Vieneu.API")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONFIG_PATH = os.getenv(
    "TTS_CONFIG_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml"),
)

TTS_USERNAME = os.getenv("TTS_USERNAME", "admin")
TTS_PASSWORD = os.getenv("TTS_PASSWORD", "admin")
TTS_HOST = os.getenv("TTS_HOST", "0.0.0.0")
TTS_PORT = int(os.getenv("TTS_PORT", "8000"))
TTS_RATE_LIMIT = os.getenv("TTS_RATE_LIMIT", "30/minute")

# ---------------------------------------------------------------------------
# Globals (initialised in lifespan)
# ---------------------------------------------------------------------------
tts_engine = None
worker: Optional[TTSWorker] = None
cache: Optional[TTSCache] = None
scheduler = None
_startup_time: float = 0.0


def _load_config() -> dict:
    if os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    return {}


def _load_tts_engine():
    """Load and cache the TTS model once at startup."""
    from vieneu import Vieneu

    cfg = _load_config()
    api_cfg = cfg.get("api_service", {})

    # Allow env var override for backbone repo (e.g. local path in Docker)
    backbone_repo = os.getenv("TTS_BACKBONE_REPO") or api_cfg.get(
        "backbone_repo", "pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF"
    )
    device = api_cfg.get("device", "cpu")

    logger.info(f"Loading TTS model: {backbone_repo} on {device}")
    engine = Vieneu(mode="turbo", backbone_repo=backbone_repo, device=device)
    logger.info("TTS model loaded and cached in memory")
    return engine


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    global tts_engine, worker, cache, scheduler, _startup_time

    _startup_time = time.time()

    tts_engine = _load_tts_engine()

    cache = TTSCache()

    worker = TTSWorker(tts_engine)
    worker.start()

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            _daily_cleanup, "cron", hour=0, minute=0, id="tts_cache_cleanup"
        )
        scheduler.start()
        logger.info("APScheduler started (daily cache cleanup at 00:00)")
    except ImportError:
        logger.warning(
            "apscheduler not installed; daily cache cleanup disabled"
        )

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
    if cache is not None:
        cache.close()
    if tts_engine is not None:
        tts_engine.close()


async def _daily_cleanup() -> None:
    if cache is not None:
        cache.cleanup_old()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="VieNeu-TTS API Service",
    version="1.0.0",
    description="CPU-optimised Vietnamese TTS API with caching and queueing",
    lifespan=lifespan,
)

# Rate limiting ---
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, default_limits=[TTS_RATE_LIMIT])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    _has_limiter = True
except ImportError:
    _has_limiter = False
    logger.warning("slowapi not installed; rate limiting disabled")

# Security ---
security = HTTPBasic()


def _verify_credentials(
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    correct_user = secrets.compare_digest(credentials.username, TTS_USERNAME)
    correct_pass = secrets.compare_digest(credentials.password, TTS_PASSWORD)
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class SynthesizeRequest(BaseModel):
    """JSON body for the TTS synthesize endpoint."""

    text: str = Field(..., min_length=1, max_length=5000)
    lang: str = Field(default="vi", pattern="^(vi|en)$")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    voice_id: Optional[str] = Field(default=None)
    output_format: str = Field(default="wav", pattern="^(wav|mp3)$")
    is_load_from_cache: bool = Field(
        default=True,
        description=(
            "When True, return a cached audio file if one exists for this "
            "exact request.  When False, always regenerate the audio and "
            "replace the old cached file."
        ),
    )
    temperature: float = Field(
        default=0.4,
        ge=0.1,
        le=1.5,
        description="Generation temperature. Higher = more varied but less stable.",
    )
    top_k: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Top-K sampling parameter for token generation.",
    )
    max_chars_per_chunk: int = Field(
        default=256,
        ge=128,
        le=512,
        description="Max characters per text chunk for synthesis.",
    )


class HealthResponse(BaseModel):
    """Response for the /health endpoint."""

    status: str
    model_loaded: bool
    queue_size: int
    cache_db: str
    uptime_seconds: float


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Unauthenticated health-check for Docker / load-balancers."""
    return HealthResponse(
        status="ok",
        model_loaded=tts_engine is not None,
        queue_size=worker.queue_size if worker else 0,
        cache_db=cache.db_path if cache else "n/a",
        uptime_seconds=round(time.time() - _startup_time, 1),
    )


@app.post("/v1/tts/synthesize")
async def synthesize(
    req: SynthesizeRequest,
    _user: str = Depends(_verify_credentials),
):
    """Synthesize speech from text.

    Returns the audio file directly as a ``FileResponse``.
    """
    if worker is None or cache is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TTS engine not ready",
        )

    cfg = _load_config()
    api_cfg = cfg.get("api_service", {})
    lang_cfg = api_cfg.get("languages", {}).get(req.lang, {})
    gen_cfg = api_cfg.get("generation", {})
    voice_id = req.voice_id or os.getenv("TTS_DEFAULT_VOICE") or lang_cfg.get("default_voice_id", "")
    output_format = req.output_format or lang_cfg.get("output_format", "wav")

    # Resolve generation parameters: request > env > config > hardcoded default
    temperature = req.temperature
    if temperature == 0.4:  # default from schema — check config/env overrides
        temperature = float(os.getenv("TTS_TEMPERATURE", "0")) or gen_cfg.get("temperature", 0.4)
    top_k = req.top_k
    if top_k == 50:
        top_k = int(os.getenv("TTS_TOP_K", "0")) or gen_cfg.get("top_k", 50)
    max_chars = req.max_chars_per_chunk
    if max_chars == 256:
        max_chars = int(os.getenv("TTS_MAX_CHARS_PER_CHUNK", "0")) or gen_cfg.get("max_chars_per_chunk", 256)

    if req.is_load_from_cache:
        entry = cache.lookup(req.text, req.lang, req.speed, voice_id)
        if entry is not None:
            media = (
                "audio/mpeg" if entry.file_path.endswith(".mp3") else "audio/wav"
            )
            return FileResponse(
                entry.file_path,
                media_type=media,
                headers={"X-Cache": "HIT"},
            )

    future: asyncio.Future = asyncio.get_running_loop().create_future()
    job = TTSRequest(
        text=req.text,
        lang=req.lang,
        speed=req.speed,
        voice_id=voice_id,
        output_format=output_format,
        future=future,
        temperature=temperature,
        top_k=top_k,
        max_chars=max_chars,
    )

    try:
        filepath = await worker.submit(job)
    except Exception as exc:
        logger.error(f"Synthesis failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Synthesis failed: {exc}",
        ) from exc

    cache.store(req.text, req.lang, req.speed, voice_id, filepath)

    media = "audio/mpeg" if filepath.endswith(".mp3") else "audio/wav"
    return FileResponse(
        filepath,
        media_type=media,
        headers={"X-Cache": "MISS"},
    )


@app.get("/v1/tts/voices")
async def list_voices(
    _user: str = Depends(_verify_credentials),
):
    """List available preset voices."""
    if tts_engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TTS engine not ready",
        )
    voices = tts_engine.list_preset_voices()
    return [
        {"id": vid, "description": desc}
        for desc, vid in voices
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    logger.info(f"Starting VieNeu-TTS API on {TTS_HOST}:{TTS_PORT}")
    uvicorn.run(
        "apps.api_service:app",
        host=TTS_HOST,
        port=TTS_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
