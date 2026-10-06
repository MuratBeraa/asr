"""
Turkish STT + Battle Card + RAG - FastAPI + WebSocket.
- WS /ws: Mikrofon PCM akisi -> STT -> sliding window + RAG + LLM
- GET /: index.html
- GET /static/*: statik dosyalar
"""
import asyncio
import json
import time
import threading
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from stt_service import STTSession
from llm_service import generate_battle_card
from rag_service import get_rag

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

# Ayarlar
SLIDING_WINDOW_SEC = 300       # 5 dakika
BC_CHECK_INTERVAL = 5          # 5 saniyede bir kontrol
BC_MIN_NEW_CHARS = 20          # En az 20 yeni karakter

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# RAG servisini başlat
rag = get_rag()


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


class SessionState:
    def __init__(self):
        self.stt = STTSession()
        self.segments = []            # [(timestamp, text), ...]
        self.last_bc_text = ""        # Son LLM'e gönderilen transcript
        self.last_bc_result = None    # Son Battle Card sonucu
        self.generating_bc = False
        self.lock = threading.Lock()

    def add_final(self, text: str):
        with self.lock:
            self.segments.append((time.time(), text))

    def get_sliding_window(self) -> str:
        """Son 5 dakikadaki tüm final segmentleri döndür."""
        cutoff = time.time() - SLIDING_WINDOW_SEC
        with self.lock:
            recent = [s for ts, s in self.segments if ts >= cutoff]
        return " ".join(recent)


async def bc_worker(ws: WebSocket, state: SessionState, loop):
    """5 saniyede bir kontrol et: yeni içerik var mı? Varsa RAG+LLM çağır."""
    while True:
        await asyncio.sleep(BC_CHECK_INTERVAL)

        with state.lock:
            generating = state.generating_bc

        if generating:
            continue

        transcript = state.get_sliding_window()

        if len(transcript.strip()) < 20:
            continue

        # Yeni içerik var mı?
        if transcript == state.last_bc_text:
            continue

        # Ne kadar yeni?
        new_chars = abs(len(transcript) - len(state.last_bc_text))
        if state.last_bc_text and new_chars < BC_MIN_NEW_CHARS:
            continue

        with state.lock:
            state.generating_bc = True

        try:
            # 1. RAG: ilgili kampanyaları bul
            campaigns = await loop.run_in_executor(None, rag.search, transcript, 5)
            campaigns_text = rag.format_for_llm(campaigns)

            print(f"[bc] {len(campaigns)} kampanya bulundu")

            # 2. LLM: Battle Card üret
            bc = await loop.run_in_executor(
                None, generate_battle_card, transcript, campaigns_text
            )
            bc["updated_at"] = time.time()
            bc["campaign_ids"] = [c["id"] for c in campaigns]

            with state.lock:
                state.last_bc_text = transcript
                state.last_bc_result = bc

            try:
                await ws.send_json({"type": "battle_card", "data": bc})
            except Exception:
                break
        except Exception as e:
            print(f"[bc_worker] hata: {e}")
        finally:
            with state.lock:
                state.generating_bc = False


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    state = SessionState()
    loop = asyncio.get_event_loop()

    worker_task = asyncio.create_task(bc_worker(ws, state, loop))

    try:
        while True:
            data = await ws.receive()

            if "text" in data and data["text"] is not None:
                try:
                    msg = json.loads(data["text"])
                    if msg.get("action") == "refresh_bc":
                        with state.lock:
                            state.last_bc_text = ""
                    continue
                except Exception:
                    pass
                continue

            if "bytes" in data and data["bytes"] is not None:
                pcm = data["bytes"]
                if not pcm:
                    continue

                try:
                    text, is_final = state.stt.process(pcm)
                except Exception as e:
                    await ws.send_json({"type": "error", "msg": str(e)})
                    continue

                if not text:
                    continue

                await ws.send_json({
                    "type": "stt",
                    "text": text,
                    "final": bool(is_final),
                })

                if is_final:
                    state.add_final(text)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[ws] hata: {e}")
    finally:
        worker_task.cancel()


if __name__ == "__main__":
    print("http://127.0.0.1:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")