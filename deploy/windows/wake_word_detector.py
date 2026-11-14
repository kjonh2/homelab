import logging

logger = logging.getLogger(__name__)

class WakeWordDetector:
    def __init__(self, model_path=None, sample_rate=16000, chunk_duration_ms=1000, threshold=0.5):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.detection_callback = None
        
    def set_detection_callback(self, callback):
        self.detection_callback = callback
        
    def start_listening(self):
        logger.info("WakeWordDetector started (placeholder)")
        
    def stop_listening(self):
        logger.info("WakeWordDetector stopped")
        
    def process_audio(self, audio_chunk):
        # In a real implementation, this would use a small NN model or Porcupine
        # For this prototype, we'll let the main loop handle the transcription
        # and check for the wake word there (already implemented in drisa_main.py)
        pass
