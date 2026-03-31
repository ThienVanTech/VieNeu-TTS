# 🦜 VieNeu-TTS

**VieNeu-TTS** is an advanced on-device Vietnamese Text-to-Speech (TTS) model with **instant voice cloning** and **English-Vietnamese bilingual** support.

[![Hugging Face v2 Turbo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-v2%20Turbo-blue)](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)

## ✨ Key Features
- **Bilingual (English-Vietnamese)**: Seamless transitions between languages (Code-switching) in version 2.0+.
- **Ultra-Fast Turbo Mode**: Optimized for CPU/Mobile using GGUF and ONNX. No dedicated GPU required!
- **Instant Voice Cloning**: Clone any voice with just 3-5s of reference audio (GPU mode).
- **Production Ready**: High-fidelity 24 kHz audio generation, fully offline.
- **AI Identification**: Built-in audio watermarking for responsible AI use.

---

## 📦 Quick Install

```bash
# Minimal installation (Turbo/CPU Only)
pip install vieneu

# Optional: Pre-built llama-cpp-python for CPU (if building fails)
pip install vieneu --extra-index-url https://pnnbao97.github.io/llama-cpp-python-v0.3.16/cpu/

# Optional: macOS Metal acceleration
pip install vieneu --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/metal/
```
---

## 🚀 Quick Start (Python SDK)

The SDK now defaults to **Turbo mode** for maximum out-of-the-box compatibility.

```python
from vieneu import Vieneu

# Initialize - Minimal dependencies required!
tts = Vieneu()

# Synthesis with Bilingual support (Vietnamese + English)
text = "Trước đây, hệ thống điện chủ yếu sử dụng direct current, nhưng Tesla đã chứng minh rằng alternating current is more efficient."
audio = tts.infer(text=text)

# Save output
tts.save(audio, "output.wav")
print("💾 Saved synthesis to output.wav")
```

### Advanced Usage (Remote API)
Connect to a remote VieNeu-TTS server without loading heavy models locally:
```python
tts = Vieneu(mode='remote', api_base='http://your-server:23333/v1')
audio = tts.infer(text="Xin chào!")
```

---

## 🔬 Model Overview

| Model | Format | Device | Bilingual | Cloning | Speed |
|---|---|---|---|---|---|
| **VieNeu-v2-Turbo** | GGUF/ONNX | **CPU**/GPU | ✅ | ❌ (Ssoon) | **Extreme** |
| **VieNeu-TTS-v2** | PyTorch | GPU | ✅ | ✅ | **Standard** (Ssoon) |
| **VieNeu-TTS 0.3B** | PyTorch | GPU/CPU | ❌ | ✅ | **Very Fast** |
| **VieNeu-TTS** | PyTorch | GPU/CPU | ❌ | ✅ | **Standard** |

---

## 🤝 Support & Links
- **GitHub:** [pnnbao97/VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS)
- **Hugging Face:** [pnnbao-ump](https://huggingface.co/pnnbao-ump)
- **Discord:** [Join our community](https://discord.gg/yJt8kzjzWZ)

---

**Made with ❤️ for the Vietnamese TTS community**
