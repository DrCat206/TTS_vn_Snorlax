import edge_tts
import asyncio
from langdetect import detect

VOICE_MAP = {
    "vi": "vi-VN-HoaiMyNeural",
    "en": "en-US-AriaNeural",
    "ja": "ja-JP-NanamiNeural"
}

def detect_lang(text):
    try:
        lang = detect(text)
        if lang.startswith("ja"):
            return "ja"
        elif lang.startswith("en"):
            return "en"
        return "vi"
    except:
        return "vi"

async def generate(text, filename, anime=False):
    lang = detect_lang(text)
    voice = VOICE_MAP.get(lang)

    kwargs = {
        "text": text,
        "voice": voice
    }

    if anime and lang == "ja":
        kwargs["pitch"] = "+12%"
        kwargs["rate"] = "+10%"

    for _ in range(3):
        try:
            com = edge_tts.Communicate(**kwargs)
            await asyncio.wait_for(com.save(filename), timeout=10)
            return True
        except:
            await asyncio.sleep(1)

    return False