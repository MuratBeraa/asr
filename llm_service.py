"""OpenRouter Battle Card uretimi — RAG destekli."""
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY bulunamadi")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY,
)

MODEL = "google/gemini-2.5-flash-lite"

SYSTEM_PROMPT = """Sen Eminevim'de calisan bir satis temsilcisine anlik destek veren bir yapay zeka asistanisin.
Sana iki bilgi verilecek:
1. Musteri ile temsilci arasinda gecen son 5 dakikalik konusma transkripti
2. Bu konusmaya uygun olabilecek Eminevim kampanyalari (RAG ile bulundu)

Gorev: Bu bilgileri kullanarak temsilciye ANLIK, KISA ve UYGULANABILIR bir Battle Card uret.

UC ALAN uret:

1. intent: Musterinin asil istegi, butcesi, ihtiyaci nedir? Konusmadan cikar. En fazla 2 cumle.

2. action: Temsilci su anda ne yapmali? Somut bir sonraki adim. En fazla 2 cumle.

3. warning: Temsilcinin dikkat etmesi gerekenler + MUSTERIYE ONERILEBILECEK KAMPANYALAR.
   Basta dikkat edilecekleri yaz, sonra "Uygun Kampanyalar:" basligi altinda
   sana verilen kampanyalardan en uygun 1-3 tanesini KOD ve ISIMLE listele.
   Ornek format:
   "Musteri 500 bin pesinati reddetti, tekrar onermeyin.
    Uygun Kampanyalar: EMP-2025-001 (Genc Ev Sahibi Paketi), EMP-2025-004 (Dusuk Pesinat Firsati)"

Yaniti SADECE su JSON formatinda ver, baska hicbir sey yazma:
{"intent": "...", "action": "...", "warning": "..."}

Tum cevaplar TURKCE olmali. Kisa ve net yaz.
Temsilci ve musteriyi konusma baglamindan sen ayirt et."""


def generate_battle_card(transcript: str, campaigns_text: str = "", timeout: float = 15.0) -> dict:
    if not transcript or len(transcript.strip()) < 20:
        return {
            "intent": "Henuz yeterli konusma yok",
            "action": "Konusmanin ilerlemesini bekleyin",
            "warning": "-",
        }

    user_prompt = f"""KONUSMA TRANSKRIPTI (son 5 dakika):
{transcript}

ILGILI KAMPANYALAR:
{campaigns_text if campaigns_text else '(Bu konusmayla ilgili kampanya bulunamadi)'}

Yukaridaki konusmayi analiz ederek Battle Card uret."""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=400,
            timeout=timeout,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        return {
            "intent": str(data.get("intent", ""))[:600],
            "action": str(data.get("action", ""))[:600],
            "warning": str(data.get("warning", ""))[:800],
        }
    except json.JSONDecodeError:
        return {
            "intent": "LLM yaniti parse edilemedi",
            "action": "Tekrar deneyin",
            "warning": "-",
        }
    except Exception as e:
        return {
            "intent": "LLM hatasi",
            "action": str(e)[:200],
            "warning": "-",
        }