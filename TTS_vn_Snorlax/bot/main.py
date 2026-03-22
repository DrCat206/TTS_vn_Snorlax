import discord
from discord.ext import commands
import asyncio
import os
import re
from io import BytesIO
import edge_tts
from dotenv import load_dotenv
from langdetect import detect
from keep_alive import keep_alive

load_dotenv()

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("❌ Missing TOKEN")

# ===== CONFIG ĐA GIỌNG & TÙY CHỈNH TỪNG NGƯỜI =====
LANG_CONFIG = {
    "vi": {"voice": "vi-VN-HoaiMyNeural", "pitch": "+15Hz", "suffix": " nha~"}, # Tiếng Việt: Giọng cao, thêm đuôi "nha"
    "ja": {"voice": "ja-JP-NanamiNeural", "pitch": "+15Hz", "suffix": " ね〜"},  # Tiếng Nhật: Giọng cao, chuẩn anime
    "en": {"voice": "en-US-AnaNeural",    "pitch": "+0Hz",  "suffix": ""}        # Tiếng Anh: Giọng chuẩn người thật, không đuôi
}
DEFAULT_LANG = "vi"

MAX_CACHE_SIZE = 500 # Chống tràn RAM
AFK_TIMEOUT = 300.0  # Tự động out sau 5 phút (300 giây) im lặng

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

queues = {}
workers = {}
cache = {}

# ================= TỪ ĐIỂN & BIÊN DỊCH =================
# ================= TỪ ĐIỂN & BIÊN DỊCH =================
VIET_DICT = {
    # === Tiếng Việt Cơ Bản & Gen Z ===
    r"\bko\b": "không", r"\bk\b": "không", r"\bđc\b": "được", r"\bdc\b": "được",
    r"\bj\b": "gì", r"\br\b": "rồi", r"\bmk\b": "mình", r"\boh\b": "ồ",
    r"\bth\b": "thôi", r"\bmn\b": "mọi người", r"\bđg\b": "đang", r"\bdg\b": "đang",
    r"\bntn\b": "như thế nào", r"\bvs\b": "với", r"\blm\b": "làm",
    r"\bđt\b": "điện thoại", r"\bđth\b": "điện thoại", r"\bhc\b": "học", r"\bđh\b": "đại học",
    
    r"\bcx\b": "cũng", r"\bchx\b": "chưa", r"\bh\b": "giờ", r"\bbh\b": "bây giờ",
    r"\bv\b": "vậy", r"\bz\b": "vậy", r"\bs\b": "sao", r"\bns\b": "nói",
    r"\bbt\b": "biết", r"\bkbt\b": "không biết", r"\btrc\b": "trước",
    r"\bhnay\b": "hôm nay", r"\bqua\b": "hôm qua", r"\bmik\b": "mình",
    r"\bmng\b": "mọi người", r"\buk\b": "ừm", r"\buh\b": "ừm",
    r"\boki\b": "ô kê", r"\bok\b": "ô kê", r"\bdz\b": "đẹp trai", r"\bxinh\b": "xinh",
    
    # === Game / Mạng Xã Hội Tiếng Việt ===
    r"\bny\b": "người yêu", r"\bvk\b": "vợ", r"\bck\b": "chồng", r"\bae\b": "anh em",
    r"\bib\b": "nhắn tin", r"\brep\b": "trả lời", r"\bcmt\b": "bình luận",
    r"\btt\b": "tương tác", r"\bkb\b": "kết bạn", r"\bklq\b": "không liên quan",
    r"\bsp\b": "hỗ trợ", r"\bad\b": "át min",
    
    # === Tránh nói bậy tiếng Việt ===
    r"\bvl\b": "vãi lúa", r"\bvc\b": "vãi chưởng", r"\bvcl\b": "vãi cả lúa",
    r"\bđm\b": "đờ mờ", r"\bđcm\b": "đê xê mờ", r"\bclgt\b": "cái lú gì thế", r"\bqq\b": "quần què",

    # 🔥 === TỪ LÓNG / VIẾT TẮT TIẾNG ANH (MỚI) === 🔥
    r"\bomg\b": "oh my god",
    r"\bidk\b": "I don't know",
    r"\bbtw\b": "by the way",
    r"\bbrb\b": "be right back",
    r"\btbh\b": "to be honest",
    r"\bfr\b": "for real",
    r"\bngl\b": "not gonna lie",
    r"\bnp\b": "no problem",
    r"\bty\b": "thank you",
    r"\btysm\b": "thank you so much",
    r"\basap\b": "as soon as possible",
    r"\bgg\b": "good game",
    r"\bwp\b": "well played",
    r"\bafk\b": "away from keyboard",
    r"\bily\b": "i love you",
    r"\blol\b": "laughing out loud",
    r"\blmao\b": "laughing my ass off",
    r"\bwtf\b": "what the heck", # Né nói bậy cho Ana dễ thương
}

# Tiền biên dịch Regex (Pre-compile)
COMPILED_DICT = [(re.compile(pattern, re.IGNORECASE), replacement) for pattern, replacement in VIET_DICT.items()]

def should_read(text: str):
    if text.startswith("!"): return False
    if text.startswith("http"): return False
    if len(text) < 2: return False
    if len(text) > 120: return False
    return True

def get_lang_config(text: str):
    try:
        lang = detect(text)
        return LANG_CONFIG.get(lang, LANG_CONFIG[DEFAULT_LANG])
    except:
        return LANG_CONFIG[DEFAULT_LANG]

def anime_text(text: str, suffix: str):
    # Dịch từ lóng
    for regex, replacement in COMPILED_DICT:
        text = regex.sub(replacement, text)

    text = text.replace("...", "… ").replace("!", "！ ").replace("?", "？ ")
    
    # Thêm đuôi (nha~ / ne~) nếu câu ngắn và ngôn ngữ đó có cấu hình đuôi
    if len(text) < 25 and suffix:
        text += suffix
        
    return text

# ================= TTS STREAM =================

async def generate_stream(text: str, voice: str, pitch: str):
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate="+0%",
        pitch=pitch
    )
    audio = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio.write(chunk["data"])
    return audio.getvalue()

# ================= WORKER =================

async def tts_worker(guild, channel):
    queue = queues[guild.id]

    while True:
        try:
            text = await asyncio.wait_for(queue.get(), timeout=AFK_TIMEOUT)
        except asyncio.TimeoutError:
            vc = guild.voice_client
            if vc and vc.is_connected():
                await vc.disconnect()
            
            if guild.id in queues:
                del queues[guild.id]
                del workers[guild.id]
            
            await channel.send("💤 Kênh im lặng lâu quá nên tớ đi ngủ đây. Bye bye~")
            break
        
        try:
            vc = guild.voice_client
            if not vc:
                continue

            if vc.is_playing():
                vc.stop()

            if len(cache) >= MAX_CACHE_SIZE:
                cache.clear()
                print("🧹 Đã dọn dẹp Cache!")

            # Nhận diện ngôn ngữ & lấy cấu hình TRƯỚC khi xử lý text
            config = get_lang_config(text)
            voice_to_use = config["voice"]
            pitch_to_use = config["pitch"]
            suffix_to_use = config["suffix"]
            
            # Xử lý text với hậu tố riêng của ngôn ngữ đó
            processed_text = anime_text(text, suffix_to_use)
            
            # Key cache chứa tên giọng để phân biệt
            cache_key = f"{voice_to_use}_{text}"

            if cache_key in cache:
                audio_bytes = cache[cache_key]
            else:
                audio_bytes = await generate_stream(processed_text, voice_to_use, pitch_to_use)
                cache[cache_key] = audio_bytes

            audio_stream = BytesIO(audio_bytes)

            vc.play(
                discord.FFmpegPCMAudio(
                    audio_stream,
                    pipe=True,
                    before_options="-loglevel panic",
                    options="-vn"
                )
            )

            while vc.is_playing():
                await asyncio.sleep(0.1)

        except Exception as e:
            print("❌ ERROR:", e)

        finally:
            queue.task_done()

# ================= COMMAND =================

@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send("❌ Cậu phải vào voice trước đã~")

    channel = ctx.author.voice.channel

    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()

    if ctx.guild.id not in queues:
        queues[ctx.guild.id] = asyncio.Queue()
        workers[ctx.guild.id] = asyncio.create_task(
            tts_worker(ctx.guild, ctx.channel) 
        )

    await ctx.send("✅ Tớ vào rồi nè! Tớ biết nói cả tiếng Nhật và tiếng Anh đó nha~")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()

    if ctx.guild.id in queues:
        workers[ctx.guild.id].cancel()
        del workers[ctx.guild.id]
        del queues[ctx.guild.id]

    await ctx.send("👋 Tớ đi nha~")

# ================= MESSAGE =================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    if not message.guild:
        return

    vc = message.guild.voice_client
    if not vc:
        return

    if not message.author.voice:
        return

    if message.author.voice.channel != vc.channel:
        return

    text = message.content.strip()

    if not should_read(text):
        return

    if message.guild.id in queues:
        await queues[message.guild.id].put(text)

# ================= READY =================

@bot.event
async def on_ready():
    print(f"✅ Bot Đa Ngôn Ngữ Tối Ưu đã sẵn sàng: {bot.user}")

keep_alive() 
bot.run(TOKEN)