"""
Kokoro TTS helper - generates audio from text and plays it via sounddevice
Optimized: loads model once, reuses across calls
"""

import os
os.environ.setdefault('HF_HOME', os.path.join(os.path.expanduser('~'), '.cache', 'huggingface'))

import sys
import tempfile
import time
import numpy as np

# Global pipeline (loaded once)
_pipeline = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        print("Loading Kokoro model...", file=sys.stderr)
        from kokoro import KPipeline
        _pipeline = KPipeline(lang_code='p', repo_id='hexgrad/Kokoro-82M')
        print("Kokoro model loaded.", file=sys.stderr)
    return _pipeline

def speak(text):
    """Generate audio with Kokoro and play it via sounddevice"""
    import sounddevice as sd
    import soundfile as sf
    
    pipeline = get_pipeline()
    
    start = time.time()
    for i, (gs, ps, audio) in enumerate(pipeline(text, voice='af_heart')):
        # Play directly via sounddevice (no file needed)
        sd.play(audio, 24000)
        sd.wait()  # Wait for playback to finish
        elapsed = time.time() - start
        print(f"Audio played in {elapsed:.2f}s", file=sys.stderr)
        break

def synth_to_bytes(text, voice='pf_dora'):
    """Gera áudio Kokoro e devolve WAV bytes (SEM reproduzir no PC).
    Usado pelo voice gateway para enviar TTS ao telemóvel."""
    import io
    import soundfile as sf
    pipeline = get_pipeline()
    for gs, ps, audio in pipeline(text, voice=voice):
        buf = io.BytesIO()
        sf.write(buf, audio, 24000, format='WAV')
        return buf.getvalue()
    return None

if __name__ == '__main__':
    if len(sys.argv) > 1:
        text = ' '.join(sys.argv[1:])
        speak(text)
