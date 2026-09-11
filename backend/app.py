# AI 电台主持人 v2 · 后端 (FastAPI 单文件)
# 主题化节目 / 生动口播 / 点歌互动 / 栏目包装 / 防重复
# 曲库来自在线音乐代理; DeepSeek 编排; 本地 TTS/Qwen/MiniMax/edge-tts 合成口播
import asyncio
import base64
import contextlib
import csv
import hashlib
import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRoute
import aiohttp
from pydantic import BaseModel, Field
from typing import Annotated

try:
    from recommendations import select_songs, track_key
    from speech_audio import normalize_speech
    from music_sources import resolve_song_async, proxy_availability, catalog_match, identity, availability_notice, SOURCES, IDENTIFIER
except ModuleNotFoundError:
    from backend.recommendations import select_songs, track_key
    from backend.speech_audio import normalize_speech
    from backend.music_sources import resolve_song_async, proxy_availability, catalog_match, identity, availability_notice, SOURCES, IDENTIFIER

# ---------------- 配置 ----------------
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY", "").strip()
# Command Code 提供 OpenAI 兼容的 DeepSeek 路由
DEEPSEEK_BASE = os.getenv("DEEPSEEK_BASE", "https://api.commandcode.ai/provider/v1").rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-v4.1-flash")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "").strip()
DASHSCOPE_BASE = os.getenv("DASHSCOPE_BASE", "https://dashscope.aliyuncs.com/api/v1").rstrip("/")
QWEN_TTS_MODEL = os.getenv("QWEN_TTS_MODEL", "qwen3-tts-instruct-flash")
QWEN_TTS_VOICE = os.getenv("QWEN_TTS_VOICE", "Cherry")
QWEN_TTS_INSTRUCTIONS = os.getenv(
    "QWEN_TTS_INSTRUCTIONS", "温暖亲切、自然松弛，中速，吐字清晰，像真实电台主持人")
LOCAL_TTS_URL = os.getenv("LOCAL_TTS_URL", "").rstrip("/")
LOCAL_TTS_CACHE_ID = os.getenv("LOCAL_TTS_CACHE_ID", "sherpa-melo-zh-en-v1")
LOCAL_TTS_TIMEOUT = max(1.0, float(os.getenv("LOCAL_TTS_TIMEOUT", "60")))
LOCAL_TTS_SPEED = max(0.5, min(1.5, float(os.getenv("LOCAL_TTS_SPEED", "1.0"))))
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural")
MINIMAX_KEY = os.getenv("MINIMAX_KEY", "").strip()
MINIMAX_GROUP = os.getenv("MINIMAX_GROUP", "").strip()
MINIMAX_BASE = os.getenv("MINIMAX_BASE", "https://api.minimaxi.com").rstrip("/")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "speech-02-turbo")
MINIMAX_VOICE = os.getenv("MINIMAX_VOICE", "Chinese (Mandarin)_Warm_Girl")
MINIMAX_VOICE_SETTING = {"voice_id": MINIMAX_VOICE, "speed": 1.0, "vol": 1.0, "pitch": 0}
MINIMAX_AUDIO_SETTING = {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1}
NAS_LIST_URL = os.getenv("NAS_LIST_URL", "http://127.0.0.1:8001/songs.txt")
NAS_BASE_URL = os.getenv("NAS_BASE_URL", "http://127.0.0.1:8001")
HOST_NAME = os.getenv("HOST_NAME", "小蓝")
RADIO_BASE = os.getenv("RADIO_BASE", "http://127.0.0.1:8100").rstrip("/")

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
VOICE_DIR = DATA_DIR / "voice"
VOICE_DIR.mkdir(parents=True, exist_ok=True)

PROFILE_FILE = DATA_DIR / "profile.json"
VISITS_DB = DATA_DIR / "visits.sqlite3"

def visit_day():
    """访问统计固定按东八区自然日切分。"""
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date().isoformat()

def record_visit(token):
    visitor_hash = hashlib.sha256(f"tingjian:{token}".encode("utf-8")).hexdigest()
    day = visit_day()
    with contextlib.closing(sqlite3.connect(VISITS_DB, timeout=5)) as conn:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS visits ("
            "day TEXT NOT NULL, visitor_hash TEXT NOT NULL, "
            "PRIMARY KEY (day, visitor_hash))"
        )
        conn.execute(
            "INSERT OR IGNORE INTO visits (day, visitor_hash) VALUES (?, ?)",
            (day, visitor_hash),
        )
        conn.commit()
        today = conn.execute("SELECT COUNT(*) FROM visits WHERE day = ?", (day,)).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
    return today, total

def load_profile():
    """听众口味画像 (由网易云数据归纳), 文件缺失返回空 dict"""
    try:
        return json.loads(PROFILE_FILE.read_text("utf-8"))
    except Exception:
        return {}

def profile_hint(profile):
    if not profile:
        return ""
    st = "、".join(profile.get("styles", [])[:6]) or "多样"
    ar = "、".join(profile.get("artists", [])[:8]) or "—"
    ln = "、".join(profile.get("langs", [])[:4]) or "—"
    desc = profile.get("desc", "")
    return (f"听众口味画像：{desc}\n偏好风格：{st}；常听：{ar}；语种：{ln}。"
            "选歌与口播请尽量贴近听众口味；歌单内没有强匹配时，选风格接近的并自然过渡。")


class ConnectedRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def connected(request):
            if request.url.path not in {"/api/show", "/api/intent", "/api/chat", "/api/playback/resolve"}:
                return await handler(request)
            await request.body()
            task = asyncio.create_task(handler(request))
            try:
                while not task.done():
                    if await request.is_disconnected():
                        task.cancel()
                        return Response(status_code=499)
                    await asyncio.wait({task}, timeout=0.1)
                return await task
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        return connected


app = FastAPI(title="听间 Tingjian · AI 音乐电台")
app.router.route_class = ConnectedRoute

# ---------------- 主题与包装 ----------------
THEMES = [
    {"name": "怀旧金曲", "slogan": "把旧时光唱给你听", "brief": "经典、回忆与故事，适合娓娓道来"},
    {"name": "午后咖啡", "slogan": "忙里偷闲的一杯歌", "brief": "轻松治愈、不赶时间"},
    {"name": "元气早班", "slogan": "把好心情叫醒", "brief": "轻快有活力，适合开启新一天"},
    {"name": "深夜安眠", "slogan": "让世界慢下来", "brief": "安静温柔，适合睡前收尾"},
    {"name": "城市漫游", "slogan": "陪你在路上", "brief": "都市感，像窗外掠过的风景"},
    {"name": "心情小站", "slogan": "此刻的你最想听什么", "brief": "随性真诚，贴近听众当下心情"},
]

def time_of_day():
    # 固定东八区 (容器默认 UTC)
    h = (datetime.utcnow().hour + 8) % 24
    if h < 6:   return "深夜时分", "夜已深，人们大多准备休息"
    if h < 11:  return "早晨", "一天刚开始，很多人还在通勤路上"
    if h < 14:  return "中午", "午休时间，大家需要一点喘息"
    if h < 18:  return "下午", "午后时光，适合陪一杯茶或咖啡"
    if h < 22:  return "晚上", "一天忙完，正适合放松听歌"
    return "深夜时分", "夜深人静，愿音乐陪你入睡"

# ---------------- 曲库 ----------------
def fetch_library():
    try:
        with urllib.request.urlopen(NAS_LIST_URL, timeout=8) as r:
            text = r.read().decode("utf-8")
    except Exception as e:
        raise HTTPException(502, f"无法读取在线曲库: {e}")
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 在线曲库扩展格式: <DeepSeek可见标题>TAB<实际rel>  (见 proxy 说明)
        if "\t" in line:
            title, rel = line.split("\t", 1)
            title = title.strip(); rel = rel.strip()
            if not rel:
                continue
            out.append({"rel": rel, "title": title})
            continue
        rel = line
        name = rel.rsplit("/", 1)[-1]
        title = re.sub(r"\.(mp3|wav|flac|m4a|aac)$", "", name, flags=re.I)
        title = re.sub(r"\[mqms\d*\]", "", title).strip()
        out.append({"rel": rel, "title": title})
    return enrich_library(out)


def enrich_library(library):
    """Attach independently curated scene tags only to identified catalog rows."""
    root = Path(__file__).resolve().parents[1]
    try:
        catalog = json.loads((root / "backend" / "recommendation_catalog.json").read_text("utf-8"))
        with (root / "musiclib" / "playlist.tsv").open(encoding="utf-8") as stream:
            rows = list(csv.reader((line for line in stream if not line.startswith("#")), delimiter="\t"))
        metadata = {}
        for row in rows:
            if len(row) < 3:
                continue
            title, artist = row[:2]
            source, sid = row[2:4] if len(row) >= 4 else ("netease", row[2])
            rel = f"s/{source}/{urllib.parse.quote(sid)}.mp3"
            key = f"{artist} - {title}"
            metadata[rel] = {"artist": artist, "themes": catalog.get("songs", {}).get(key, [])}
        return [dict(song, **metadata.get(song["rel"], {})) for song in library]
    except (OSError, ValueError, TypeError):
        return library

def song_url(rel):
    return NAS_BASE_URL.rstrip("/") + "/" + urllib.parse.quote(rel, safe="/")

def find_song(library, title):
    return catalog_match(library, title)


async def verify_song(song, exclude=()):
    return await resolve_song_async(NAS_LIST_URL, song, exclude)


def song_item(song, requested=False):
    lyric_title = identity(song).get("title", "")
    item = {"kind": "song", "url": song_url(song["rel"]) + "?stream=1",
            "title": song["title"], "text": "", "requested": requested}
    if lyric_title:
        item["lyric_title"] = lyric_title
    for field in ("artist", "source", "id", "lyric_id", "recommendation"):
        if field in song:
            item[field] = song[field]
    return item

# ---------------- LLM ----------------
PERSONA = (
    "你是音乐电台主持人，名叫{HOST}，声音亲切自然、说话像真实的人，不肉麻不油腻，"
    "少用网络烂梗，多用具体可感的描述。不编造歌名、歌手或音源可用性；"
    "节目编排只能使用指定歌单，主动点歌可按用户指定的歌名和歌手提交在线检索。"
    '每段口播 40~110 字。始终严格只输出 JSON。'
)

def llm_request(user_text, max_tokens=900):
    body = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "system", "content": PERSONA.replace("{HOST}", HOST_NAME)},
                     {"role": "user", "content": user_text}],
        "response_format": {"type": "json_object"},
        "temperature": 1.15,
        "max_tokens": max_tokens,
    }).encode()
    return urllib.request.Request(
        DEEPSEEK_BASE + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + DEEPSEEK_KEY})
def llm_json(user_text, max_tokens=900):
    with urllib.request.urlopen(llm_request(user_text, max_tokens), timeout=60) as r:
        data = json.loads(r.read().decode())
    return json.loads(data["choices"][0]["message"]["content"])


async def post_provider(req):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as client:
        async with client.post(req.full_url, data=req.data, headers=dict(req.header_items())) as response:
            response.raise_for_status()
            return await response.read()


async def llm_json_async(user_text, max_tokens=900):
    data = json.loads(await post_provider(llm_request(user_text, max_tokens)))
    return json.loads(data["choices"][0]["message"]["content"])

def template_show(library, theme, tod):
    show = []
    for index, song in enumerate(library):
        text = (f"{tod}，欢迎来到《{theme['name']}》，{theme['slogan']}。我是{HOST_NAME}。"
                if index == 0 else "让音乐继续陪伴你。")
        show.extend([{"type": "talk", "text": f"{text}接下来听《{song['title']}》。"},
                     {"type": "song", "title": song["title"], "rel": song["rel"]}])
    return show

# ---------------- TTS (本地主; Qwen/MiniMax/edge-tts 备用) ----------------
async def local_synth(text, path):
    if not LOCAL_TTS_URL:
        return False
    try:
        timeout = aiohttp.ClientTimeout(total=LOCAL_TTS_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as client:
            async with client.post(
                    f"{LOCAL_TTS_URL}/synthesize",
                    json={"text": text, "speed": LOCAL_TTS_SPEED}) as response:
                response.raise_for_status()
                audio_data = await response.read()
        if not audio_data:
            raise ValueError("empty local TTS response")
        normalized_audio = await asyncio.to_thread(normalize_speech, audio_data)
        Path(path).write_bytes(normalized_audio)
        return True
    except Exception as e:
        print("Local TTS 失败:", type(e).__name__, str(e)[:160])
        return False


async def _download_audio(url):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45)) as client:
        async with client.get(url) as response:
            response.raise_for_status()
            data = await response.read()
    if not data:
        raise ValueError("empty audio response")
    return data


def _audio_bytes_from_data(value):
    encoded = str(value or "").strip()
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    if not encoded:
        raise ValueError("empty audio data")
    return base64.b64decode(encoded)


async def qwen_synth(text, path):
    body = json.dumps({
        "model": QWEN_TTS_MODEL,
        "input": {
            "text": text,
            "voice": QWEN_TTS_VOICE,
            "language_type": "Chinese",
            "instructions": QWEN_TTS_INSTRUCTIONS,
        },
    }, ensure_ascii=False).encode()
    req = urllib.request.Request(
        f"{DASHSCOPE_BASE}/services/aigc/multimodal-generation/generation",
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + DASHSCOPE_API_KEY})
    data = b""
    try:
        data = await post_provider(req)
        payload = json.loads(data.decode("utf-8"))
        audio = payload.get("output", {}).get("audio") or {}
        if audio.get("data"):
            audio_data = await asyncio.to_thread(_audio_bytes_from_data, audio["data"])
        elif audio.get("url"):
            audio_data = await _download_audio(audio["url"])
        else:
            print("Qwen TTS 无音频:", payload.get("code") or "missing output.audio")
            return False
        normalized_audio = await asyncio.to_thread(normalize_speech, audio_data)
        Path(path).write_bytes(normalized_audio)
        return True
    except Exception as e:
        print("Qwen TTS 失败:", type(e).__name__, str(e)[:160])
        return False


async def minimax_synth(text, path):
    body = json.dumps({
        "model": MINIMAX_MODEL, "text": text, "stream": False,
        "voice_setting": MINIMAX_VOICE_SETTING,
        "audio_setting": MINIMAX_AUDIO_SETTING,
    }).encode()
    url = f"{MINIMAX_BASE}/v1/t2a_v2"
    if MINIMAX_GROUP:
        url += f"?GroupId={MINIMAX_GROUP}"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + MINIMAX_KEY})
    try:
        data = await post_provider(req)
    except Exception as e:
        print("MiniMax 失败:", e)
        return False
    try:
        j = json.loads(data.decode("utf-8"))
        if j.get("base_resp", {}).get("status_code") != 0:
            print("MiniMax 业务错误:", j.get("base_resp")); return False
        hexaudio = j.get("data", {}).get("audio", "")
        if not hexaudio:
            print("MiniMax 无 audio:", str(j)[:200]); return False
        normalized_audio = await asyncio.to_thread(normalize_speech, bytes.fromhex(hexaudio))
        Path(path).write_bytes(normalized_audio)
        return True
    except Exception as e:
        print("MiniMax 解析失败:", e, str(data[:160])); return False

async def tts_to_mp3(text, path):
    if LOCAL_TTS_URL and await local_synth(text, str(path)):
        return True
    if DASHSCOPE_API_KEY:
        # 静默重试最多 3 次 (不通报), 偶发失败/限流可恢复
        for attempt in range(3):
            if await qwen_synth(text, str(path)):
                return True
            await asyncio.sleep(0.4)
        print("Qwen TTS 3 次失败, 尝试备用渠道")
    if MINIMAX_KEY:
        for attempt in range(3):
            if await minimax_synth(text, str(path)):
                return True
            await asyncio.sleep(0.4)
        print("MiniMax 3 次失败, 尝试备用渠道")
    try:
        import edge_tts
        await edge_tts.Communicate(text, EDGE_TTS_VOICE).save(str(path))
        normalized = await asyncio.to_thread(normalize_speech, Path(path).read_bytes())
        Path(path).write_bytes(normalized)
        return True
    except Exception as e:
        print("TTS 失败:", e)
        return False

# ---------------- 固定串场语音 (失败兜底, 预生成缓存) ----------------
FALLBACK_LINES = [
    "好的，我们继续听歌吧。",
    "音乐还在继续，让我们接着听。",
    "嗯，说得好，我们继续享受音乐。",
]
_fb_lock = asyncio.Lock()
_fb_ready = None      # None=未初始化, True/False
_fb_round = 0         # 轮换用

ANNOUNCEMENT_LINES = {
    "unavailable": "没有找到这首歌相符的可用音源，接下来尝试下一首推荐。",
    "limited": "音源检索遇到调用限额，已停止新的检索请求。接下来尝试已有的推荐歌曲；没有可播歌曲时，等待额度恢复后自动继续。",
    "temporary": "音源服务暂时没有响应，检索尚未完成。接下来尝试下一首推荐。",
    "waiting": "目前没有可播放的歌曲，正在等待音源服务或调用额度恢复，稍后会自动继续播放推荐歌曲。",
}
COOLDOWN_LINES = (
    {"id": "mood1", "title": "给心情留一点空白", "period": "any", "text": "趁着音乐稍作休息，也给此刻的心情留一点空白。开心不必急着解释，疲惫也不用马上振作。把肩膀放松下来，慢慢呼吸，等一会儿，我们继续听歌。"},
    {"id": "mood2", "title": "今天已经走了很远", "period": "any", "text": "如果今天有些事情没有按计划发生，也没关系。能走到现在，你已经处理了许多大大小小的事。先把未完成的念头放在一旁，让这几分钟只属于自己。"},
    {"id": "breath1", "title": "三次舒缓呼吸", "period": "any", "text": "我们做三次舒缓的呼吸。慢慢吸气，停一停，再缓缓呼出。第二次，把注意力放在呼吸上。最后一次，放松眉间和肩颈，让身体找到舒服的位置。"},
    {"id": "breath2", "title": "听一听身边的声音", "period": "any", "text": "现在可以听一听身边最近的声音，再听一听稍远的声音。不必判断它们，只要让声音经过。短暂地回到当下，也是一种很好的休息。"},
    {"id": "weather1", "title": "如果窗外正在下雨", "period": "any", "text": "如果窗外正在下雨，可以听一会儿雨点落下的节奏；如果没有下雨，也可以想起某个雨天。天气会变化，心情也会流动，不必把此刻变成永远。"},
    {"id": "weather2", "title": "如果今天阳光很好", "period": "any", "text": "如果今天阳光很好，稍后不妨去窗边看一眼；如果天空阴着，也可以给自己留一盏温暖的灯。无论外面是什么天气，都愿你此刻感到安稳。"},
    {"id": "morning", "title": "早晨的一点从容", "period": "morning", "text": "早上好。新的一天不必一开始就跑得很快，先整理呼吸，再挑一件最值得做的事。其余的事情，可以一件一件来。音乐很快就会回来。"},
    {"id": "evening", "title": "把今天轻轻放下", "period": "evening", "text": "夜晚适合把白天的声音慢慢放低。做得好的事情值得记住，没有完成的事情留给明天。现在让眼睛和肩膀都松一点，陪自己安静片刻。"},
)


def _cooldown_revision(qwen_model=QWEN_TTS_MODEL, qwen_voice=QWEN_TTS_VOICE,
                       qwen_instructions=QWEN_TTS_INSTRUCTIONS,
                       model=MINIMAX_MODEL, voice_setting=MINIMAX_VOICE_SETTING,
                       audio_setting=MINIMAX_AUDIO_SETTING, lines=COOLDOWN_LINES,
                       local_url=LOCAL_TTS_URL, local_cache_id=LOCAL_TTS_CACHE_ID,
                       local_speed=LOCAL_TTS_SPEED):
    contract = {"qwen_model": qwen_model, "qwen_voice": qwen_voice,
                "qwen_instructions": qwen_instructions, "model": model,
                "voice_setting": voice_setting, "audio_setting": audio_setting,
                "edge_voice": EDGE_TTS_VOICE, "lines": lines}
    if local_url:
        contract["local_tts"] = {
            "url": local_url,
            "cache_id": local_cache_id,
            "speed": local_speed,
        }
    digest = hashlib.sha256(json.dumps(contract, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    return f"v1-{digest}"


COOLDOWN_CONTENT_VERSION = _cooldown_revision()
_announcement_task = None


def _cooldown_path(asset_id):
    return VOICE_DIR / f"cooldown_{COOLDOWN_CONTENT_VERSION}_{asset_id}.mp3"


def _announcement_path(reason):
    return VOICE_DIR / f"notice_{COOLDOWN_CONTENT_VERSION}_{reason}.mp3"


def _fallback_path(index):
    return VOICE_DIR / f"fb_{COOLDOWN_CONTENT_VERSION}_{index}.mp3"


async def prepare_playback_audio():
    # Generate once at startup, never as part of a failure or cooldown loop.
    for reason, text in ANNOUNCEMENT_LINES.items():
        path = _announcement_path(reason)
        if not path.is_file() or not path.stat().st_size:
            await tts_to_mp3(text, path)
    if not (LOCAL_TTS_URL or DASHSCOPE_API_KEY or MINIMAX_KEY):
        return
    for item in COOLDOWN_LINES:
        path = _cooldown_path(item["id"])
        if not path.is_file() or not path.stat().st_size:
            await tts_to_mp3(item["text"], path)


@app.on_event("startup")
async def start_announcements():
    global _announcement_task
    _announcement_task = asyncio.create_task(prepare_playback_audio())


@app.on_event("shutdown")
async def stop_announcements():
    if _announcement_task:
        _announcement_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _announcement_task


@app.get("/api/playback/announcement/{reason}.mp3")
def announcement_file(reason: str):
    if reason not in ANNOUNCEMENT_LINES:
        raise HTTPException(404)
    path = _announcement_path(reason)
    if not path.is_file() or not path.stat().st_size:
        raise HTTPException(503, "播报缓存准备中", headers={"Retry-After": "30"})
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/playback/cooldown/content.json")
def cooldown_content():
    items = []
    for item in COOLDOWN_LINES:
        path = _cooldown_path(item["id"])
        if path.is_file() and path.stat().st_size:
            items.append({**item, "url": f"/api/playback/cooldown/{COOLDOWN_CONTENT_VERSION}/{item['id']}.mp3"})
    return {"version": COOLDOWN_CONTENT_VERSION, "items": items}


@app.get("/api/playback/cooldown/{version}/{asset_id}.mp3")
def cooldown_audio(version: str, asset_id: str):
    known = {item["id"] for item in COOLDOWN_LINES}
    if version != COOLDOWN_CONTENT_VERSION or asset_id not in known:
        raise HTTPException(404)
    path = _cooldown_path(asset_id)
    if not path.is_file() or not path.stat().st_size:
        raise HTTPException(503, "冷却内容缓存准备中", headers={"Retry-After": "30"})
    return FileResponse(path, media_type="audio/mpeg",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/api/playback/availability")
async def playback_availability():
    return await proxy_availability(NAS_LIST_URL)

async def ensure_fallback_voice():
    """确保至少一条固定串场语音可用; 返回是否可用"""
    global _fb_ready
    if _fb_ready is not None:
        return _fb_ready
    async with _fb_lock:
        if _fb_ready is not None:
            return _fb_ready
        ok = False
        if LOCAL_TTS_URL or DASHSCOPE_API_KEY or MINIMAX_KEY:
            for i, line in enumerate(FALLBACK_LINES):
                if await tts_to_mp3(line, _fallback_path(i)):
                    ok = True
                    break
        _fb_ready = ok
        print("固定串场语音就绪:", ok)
        return ok

def pick_fallback_url():
    global _fb_round
    n = len(FALLBACK_LINES)
    for _ in range(n):
        i = _fb_round % n
        _fb_round += 1
        path = _fallback_path(i)
        if path.is_file() and path.stat().st_size:
            return f"/voice/{path.name}"
    return None

# ---------------- 组节目 ----------------
def _cleanup_old_voice():
    """语音文件超过 240 个时删最老, 防磁盘膨胀 (固定串场 fb_* 保留)"""
    try:
        files = sorted(VOICE_DIR.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
        if len(files) > 240:
            for f in files[: len(files) - 200]:
                if f.name.startswith(("fb_", "notice_")) or f.name.startswith(f"cooldown_{COOLDOWN_CONTENT_VERSION}_"):
                    continue
                f.unlink(missing_ok=True)
    except Exception as e:
        print("cleanup:", e)

async def segments_to_items(library, segments, key, add_song_fallback=True):
    items, talks = [], []
    talk_idx = 0
    for seg in segments:
        kind = seg.get("type")
        if kind == "talk":
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            fname = f"{key}_{talk_idx:02d}.mp3"
            talk_idx += 1
            talks.append((fname, text))
            items.append({"kind": "talk", "url": f"/voice/{fname}", "text": text,
                          "title": "主持人", "ok": False})
        elif kind == "song":
            title = (seg.get("title") or "").strip()
            hit = (next((song for song in library if song["rel"] == seg["rel"]), None)
                   if "rel" in seg else find_song(library, title))
            if not hit:
                print("歌单中未找到:", title)
                continue
            if not hit.get("_verified"):
                result = await verify_song(hit)
                hit = result.get("song")
            if hit:
                items.append(song_item(hit, requested=seg.get("requested", False)))
    if add_song_fallback and not any(i["kind"] == "song" for i in items) and library:
        result = await verify_song(library[0])
        if result.get("song"):
            items.append(song_item(result["song"]))
    async def do_tts(fname, text):
        return fname, await tts_to_mp3(text, VOICE_DIR / fname)
    if talks:
        _cleanup_old_voice()
        results = await asyncio.gather(*[do_tts(f, t) for f, t in talks])
        okmap = dict(results)
        fb_avail = await ensure_fallback_voice()
        for it in items:
            if it["kind"] == "talk":
                fname = it["url"].rsplit("/", 1)[-1]
                if not okmap.get(fname, False):
                    fb = pick_fallback_url() if fb_avail else None
                    if fb:
                        it["url"] = fb      # 固定串场语音顶上, 节目照常继续
                        it["text"] = ""     # 播固定语, 不展示原稿
                    else:
                        it["kind"] = "text"  # 极端兜底: 纯文稿
                        it.pop("url", None)
    return items

async def make_show(library, theme, tod, tod_note, exclude, recommendation=None):
    songs, recommendation_meta = select_songs(
        library, theme["name"], exclude, recommendation, load_profile())
    if not songs:
        raise HTTPException(422, "没有可推荐歌曲，请调整少推荐列表或换一首作为推荐起点")
    songs, checks = await verify_recommendations(library, songs, theme, exclude, recommendation)
    if not songs:
        status = "limited" if "limited" in checks else "temporary" if "temporary" in checks else "unavailable"
        quota = await playback_availability() if status == "limited" else {}
        raise HTTPException(429 if status == "limited" else 503 if status == "temporary" else 422,
                            {"status": status, "notice": availability_notice(status, "本期候选歌曲"),
                             "retry_after": max(1, int(quota.get("retry_after", 30)))})
    recommendation_meta["count"] = len(songs)
    recommendation_meta["availability_checked"] = True
    failed = sum(status != "available" for status in checks)
    if failed:
        notice = (f"已跳过 {failed} 首暂未验证可播的候选，本期包含 {len(songs)} 首已验证歌曲。")
        recommendation_meta["notice"] = "；".join(filter(None, [recommendation_meta.get("notice"), notice]))
    titles = json.dumps([song["title"] for song in songs], ensure_ascii=False)
    user = (f"现在是{theme['name']}时段：{tod}，{tod_note}。本期栏目《{theme['name']}》，"
            f"口号：{theme['slogan']}。风格：{theme['brief']}。"
            f"节目选歌已经完成，以下歌曲及顺序不可更改：{titles}。"
            "请按这个顺序为每首歌写一句自然的口播引介，第一句兼作开场。"
            "可以围绕栏目情境表达感受，不要编造歌词、歌曲年代、声学特征或听众偏好。"
            '只输出 JSON: {"introductions":["第一首引介", "第二首引介"],"closing":"简短结束语"}。'
            f"introductions 必须恰好有 {len(songs)} 条，closing 可为空字符串。")
    try:
        raw = await llm_json_async(user)
        introductions = raw.get("introductions")
        if not isinstance(introductions, list) or len(introductions) != len(songs):
            # Accept the older response shape only when its exact song order is
            # already the selected order. It cannot introduce or duplicate songs.
            legacy = raw.get("show", [])
            if not isinstance(legacy, list) or any(not isinstance(seg, dict) for seg in legacy):
                raise ValueError("invalid narration")
            if [seg.get("title") for seg in legacy if seg.get("type") == "song"] != [song["title"] for song in songs]:
                raise ValueError("narration changed selected songs")
            introductions = [seg.get("text") for seg in legacy if seg.get("type") == "talk"]
        if len(introductions) != len(songs) or any(not isinstance(text, str) or not text.strip() or len(text) > 1000 for text in introductions):
            raise ValueError("invalid narration length")
        segments = []
        for song, text in zip(songs, introductions):
            segments.extend([{"type": "talk", "text": text.strip()},
                             {"type": "song", "title": song["title"], "rel": song["rel"]}])
        closing = raw.get("closing", "")
        if isinstance(closing, str) and closing.strip() and len(closing) <= 1000:
            segments.append({"type": "talk", "text": closing.strip()})
        recommendation_meta["narration_fallback"] = False
    except Exception as e:
        print("LLM 口播失败, 用模板:", type(e).__name__)
        segments = template_show(songs, theme, tod)
        recommendation_meta["narration_fallback"] = True
    items = await segments_to_items(songs, segments, f"s{int(__import__('time').time()*1000)}", add_song_fallback=False)
    return {"meta": {"theme": theme["name"], "slogan": theme["slogan"],
                     "time": tod, "recommendation": recommendation_meta}, "items": items}


async def verify_recommendations(library, candidates, theme, exclude, recommendation):
    """Validate before narration; refill only within the same preference rules."""
    verified, statuses, tried = [], [], set()
    deadline = time.monotonic() + 60
    target = len(candidates)
    while candidates and len(verified) < target:
        remaining = deadline - time.monotonic()
        if remaining < 2:
            statuses.append("temporary")
            break
        batch = candidates[:target - len(verified)]
        tried.update(song["rel"] for song in batch)
        tasks = [asyncio.create_task(verify_song(song)) for song in batch]
        try:
            done, pending = await asyncio.wait(tasks, timeout=remaining)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        for task in tasks:
            if task in pending:
                task.cancel()
                statuses.append("temporary")
                continue
            result = task.result()
            statuses.append(result["status"])
            if result.get("song"):
                verified.append(result["song"])
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if "limited" in statuses or time.monotonic() >= deadline:
            break
        used = {track_key(song) for song in verified}
        available = [song for song in library if song["rel"] not in tried and track_key(song) not in used]
        candidates, _ = select_songs(available, theme["name"], exclude, recommendation,
                                     load_profile(), count=target - len(verified)) if available and len(verified) < target else ([], {})
    return verified, statuses

SongTitle = Annotated[str, Field(max_length=500)]

class RecommendationReq(BaseModel):
    personalize: bool = False
    favorites: list[SongTitle] = Field(default_factory=list, max_length=100)
    history: list[SongTitle] = Field(default_factory=list, max_length=100)
    disliked: list[SongTitle] = Field(default_factory=list, max_length=100)
    seed: SongTitle = ""

class ShowReq(BaseModel):
    exclude: list[SongTitle] = Field(default_factory=list, max_length=100)
    theme: str = Field(default="", max_length=100)
    recommendation: RecommendationReq = Field(default_factory=RecommendationReq)

@app.post("/api/show")
async def api_show(req: ShowReq):
    library = await asyncio.to_thread(fetch_library)
    if not library:
        raise HTTPException(502, "曲库为空")
    tod, tod_note = time_of_day()
    theme = next((t for t in THEMES if t["name"] == req.theme), None) or \
            __import__("random").choice(THEMES)
    return await make_show(library, theme, tod, tod_note, req.exclude, req.recommendation.model_dump())

class ChatReq(BaseModel):
    message: str = Field(default="", max_length=1000)
    exclude: list[SongTitle] = Field(default_factory=list, max_length=100)

@app.post("/api/chat")
async def api_chat(req: ChatReq):
    result = await api_intent(IntentReq(message=req.message, exclude=req.exclude))
    if result.get("notice"):
        result["items"] = [{"kind": "text", "title": "点歌提示", "text": result["notice"]}]
    return result

class IntentReq(BaseModel):
    message: str = Field(default="", max_length=1000)
    exclude: list[SongTitle] = Field(default_factory=list, max_length=100)
    state: dict = Field(default_factory=dict)


class SourceRef(BaseModel):
    source: str = Field(pattern="^(" + "|".join(sorted(SOURCES)) + ")$")
    id: str = Field(pattern=r"^[A-Za-z0-9_+=.-]{1,200}$")


class PlaybackResolveReq(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    artist: str = Field(default="", max_length=200)
    source: str = Field(default="", max_length=20)
    id: str = Field(default="", max_length=200)
    exclude: list[SourceRef] = Field(default_factory=list, max_length=40)


@app.post("/api/playback/resolve")
async def api_playback_resolve(req: PlaybackResolveReq):
    if req.source and (req.source not in SOURCES or not IDENTIFIER.fullmatch(req.id)):
        raise HTTPException(422, "音源标识无效")
    song = {"title": req.title, "artist": req.artist}
    if req.source:
        song.update(source=req.source, id=req.id)
    result = await verify_song(song, [entry.model_dump() for entry in req.exclude])
    response = {key: result[key] for key in ("status", "searched", "retry_after") if key in result}
    if result.get("song"):
        response["item"] = song_item(result["song"])
    else:
        response["notice"] = availability_notice(result["status"], req.title)
    return response

INTENT_ACTIONS = (
    '可用动作(按需选多个, 都可不填): '
    '[{"type":"play_song","title":"歌名或歌单标题","artist":"用户指定歌手或空字符串"}] 在线点歌，歌单外也可检索; '
    '[{"type":"play_theme","theme":"主题名"}] 换成某主题开新一期; '
    '{"type":"pause"} / {"type":"resume"} / {"type":"next"} / {"type":"prev"} / '
    '{"type":"stop"} / {"type":"set_auto","on":true或false}; '
    '纯聊天可不带动作。reply 是你要开口说的话(即便有动作也说一句配合), '
    '没有话说就回空字符串。'
)

@app.post("/api/intent")
async def api_intent(req: IntentReq):
    try:
        library = await asyncio.to_thread(fetch_library)
    except HTTPException:
        library = []
    msg = (req.message or "").strip()
    if not msg:
        raise HTTPException(400, "empty")
    st = req.state or {}
    cur = st.get("current") or "无"
    playing = "播放中" if st.get("playing") else "未在播放"
    paused = "，暂停着" if st.get("paused") else ""
    theme = st.get("theme") or "无"
    automode = "开" if st.get("auto") else "关"
    themes = "、".join(t["name"] for t in THEMES)
    titles = "\n".join(f"- {song['title']}" for song in library)
    user = (f"你是{HOST_NAME}。现在电台状态：{playing}{paused}，正在播：「{cur}」，"
            f"当前主题：{theme}，自动广播：{automode}。\n"
            f"听众说：「{msg}」。请判断听众意图并决定动作（点歌/换主题/播放控制/闲聊等）。\n"
            f"可用主题名：{themes}\n"
            f"可用动作：{INTENT_ACTIONS}\n"
            f"注意：听众说「下一首/上一首/跳过/暂停/继续/停止」等是在操作播放器，必须输出对应控制动作，不要自己选歌。\n"
            "用户明确点歌时，即使歌单外也输出 play_song 并保留歌名、歌手、现场或其他版本要求；"
            "没有指定歌手就留空，不猜原唱。不承诺找到或播放成功，系统会实际检索验证。\n"
            f"可选歌单:\n{titles}\n\n"
            '输出 JSON: {"reply":"口播文本或空","actions":[动作对象...]}')
    quoted = re.fullmatch(r"(?:请|帮我|麻烦)?\s*(?:播放|点播|放|我想听|想听|听)\s*《([^》]{1,500})》[。！!\s]*", msg)
    try:
        raw = ({"actions": [{"type": "play_song", "title": quoted.group(1), "artist": ""}]}
               if quoted else await llm_json_async(user, max_tokens=700))
    except Exception as e:
        print("intent LLM 失败:", e)
        raw = {"reply": f"嗯，你说的是「{msg}」吗？我接着放歌陪你。", "actions": []}
    if not isinstance(raw, dict):
        raw = {}
    reply = str(raw.get("reply") or "").strip()
    actions = raw.get("actions") if isinstance(raw.get("actions"), list) else []

    segs = []
    if reply:
        segs.append({"type": "talk", "text": reply})
    valid_actions = []
    notice, availability = "", ""
    retry_after = 0
    song_requests = 0
    for a in actions:
        if not isinstance(a, dict):
            continue
        t = a.get("type")
        if t == "play_song":
            title = str(a.get("title") or "").strip()[:500]
            artist = str(a.get("artist") or "").strip()[:200]
            if not title or song_requests:
                continue
            song_requests += 1
            hit = catalog_match(library, title, artist)
            result = await verify_song(hit or {"title": title, "artist": artist})
            availability = result["status"]
            retry_after = result.get("retry_after", 30 if availability in ("limited", "temporary") else 0)
            if result.get("song"):
                hit = result["song"]
                library = [hit]
                segs = [{"type": "talk", "text": f"找到《{hit['title']}》的可用音源了，接下来听这首。"},
                        {"type": "song", "title": hit["title"], "rel": hit["rel"], "requested": True}]
            else:
                notice = availability_notice(availability, f"{artist} - {title}" if artist else title)
                # A deterministic visible reply cannot be lost to a TTS fallback.
                segs = []
                valid_actions.append({"type": "next"})
        elif t in ("pause", "resume", "next", "prev", "stop"):
            valid_actions.append({"type": t})
        elif t == "set_auto":
            valid_actions.append({"type": t, "on": bool(a.get("on"))})
        elif t == "play_theme":
            nm = (a.get("theme") or "").strip()
            if any(x["name"] == nm for x in THEMES):
                valid_actions.append({"type": t, "theme": nm})
    # 控制类意图只保留口播, 不带歌曲 (否则会等歌放完才执行控制)
    has_control = any(a["type"] in ("pause","resume","next","prev","stop") for a in valid_actions)
    if has_control:
        segs = [s for s in segs if s["type"] == "talk"]
    items = await segments_to_items(library, segs, f"c{int(__import__('time').time()*1000)}", add_song_fallback=False) \
            if segs else []
    response = {"items": items, "actions": valid_actions}
    if notice:
        response.update(notice=notice, availability=availability, retry_after=retry_after)
    return response


ALARM_FILE = DATA_DIR / "alarm.json"

def read_alarm():
    try:
        return json.loads(ALARM_FILE.read_text("utf-8"))
    except Exception:
        return {"enabled": False, "time": "07:30"}

class AlarmReq(BaseModel):
    enabled: bool = False
    time: str = "07:30"

@app.get("/api/alarm")
def api_alarm_get():
    a = read_alarm()
    a["server_time"] = datetime.utcnow().strftime("%H:%M")
    return a

@app.post("/api/alarm")
def api_alarm_set(req: AlarmReq):
    import re
    t = req.time.strip()
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
        raise HTTPException(400, "time 需为 HH:MM")
    ALARM_FILE.write_text(json.dumps({"enabled": bool(req.enabled), "time": t}, ensure_ascii=False), "utf-8")
    return {"saved": True}

# 电台播放列表短缓存: 闹钟/播放器刚拉过的整期在 5 分钟内直接复用,
# 避免每次现场调 DeepSeek+TTS (7~30s) 拖垮 EasyInput 的列表请求
_PLAYLIST_CACHE = {"t": 0.0, "text": ""}

NCM_API = os.getenv("NCM_API", "http://192.168.1.88:8300").rstrip("/")
LIKED_FILE = DATA_DIR / "liked_930.json"
NCM_COOKIE_FILE = DATA_DIR / "ncm_cookie.txt"

# 网易云登录 cookie (VIP): 请求 /song/url 必须带, 否则返回 30~45s 试听片段.
# ncm_cookie.txt 是 curl 格式 jar, 需解析成 "k=v; k2=v2" 再作 Cookie header.
_ncm_cookie_cache = None
def _ncm_cookie_headers():
    global _ncm_cookie_cache
    if _ncm_cookie_cache is None:
        try:
            pairs = []
            for ln in NCM_COOKIE_FILE.read_text("utf-8", errors="ignore").splitlines():
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                parts = ln.split("\t")
                # jar 行: domain flag path secure expiry name value
                if len(parts) >= 7:
                    pairs.append(f"{parts[5]}={parts[6]}")
            _ncm_cookie_cache = "; ".join(pairs)
        except Exception:
            _ncm_cookie_cache = ""
    return {"Cookie": _ncm_cookie_cache} if _ncm_cookie_cache else {}

def _load_liked():
    """网易云'喜欢的音乐'池: [{id,title,artist}...], 文件缺失/异常返回 []"""
    try:
        return json.loads(LIKED_FILE.read_text("utf-8"))
    except Exception as e:
        print("liked 池加载失败:", e)
        return []

def _ncm_by_liked_id(song_id) -> str:
    """用池内已知 id 直接取 URL (比搜索准且快)"""
    return _ncm_song_url(song_id)

# ---------------- 连续混合电台 (本地曲库 + 网易云喜欢的音乐) ----------------
import random as _random
_RECENT_FILE = DATA_DIR / "radio_recent.json"
_EPISODE_CACHE = {"text": "", "t": 0.0}      # 当前一期 (播完请求 ?next=1 换新)
_RECENT_MAX = 60

def _load_recent():
    try:
        return json.loads(_RECENT_FILE.read_text("utf-8"))
    except Exception:
        return []

def _save_recent(recent):
    try:
        _RECENT_FILE.write_text(json.dumps(recent, ensure_ascii=False), "utf-8")
    except Exception:
        pass

def _norm(s: str) -> str:
    import re as _re
    s = _re.sub(r"[（(【\[].*?[）)】\]]", "", s)   # 去括号注释(歌手/版本)
    s = _re.sub(r"\[(本地|网易)\]", "", s)
    return re.sub(r"\s+", "", s or "").lower()

def _episode_candidates(library, liked, recent):
    """混合候选: 本地全部 + liked 随机抽样; 剔除近期播过. 返回 (候选列表[str], idx_map)"""
    recent_keys = {_norm(x.get("k", "")) for x in recent}
    cands = []
    idxmap = []      # (kind, obj)
    for s in library:
        title = s["title"]
        if _norm(title) in recent_keys:
            continue
        cands.append(f"[本地] {title}")
        idxmap.append(("local", s))
    pool = [t for t in liked if _norm(t.get("title", "")) not in recent_keys]
    _random.shuffle(pool)
    for t in pool[:14]:
        tag = f"{t['title']} — {t['artist']}" if t.get("artist") else t["title"]
        cands.append(f"[网易] {tag}")
        idxmap.append(("ncm", t))
    return cands, idxmap

def _resolve_candidate(local_lib, liked, kind, obj):
    """把 LLM 选中的一项解析为 (url, display) 或 None"""
    song = obj if kind == "local" else dict(obj, source="netease", id=str(obj["id"]))
    result = resolve_song(NAS_LIST_URL, song)
    if result.get("song"):
        item = song_item(result["song"])
        return item["url"], item["title"]
    return None

async def make_mixed_episode():
    """生成一期连续电台: 混合本地+网易云 liked, 返回纯文本行 (口播mp3 与 歌URL 交替)"""
    import time as _tt
    library = fetch_library()
    liked = _load_liked()
    recent = _load_recent()
    tod, tod_note = time_of_day()
    theme = _random.choice(THEMES) if library else THEMES[0]

    cands, idxmap = _episode_candidates(library, liked, recent)
    if not cands:
        cands = ["[本地] 暂无可用歌曲"]
        idxmap = []
    cand_text = "\n".join(cands[:60])
    ph = profile_hint(load_profile())
    user = (f"现在约{tod}，{tod_note}。给这台一直播放的床头电台编一期节目（《{theme['name']}》风格：{theme['brief']}）。"
            f"从下面候选里选 3~4 首歌（可本地可网易，尽量多样），每首歌前配一句自然口播引介，"
            f"开场先有一句暖场（可呼应听众口味画像），歌曲之间口播要连贯串场，像真电台。"
            f"口播 25~60 字，别啰嗦，别说空话。最近播过的不选（未出现在候选即已排除）。\n\n"
            f"{ph}\n候选:\n{cand_text}\n\n"
            '只输出 JSON: {"open":"开场白","items":[{"talk":"引介口播","title":"候选里原样标题"},...]}'
            f"\n\n(title 必须与上面候选行完全一致, 含 [本地]/[网易] 前缀)")
    try:
        raw = llm_json(user)
    except Exception as e:
        print("电台 LLM 失败, 走模板:", e)
        raw = {"open": f"{tod}，欢迎来到《{theme['name']}》。",
               "items": [{"talk": "先来一首。", "title": c} for c in cands[:2]]}

    # 组装 talk/歌 交替
    segs = []
    if raw.get("open"):
        segs.append(("talk", str(raw["open"])))
    chosen = 0
    for it in (raw.get("items") or [])[:8]:
        if chosen >= 4:
            break
        t = (it.get("title") or "").strip()
        if not t:
            continue
        # 找候选匹配 (归一化)
        best = None
        tn = _norm(t)
        for i, c in enumerate(cands):
            if _norm(c) == tn or (tn and tn in _norm(c)) or (_norm(c) and _norm(c) in tn):
                best = idxmap[i]; break
        if best is None:
            # 尝试本地标题包含
            hit = find_song(library, t.replace("[网易]", "").replace("[本地]", "").strip())
            if hit:
                best = ("local", hit)
            else:
                continue
        r = await asyncio.to_thread(_resolve_candidate, library, liked, best[0], best[1])
        if not r:
            continue
        u, disp = r
        if (it.get("talk") or "").strip():
            segs.append(("talk", str(it["talk"]).strip()))
        segs.append(("song", u, disp))
        chosen += 1

    if chosen == 0 and library:
        picks = _random.sample(library, min(3, len(library)))
        results = await asyncio.gather(*(verify_song(song) for song in picks))
        segs = [("talk", f"{tod}，欢迎回来。")]
        for result in results:
            if result.get("song"):
                item = song_item(result["song"])
                segs.append(("song", item["url"], item["title"]))
        if len(segs) == 1:
            raise HTTPException(503, "在线音源暂未通过校验，请稍后重试")

    # TTS (talk 段) + 更新防重
    key = f"r{int(_tt.time()*1000)}"
    lines = []
    talk_i = 0
    rec_add = []
    tasks = []
    fnames = []
    for seg in segs:
        if seg[0] == "talk":
            fn = f"{key}_{talk_i:02d}.mp3"
            talk_i += 1
            fnames.append(fn)
            tasks.append(tts_to_mp3(seg[1], VOICE_DIR / fn))
        else:
            tasks.append(None)
    if tasks:
        results = await asyncio.gather(*[x for x in tasks if x is not None])
        ri = 0
    for seg in segs:
        if seg[0] == "talk":
            fn = fnames[ri]; ok = results[ri] if ri < len(results) else False
            ri += 1
            if ok:
                lines.append(f"{RADIO_BASE}/voice/{fn}")
        else:
            lines.append(seg[1])
            if len(seg) > 2:
                rec_add.append({"k": seg[2]})
    # 记入防重 (保留最近 60)
    if rec_add:
        recent = (rec_add + recent)[:_RECENT_MAX]
        _save_recent(recent)
    text = "\n".join(lines)
    _EPISODE_CACHE.update(t=_tt.time(), text=text)
    return text

def _ncm_song_url(song_id) -> str:
    """从本机 NeteaseCloudMusicApi 取一首歌的可播 URL (带 VIP cookie).
    必须用 /song/url/v1?level=standard: 默认 /song/url 对 VIP 返回 FLAC,
    而 EasyInput 播放器只支持 MP3, FLAC 会无声/爆音."""
    try:
        req = urllib.request.Request(
            f"{NCM_API}/song/url/v1?id={song_id}&level=standard",
            headers=_ncm_cookie_headers())
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode())
        items = d.get("data") or []
        return (items[0].get("url") or "") if items else ""
    except Exception as e:
        print("ncm url fail:", e)
        return ""

def _ncm_search(title: str, artist: str = ""):
    """搜网易云, 返回 (song_id, 正式标题, 歌手) 或 None.
    artist 有值时优先找原唱/含该歌手的版本, 避免搜到翻唱."""
    import urllib.parse as _up
    try:
        kw = f"{title} {artist}".strip() if artist else title
        q = _up.quote(kw)
        req = urllib.request.Request(f"{NCM_API}/search?keywords={q}&limit=10",
                                     headers=_ncm_cookie_headers())
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode())
        songs = (d.get("result") or {}).get("songs") or []
        if not songs:
            return None
        def artists_of(s):
            return [a.get("name") or "" for a in (s.get("ar") or s.get("artists") or [])]
        if artist:
            # 优先歌手匹配(整名或主名含), 其次取第一条
            best = None
            for s in songs:
                as_ = artists_of(s)
                if any(artist in a or a in artist for a in as_):
                    best = s
                    break
            if best is None:
                best = songs[0]
            s = best
        else:
            s = songs[0]
        return s.get("id"), s.get("name") or title, "/".join(artists_of(s))
    except Exception as e:
        print("ncm search fail:", e)
        return None

def _ncm_resolve(title: str, artist: str = ""):
    """Compatibility helper; all new requests use the verified multi-source path."""
    result = resolve_song(NAS_LIST_URL, {"title": title, "artist": artist})
    if result.get("song"):
        return dict(song_item(result["song"]), artist_match=True, want_artist=artist)
    return None

@app.get("/api/radio/playlist")
async def api_radio_playlist(next_ep: int = 0):
    """连续混合电台: EasyInput 一期播完请求 ?next=1 生成新一期.
    无参: 返回当前一期 (首次调用自动生成). 每期 3~4 首歌(本地曲库+网易云喜欢池),
    歌间有主持人口播, 带防重."""
    if next_ep or not _EPISODE_CACHE["text"]:
        try:
            text = await make_mixed_episode()
        except Exception as e:
            print("电台生成异常:", e)
            if _EPISODE_CACHE["text"]:
                return Response(_EPISODE_CACHE["text"], media_type="text/plain; charset=utf-8")
            raise HTTPException(502, f"电台生成失败: {e}")
        return Response(text, media_type="text/plain; charset=utf-8")
    return Response(_EPISODE_CACHE["text"], media_type="text/plain; charset=utf-8")

# ---------------- 语音对讲 (S8 / ESP32) ----------------
# 语音识别后端 (sherpa-asr 容器, 已加入 radio_default 网络, 用容器名直连)
WHISPER_URL = os.getenv("WHISPER_URL", "http://sherpa-asr:8000").rstrip("/")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
TALK_IN_DIR = DATA_DIR / "talk_in"
TALK_IN_DIR.mkdir(parents=True, exist_ok=True)

# 简单 WAV 校验/信息: 返回 (sample_rate, channels, data_bytes) 或抛 400
def _wav_info(raw: bytes):
    if len(raw) < 44 or raw[0:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise HTTPException(400, "不是 WAV 文件")
    ch = int.from_bytes(raw[22:24], "little")
    rate = int.from_bytes(raw[24:28], "little")
    # 找 data 块
    pos = 12
    while pos + 8 <= len(raw):
        cid = raw[pos:pos + 4]
        sz = int.from_bytes(raw[pos + 4:pos + 8], "little")
        if cid == b"data":
            return rate, ch, min(sz, len(raw) - pos - 8)
        pos += 8 + sz
    raise HTTPException(400, "WAV 无 data 块")

def _whisper_transcribe(path: Path, lang: str = "zh") -> str:
    """调 faster-whisper 的 OpenAI 兼容 /v1/audio/transcriptions"""
    import uuid
    boundary = "----talk" + uuid.uuid4().hex
    parts = []
    with open(path, "rb") as f:
        audio = f.read()
    def field(name, value):
        return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                f"{value}\r\n").encode()
    parts.append(field("model", WHISPER_MODEL))
    parts.append(field("language", lang))
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                f"filename=\"talk.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode())
    parts.append(audio)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(WHISPER_URL + "/v1/audio/transcriptions", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode())
        return (data.get("text") or "").strip()
    except Exception as e:
        print("whisper 调用失败:", e)
        return ""

@app.post("/api/talk")
async def api_talk(request: Request):
    """ESP32 语音对讲: 收 16k mono WAV (raw body) -> whisper 转写 -> 主持人回应(TTS) ->
    返回纯文本列表(每行一个绝对 URL: 口播 mp3 + 可选歌曲), 供 EasyInput 顺序播放"""
    raw = await request.body()
    if len(raw) < 44 or len(raw) > 4 * 1024 * 1024:
        raise HTTPException(400, "音频大小异常")
    rate, ch, _ = _wav_info(raw)
    if rate != 16000 or ch != 1:
        raise HTTPException(400, f"需要 16kHz 单声道 WAV (收到 {rate}Hz {ch}ch)")

    import time as _time
    ts = int(_time.time() * 1000)
    in_path = TALK_IN_DIR / f"t{ts}.wav"
    in_path.write_bytes(raw)

    text = _whisper_transcribe(in_path)
    try:
        dbg = TALK_IN_DIR / "last.wav"      # 保留最近一次上传供诊断
        dbg.write_bytes(raw)
    except Exception:
        pass
    try:
        in_path.unlink()
    except Exception:
        pass

    final_lines = []
    library = fetch_library()
    if not text:
        # 识别失败: 固定一句话回应 (不走 LLM, 保证有反馈)
        import time as _tt2
        ts2 = int(_time.time() * 1000)
        fname = f"t{ts2}_00.mp3"
        if await tts_to_mp3("抱歉，我没有听清，能再说一次吗？", VOICE_DIR / fname):
            final_lines.append(f"{RADIO_BASE}/voice/{fname}")
        else:
            fb = pick_fallback_url()
            if fb:
                final_lines.append(fb)
    else:
        # ① ASR 纠错: 只做保守修正。绝不把不确定的音臆断成别的歌名/专有名词
        #    (否则识别错的“晴天/青天”会被脑补成另一首歌, 如“青花瓷”)。
        corrected = text
        try:
            fix_user = (f"语音识别把听众的话转成了下面这段(可能有同音错别字、断句或多余语气词)。"
                        f"请只纠正明显的同音错别字、断句和重复语气词，使句子通顺、意思不变。"
                        f"重要约束：语音不清、无法确定的字词保持原样，绝不猜测或替换。"
                        f"特别禁止：不要把不确定的音节脑补成你联想到的歌曲名/人名等专有名词——"
                        f"例如识别到“青天”时，绝不能改成“青花瓷”。尽量原样。\n\n"
                        f"识别文本：{text}\n\n"
                        '输出 JSON: {"fixed":"保守纠正后的原话(不确定就基本照抄)"}')
            raw_fix = llm_json(fix_user, max_tokens=300)
            if isinstance(raw_fix, dict):
                corrected = (raw_fix.get("fixed") or raw_fix.get("text") or "").strip()
            elif isinstance(raw_fix, str):
                corrected = raw_fix.strip()
            if not corrected:
                corrected = text
            if corrected != text:
                print(f"ASR 纠错: {text!r} -> {corrected!r}")
        except Exception as e:
            print("ASR 纠错失败(用原文):", e)

        titles = "\n".join(f"- {t}" for t in library[:80])
        user = (f"听众刚才对你说（语音识别结果，可能仍有同音字误差）：{text}\n\n"
                f"请以{HOST_NAME}的身份自然回应，口语化、简短（40~110字）。"
                f"如果听众是在点歌或暗示想听某首：优先从下方可选歌单里选；"
                f"歌单里没有的歌曲也可以点，歌名填在 song_title，我们会跨音源检索。"
                f"点歌时若歌名有同音字误差，请按歌手和常识推断出真实歌名再填——例如"
                f"“周杰伦的青天”应推断为周杰伦的《晴天》而非《青花瓷》。"
                f"歌手名也填进 artist 字段（听众提到或你能推断出原唱时），方便找原唱版本而非翻唱。\n\n"
                f"可选歌单(本地):\n{titles}\n\n"
                '输出 JSON: {"reply":"你要说出口播的一段话","song_title":"推断后的真实歌名(没点歌就空字符串)","artist":"原唱歌手名(听众提到或你推断出就填,否则空字符串)"}')
        try:
            raw_llm = llm_json(user, max_tokens=500)
        except Exception as e:
            print("talk LLM 失败:", e)
            raw_llm = {"reply": "嗯嗯，我在听，你接着说。", "song_title": ""}
        reply = (raw_llm.get("reply") or "").strip() or "嗯嗯，我在听。"
        st = str(raw_llm.get("song_title") or "").strip()[:500]
        ar = str(raw_llm.get("artist") or "").strip()[:200]
        verified = None
        if st:
            hit = catalog_match(library, st, ar)
            result = await verify_song(hit or {"title": st, "artist": ar})
            verified = result.get("song")
            reply = (f"找到《{verified['title']}》的可用音源了，接下来听这首。" if verified
                     else availability_notice(result["status"], st))
        import time as _tt
        key = f"t{ts}"
        fname = f"{key}_00.mp3"
        talk_ok = await tts_to_mp3(reply, VOICE_DIR / fname)
        items2 = []
        if talk_ok:
            items2.append({"kind": "talk", "url": f"{RADIO_BASE}/voice/{fname}"})
        else:
            fb = pick_fallback_url()
            if fb:
                items2.append({"kind": "talk", "url": fb})
        if verified:
            items2.append(song_item(verified, requested=True))
        final_lines = [it["url"] for it in items2 if it["kind"] in ("talk", "song")]

    if not final_lines:
        raise HTTPException(502, "无可用回应")
    return Response("\n".join(final_lines), media_type="text/plain; charset=utf-8")

@app.get("/api/themes")
def api_themes():
    return THEMES

class VisitReq(BaseModel):
    token: str = ""

@app.post("/api/visits")
def api_visits(req: VisitReq, response: Response):
    """匿名记录一次浏览器当日访问，不保存原始标识或 IP。"""
    token = req.token.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{8,128}", token):
        raise HTTPException(422, "访客标识无效")
    response.headers["Cache-Control"] = "no-store"
    try:
        today, total = record_visit(token)
    except sqlite3.Error as e:
        print("访问统计失败:", e)
        raise HTTPException(503, "访问统计暂不可用")
    return {"today": today, "total": total}

@app.get("/voice/{name}")
def voice_file(name: str):
    path = VOICE_DIR / name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/mpeg")

@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)   # 浏览器请求站点图标, 返回空即可

class RevalidatingStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        # Unversioned imports must revalidate too, including conditional 304s.
        if path in (".", "", "/") or Path(path).suffix in {".html", ".js", ".css"}:
            response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", RevalidatingStaticFiles(directory=str(Path(__file__).parent / "static"), html=True), name="web")
