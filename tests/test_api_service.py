"""Tests for the VieNeu-TTS API service components.

These tests validate the cache layer, worker speed post-processing, and the
FastAPI endpoints using mocked TTS engines (no real model loading required).
"""

import asyncio
import os
import sqlite3
import tempfile
import time

import numpy as np
import pytest

from apps.tts_cache import TTSCache, _compute_hash
from apps.tts_worker import _apply_speed, _wav_bytes


# ──────────────────────────────────────────────────────────────────────────────
# Cache tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_cache(tmp_path):
    db = str(tmp_path / "test.db")
    cdir = str(tmp_path / "audio")
    return TTSCache(db_path=db, cache_dir=cdir)


class TestTTSCache:
    def test_lookup_miss(self, tmp_cache):
        assert tmp_cache.lookup("hello", "vi", 1.0, "v1") is None

    def test_store_and_lookup_hit(self, tmp_cache):
        fpath = os.path.join(tmp_cache.cache_dir, "test.wav")
        with open(fpath, "wb") as f:
            f.write(b"RIFF" + b"\x00" * 100)

        entry = tmp_cache.store("hello", "vi", 1.0, "v1", fpath)
        assert entry.hash == _compute_hash("hello", "vi", 1.0, "v1")
        assert entry.file_path == fpath

        hit = tmp_cache.lookup("hello", "vi", 1.0, "v1")
        assert hit is not None
        assert hit.file_path == fpath

    def test_lookup_removes_orphan_record(self, tmp_cache):
        tmp_cache.store("a", "vi", 1.0, "v1", "/nonexistent/file.wav")
        assert tmp_cache.lookup("a", "vi", 1.0, "v1") is None

    def test_store_replaces_old_file(self, tmp_cache):
        old = os.path.join(tmp_cache.cache_dir, "old.wav")
        new = os.path.join(tmp_cache.cache_dir, "new.wav")
        for p in (old, new):
            with open(p, "wb") as f:
                f.write(b"data")

        tmp_cache.store("b", "vi", 1.0, "v1", old)
        tmp_cache.store("b", "vi", 1.0, "v1", new)

        assert not os.path.isfile(old)
        hit = tmp_cache.lookup("b", "vi", 1.0, "v1")
        assert hit is not None
        assert hit.file_path == new

    def test_invalidate(self, tmp_cache):
        fpath = os.path.join(tmp_cache.cache_dir, "del.wav")
        with open(fpath, "wb") as f:
            f.write(b"data")

        tmp_cache.store("c", "vi", 1.0, "v1", fpath)
        tmp_cache.invalidate("c", "vi", 1.0, "v1")

        assert not os.path.isfile(fpath)
        assert tmp_cache.lookup("c", "vi", 1.0, "v1") is None

    def test_cleanup_old(self, tmp_cache):
        fpath = os.path.join(tmp_cache.cache_dir, "stale.wav")
        with open(fpath, "wb") as f:
            f.write(b"data")

        tmp_cache.store("d", "vi", 1.0, "v1", fpath)
        # Manually backdate the last_used timestamp
        h = _compute_hash("d", "vi", 1.0, "v1")
        old_ts = time.time() - 31 * 86400
        tmp_cache._conn.execute(
            "UPDATE tts_cache SET last_used = ? WHERE hash = ?", (old_ts, h)
        )
        tmp_cache._conn.commit()

        removed = tmp_cache.cleanup_old(max_age_days=30)
        assert removed == 1
        assert not os.path.isfile(fpath)

    def test_hash_deterministic(self):
        a = _compute_hash("hello", "vi", 1.0, "voice1")
        b = _compute_hash("hello", "vi", 1.0, "voice1")
        assert a == b

    def test_hash_varies_with_params(self):
        base = _compute_hash("hello", "vi", 1.0, "v1")
        assert _compute_hash("hello", "en", 1.0, "v1") != base
        assert _compute_hash("hello", "vi", 1.5, "v1") != base
        assert _compute_hash("hello", "vi", 1.0, "v2") != base
        assert _compute_hash("world", "vi", 1.0, "v1") != base


# ──────────────────────────────────────────────────────────────────────────────
# Worker helper tests
# ──────────────────────────────────────────────────────────────────────────────

class TestApplySpeed:
    def test_noop_at_1x(self):
        audio = np.random.randn(24000).astype(np.float32)
        result = _apply_speed(audio, 1.0)
        np.testing.assert_array_equal(result, audio)

    def test_empty_audio(self):
        result = _apply_speed(np.array([], dtype=np.float32), 1.5)
        assert len(result) == 0

    def test_speed_up_shortens(self):
        audio = np.random.randn(48000).astype(np.float32)
        result = _apply_speed(audio, 2.0)
        assert len(result) < len(audio)

    def test_slow_down_lengthens(self):
        audio = np.random.randn(48000).astype(np.float32)
        result = _apply_speed(audio, 0.5)
        assert len(result) > len(audio)

    def test_output_dtype(self):
        audio = np.random.randn(24000).astype(np.float32)
        result = _apply_speed(audio, 1.5)
        assert result.dtype == np.float32


class TestWavBytes:
    def test_produces_valid_wav(self):
        audio = np.zeros(24000, dtype=np.float32)
        data = _wav_bytes(audio)
        assert data[:4] == b"RIFF"

    def test_length_proportional(self):
        short = _wav_bytes(np.zeros(100, dtype=np.float32))
        long = _wav_bytes(np.zeros(1000, dtype=np.float32))
        assert len(long) > len(short)


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI endpoint tests (with mocked TTS engine)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Create a TestClient with a mocked TTS engine."""
    monkeypatch.setenv("TTS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("TTS_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TTS_USERNAME", "testuser")
    monkeypatch.setenv("TTS_PASSWORD", "testpass")

    from unittest.mock import MagicMock, patch

    mock_engine = MagicMock()
    mock_engine.infer.return_value = np.random.randn(24000).astype(np.float32)
    mock_engine.list_preset_voices.return_value = [
        ("Default Vietnamese", "default_vi"),
    ]
    mock_engine.get_preset_voice.return_value = {
        "codes": np.zeros(128),
        "text": "ref",
    }
    mock_engine.close.return_value = None

    with patch("apps.api_service._load_tts_engine", return_value=mock_engine):
        from fastapi.testclient import TestClient

        # Need to reimport to pick up the monkeypatched env vars
        import importlib
        import apps.api_service as api_mod
        importlib.reload(api_mod)

        with patch.object(api_mod, "_load_tts_engine", return_value=mock_engine):
            with TestClient(api_mod.app) as tc:
                yield tc


class TestHealthEndpoint:
    def test_health_no_auth_required(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["model_loaded"] is True


class TestSynthesizeEndpoint:
    def test_rejects_without_auth(self, client):
        resp = client.post(
            "/v1/tts/synthesize",
            json={"text": "hello"},
        )
        assert resp.status_code == 401

    def test_rejects_bad_auth(self, client):
        resp = client.post(
            "/v1/tts/synthesize",
            json={"text": "hello"},
            auth=("wrong", "creds"),
        )
        assert resp.status_code == 401

    def test_synthesize_wav(self, client):
        import uuid

        resp = client.post(
            "/v1/tts/synthesize",
            json={"text": f"synthesize wav {uuid.uuid4()}", "lang": "vi", "speed": 1.0},
            auth=("testuser", "testpass"),
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        assert resp.headers["x-cache"] == "MISS"

    def test_cache_hit_on_second_request(self, client):
        import uuid

        payload = {
            "text": f"cache test {uuid.uuid4()}",
            "lang": "vi",
            "speed": 1.0,
            "is_load_from_cache": True,
        }
        auth = ("testuser", "testpass")

        r1 = client.post("/v1/tts/synthesize", json=payload, auth=auth)
        assert r1.status_code == 200
        assert r1.headers["x-cache"] == "MISS"

        r2 = client.post("/v1/tts/synthesize", json=payload, auth=auth)
        assert r2.status_code == 200
        assert r2.headers["x-cache"] == "HIT"

    def test_bypass_cache(self, client):
        import uuid

        payload = {
            "text": f"no cache {uuid.uuid4()}",
            "lang": "vi",
            "speed": 1.0,
            "is_load_from_cache": False,
        }
        auth = ("testuser", "testpass")

        r1 = client.post("/v1/tts/synthesize", json=payload, auth=auth)
        assert r1.status_code == 200

        r2 = client.post("/v1/tts/synthesize", json=payload, auth=auth)
        assert r2.status_code == 200
        assert r2.headers["x-cache"] == "MISS"

    def test_rejects_empty_text(self, client):
        resp = client.post(
            "/v1/tts/synthesize",
            json={"text": ""},
            auth=("testuser", "testpass"),
        )
        assert resp.status_code == 422

    def test_rejects_invalid_lang(self, client):
        resp = client.post(
            "/v1/tts/synthesize",
            json={"text": "test", "lang": "fr"},
            auth=("testuser", "testpass"),
        )
        assert resp.status_code == 422


class TestVoicesEndpoint:
    def test_list_voices(self, client):
        resp = client.get(
            "/v1/tts/voices",
            auth=("testuser", "testpass"),
        )
        assert resp.status_code == 200
        voices = resp.json()
        assert len(voices) >= 1
        assert voices[0]["id"] == "default_vi"
