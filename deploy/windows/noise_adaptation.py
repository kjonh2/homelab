"""
Adaptação de ruído online — STUB no-op.

O ficheiro original (OnlineNoiseAdapter com modelo .pt) perdeu-se do projeto
(só ficou __pycache__/noise_adaptation.cpython-311.pyc). Este stub mantém a
interface usada pelo drisa_main.py (process_frame) e devolve o áudio sem
alterações, para a app arrancar sem adaptação de ruído. Quando o modelo
original voltar, basta substituir este ficheiro.
"""


class OnlineNoiseAdapter:
    def __init__(self, model_path=None, device=None, update_interval=None):
        self.model_path = model_path
        self.device = device
        self.update_interval = update_interval
        self.enabled = False

    def process_frame(self, audio_data, sample_rate: int, is_voice_active: bool = False):
        """No-op: devolve o áudio tal como recebe (sem adaptação de ruído)."""
        return audio_data
