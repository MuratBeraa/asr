import sys
import queue
import numpy as np
import sounddevice as sd
import mihu_stt

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
BLOCK_SIZE = 1600
DEVICE = None

# ANSI kaçış dizileri
CLEAR_LINE = "\x1b[2K\r"
DISABLE_WRAP = "\x1b[7l"
ENABLE_WRAP = "\x1b[7h"

print("Model yükleniyor...")
stt = mihu_stt.StreamingSTT()
print("Hazır! Konuşmaya başla. Çıkmak için Ctrl+C.\n")

# Satır kaydırmayı kapat
sys.stdout.write(DISABLE_WRAP)
sys.stdout.flush()

audio_queue: "queue.Queue[bytes]" = queue.Queue()

def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"[stream uyarı] {status}", file=sys.stderr)
    audio_queue.put(indata.tobytes())

def main():
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        blocksize=BLOCK_SIZE,
        device=DEVICE,
        callback=audio_callback,
    ):
        current_line = ""
        try:
            while True:
                pcm_bytes = audio_queue.get()
                text, is_final = stt.accept_pcm16(pcm_bytes, sample_rate=SAMPLE_RATE)

                if text != current_line:
                    sys.stdout.write(CLEAR_LINE + text)
                    sys.stdout.flush()
                    current_line = text

                if is_final:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    current_line = ""
        except KeyboardInterrupt:
            print("\n\nÇıkılıyor...")
        finally:
            # Satır kaydırmayı geri aç
            sys.stdout.write(ENABLE_WRAP)
            sys.stdout.flush()
            close_fn = getattr(stt, "close", None)
            if callable(close_fn):
                close_fn()

if __name__ == "__main__":
    main()