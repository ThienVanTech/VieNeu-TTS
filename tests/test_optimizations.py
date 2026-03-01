import pytest
from vieneu_utils.phonemize_text import phonemize_batch, phonemize_with_dict
from unittest.mock import patch, MagicMock

def test_phonemize_batch_deduplication():
    # Use 3 texts with overlapping words and English segments
    # Note: we use words that won't be normalized to numbers
    texts = [
        "Cái Bàn <en>world</en>",
        "Cái Bàn <en>world</en>",
        "Cái Ghế <en>world</en>"
    ]

    # Patch the actual phonemize call to count how many times it's called
    with patch("vieneu_utils.phonemize_text.phonemize") as mock_phonemize:
        # Mocking return values for phonemize
        # 1. EN segments: ['world']
        # 2. VI cores: ['cái', 'bàn', 'ghế']
        mock_phonemize.side_effect = [
            ["w-o-r-l-d"], # EN result
            ["kai", "ban", "ge"] # VI result
        ]

        # Use an empty custom dict to ensure words are not found
        results = phonemize_batch(texts, phoneme_dict={})

        # Verify deduplication:
        # - phonemize should be called once for unique EN segments
        # - phonemize should be called once for unique VI cores
        assert mock_phonemize.call_count == 2

        # Check if calls had unique elements
        en_call_args = mock_phonemize.call_args_list[0][0][0]
        assert len(en_call_args) == 1
        assert "world" in en_call_args

        vi_call_args = mock_phonemize.call_args_list[1][0][0]
        # 'cái', 'bàn', 'ghế'
        assert len(vi_call_args) == 3
        assert "cái" in vi_call_args
        assert "bàn" in vi_call_args
        assert "ghế" in vi_call_args

def test_phonemize_with_dict_caching():
    from vieneu_utils.phonemize_text import _phonemize_with_dict_cached
    text = "Câu này sẽ được cache"

    # Clear cache before test
    _phonemize_with_dict_cached.cache_clear()

    with patch("vieneu_utils.phonemize_text.phonemize_batch") as mock_batch:
        mock_batch.return_value = ["p-h-o-n-e-m-e-s"]

        # First call (uses default dict)
        res1 = phonemize_with_dict(text)
        # Second call (uses default dict)
        res2 = phonemize_with_dict(text)

        assert res1 == res2
        # Should only be called once due to LRU cache
        assert mock_batch.call_count == 1

def test_base_ref_phoneme_cache():
    from vieneu.base import BaseVieneuTTS

    # BaseVieneuTTS is abstract, so we need a concrete implementation or mock
    class MockTTS(BaseVieneuTTS):
        def infer(self, text, **kwargs):
            return None

    tts = MockTTS()
    ref_text = "Giọng đọc mẫu số 1"

    with patch("vieneu_utils.phonemize_text.phonemize_with_dict") as mock_phonemize:
        mock_phonemize.return_value = "cached-phonemes"

        p1 = tts.get_ref_phonemes(ref_text)
        p2 = tts.get_ref_phonemes(ref_text)

        assert p1 == p2
        assert mock_phonemize.call_count == 1
        assert ref_text in tts._ref_phoneme_cache
