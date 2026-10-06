"""mihu_stt streaming wrapper."""
import mihu_stt


class STTSession:
    def __init__(self):
        self.session = mihu_stt.StreamingSTT()

    def process(self, pcm_bytes: bytes):
        """PCM16 bytes -> (text, is_final)."""
        return self.session.accept_pcm16(pcm_bytes, sample_rate=16000)