# AI 电台主持人 v2 · 后端 (FastAPI 单文件)
# 主题化节目 / 生动口播 / 点歌互动 / 栏目包装 / 防重复
# 曲库来自在线音乐代理; DeepSeek 编排; MiniMax TTS (v2, audio 为 hex 字符串)
import asyncio
import csv
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Annotated

try:
    from recommendations import select_songs
    from speech_audio import normalize_speech
except ModuleNotFoundError:
    from backend.recommendations import select_songs
    from backend.speech_audio import normalize_speech

# ---------------- 配置 ----------------
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY", "").strip()
DEEPSEEK_BASE = os.getenv("DEEPSEEK_BASE", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
MINIMAX_KEY = os.getenv("MINIMAX_KEY", "").strip()
MINIMAX_GROUP = os.getenv("MINIMAX_GROUP", "").strip()
MINIMAX_BASE = os.getenv("MINIMAX_BASE", "https://api.minimaxi.com").rstrip("/")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "speech-02-turbo")
MINIMAX_VOICE = os.getenv("MINIMAX_VOICE", "Chinese (Mandarin)_Warm_Girl")
NAS_LIST_URL = os.getenv("NAS_LIST_URL", "http://127.0.0.1:8001/songs.txt")
NAS_BASE_URL = os.getenv("NAS_BASE_URL", "http://127.0.0.1:8001")
HOST_NAME = os.getenv("HOST_NAME", "小蓝")
RADIO_BASE = os.getenv("RADIO_BASE", "http://127.0.0.1:8100").rstrip("/")

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
VOICE_DIR = DATA_DIR / "voice"
VOICE_DIR.mkdir(parents=True, exist_ok=True)

PROFILE_FILE = DATA_DIR / "profile.json"

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


app = FastAPI(title="听间 Tingjian · AI 音乐电台")

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
    hit = next((s for s in library if s["title"] == title), None)
    if not hit:
        hit = next((s for s in library if title and title in s["title"]), None)
    return hit

# ---------------- LLM ----------------
PERSONA = (
    "你是音乐电台主持人，名叫{HOST}，声音亲切自然、说话像真实的人，不肉麻不油腻，"
    "少用网络烂梗，多用具体可感的描述。歌曲只能从提供的歌单标题里选，不许编造。"
    '每段口播 40~110 字。始终严格只输出 JSON。'
)

def llm_json(user_text, max_tokens=900):
    body = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "system", "content": PERSONA.replace("{HOST}", HOST_NAME)},
                     {"role": "user", "content": user_text}],
        "response_format": {"type": "json_object"},
        "temperature": 1.15,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        DEEPSEEK_BASE + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + DEEPSEEK_KEY})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    return json.loads(data["choices"][0]["message"]["content"])

def template_show(library, theme, tod):
    show = []
    for index, song in enumerate(library):
        text = (f"{tod}，欢迎来到《{theme['name']}》，{theme['slogan']}。我是{HOST_NAME}。"
                if index == 0 else "让音乐继续陪伴你。")
        show.extend([{"type": "talk", "text": f"{text}接下来听《{song['title']}》。"},
                     {"type": "song", "title": song["title"], "rel": song["rel"]}])
    return show

# ---------------- TTS (MiniMax 主; hex audio) ----------------
def minimax_synth(text, path):
    body = json.dumps({
        "model": MINIMAX_MODEL, "text": text, "stream": False,
        "voice_setting": {"voice_id": MINIMAX_VOICE, "speed": 1.0, "vol": 1.0, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
    }).encode()
    url = f"{MINIMAX_BASE}/v1/t2a_v2"
    if MINIMAX_GROUP:
        url += f"?GroupId={MINIMAX_GROUP}"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + MINIMAX_KEY})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
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
        Path(path).write_bytes(normalize_speech(bytes.fromhex(hexaudio)))
        return True
    except Exception as e:
        print("MiniMax 解析失败:", e, str(data[:160])); return False

async def tts_to_mp3(text, path):
    if MINIMAX_KEY:
        # 静默重试最多 3 次 (不通报), 偶发失败/限流可恢复
        for attempt in range(3):
            if await asyncio.to_thread(minimax_synth, text, str(path)):
                return True
            await asyncio.sleep(0.4)
        print("MiniMax 3 次失败, 使用固定串场语音")
        return False
    try:
        import edge_tts
        await edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural").save(str(path))
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

async def ensure_fallback_voice():
    """确保至少一条固定串场语音可用; 返回是否可用"""
    global _fb_ready
    if _fb_ready is not None:
        return _fb_ready
    async with _fb_lock:
        if _fb_ready is not None:
            return _fb_ready
        ok = False
        if MINIMAX_KEY:
            for i, line in enumerate(FALLBACK_LINES):
                if await tts_to_mp3(line, VOICE_DIR / f"fb_{i}.mp3"):
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
        if (VOICE_DIR / f"fb_{i}.mp3").is_file():
            return f"/voice/fb_{i}.mp3"
    return None

# ---------------- 组节目 ----------------
def _cleanup_old_voice():
    """语音文件超过 240 个时删最老, 防磁盘膨胀 (固定串场 fb_* 保留)"""
    try:
        files = sorted(VOICE_DIR.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
        if len(files) > 240:
            for f in files[: len(files) - 200]:
                if f.name.startswith("fb_"):
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
            items.append({"kind": "song", "url": song_url(hit["rel"]), "text": "",
                          "title": hit["title"]})
            if "recommendation" in hit:
                items[-1]["recommendation"] = hit["recommendation"]
    if add_song_fallback and not any(i["kind"] == "song" for i in items) and library:
        items.append({"kind": "song", "url": song_url(library[0]["rel"]),
                      "text": "", "title": library[0]["title"]})
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
    titles = json.dumps([song["title"] for song in songs], ensure_ascii=False)
    user = (f"现在是{theme['name']}时段：{tod}，{tod_note}。本期栏目《{theme['name']}》，"
            f"口号：{theme['slogan']}。风格：{theme['brief']}。"
            f"节目选歌已经完成，以下歌曲及顺序不可更改：{titles}。"
            "请按这个顺序为每首歌写一句自然的口播引介，第一句兼作开场。"
            "可以围绕栏目情境表达感受，不要编造歌词、歌曲年代、声学特征或听众偏好。"
            '只输出 JSON: {"introductions":["第一首引介", "第二首引介"],"closing":"简短结束语"}。'
            f"introductions 必须恰好有 {len(songs)} 条，closing 可为空字符串。")
    try:
        raw = await asyncio.to_thread(llm_json, user)
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
    library = fetch_library()
    if not library:
        raise HTTPException(502, "曲库为空")
    tod, tod_note = time_of_day()
    theme = next((t for t in THEMES if t["name"] == req.theme), None) or \
            __import__("random").choice(THEMES)
    return await make_show(library, theme, tod, tod_note, req.exclude, req.recommendation.model_dump())

class ChatReq(BaseModel):
    message: str = ""
    exclude: list = []

@app.post("/api/chat")
async def api_chat(req: ChatReq):
    library = fetch_library()
    msg = (req.message or "").strip()
    if not msg:
        raise HTTPException(400, "empty")
    titles = "\n".join(f"- {t}" for t in library[:80])
    user = (f"听众刚才对你说：{msg}\n\n"
            f"请以{HOST_NAME}的身份自然回应。如果听众是在点歌或暗示想听某首，"
            f"而且它就在歌单里，就选出来放。如果歌单里没有，就坦诚说没有并回应。\n\n"
            f"可选歌单:\n{titles}\n\n"
            '输出 JSON: {"reply":"你要说出口播的一段话","song_title":"歌单原标题或空字符串"}')
    try:
        raw = llm_json(user, max_tokens=500)
    except Exception as e:
        print("chat LLM 失败:", e)
        raw = {"reply": f"我这边有点走神，能再说一次吗？", "song_title": ""}
    reply = (raw.get("reply") or "").strip() or "嗯嗯，我在听。"
    segs = [{"type": "talk", "text": reply}]
    st = (raw.get("song_title") or "").strip()
    if st:
        hit = find_song(library, st)
        if hit:
            segs.append({"type": "song", "title": hit["title"]})
        else:
            segs.append({"type": "talk", "text": "其实这一首不在我的曲库里，"
                                                 "等以后有了再放给你听。"})
    items = await segments_to_items(library, segs, f"c{int(__import__('time').time()*1000)}")
    return {"items": items}

class IntentReq(BaseModel):
    message: str = ""
    exclude: list = []
    state: dict = {}     # {playing,paused,current,theme,auto} 来自前端

INTENT_ACTIONS = (
    '可用动作(按需选多个, 都可不填): '
    '[{"type":"play_song","title":"歌单标题"}] 放某首歌; '
    '[{"type":"play_theme","theme":"主题名"}] 换成某主题开新一期; '
    '{"type":"pause"} / {"type":"resume"} / {"type":"next"} / {"type":"prev"} / '
    '{"type":"stop"} / {"type":"set_auto","on":true或false}; '
    '纯聊天可不带动作。reply 是你要开口说的话(即便有动作也说一句配合), '
    '没有话说就回空字符串。'
)

@app.post("/api/intent")
async def api_intent(req: IntentReq):
    library = fetch_library()
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
    titles = "\n".join(f"- {t}" for t in library[:80])
    user = (f"你是{HOST_NAME}。现在电台状态：{playing}{paused}，正在播：「{cur}」，"
            f"当前主题：{theme}，自动广播：{automode}。\n"
            f"听众说：「{msg}」。请判断听众意图并决定动作（点歌/换主题/播放控制/闲聊等）。\n"
            f"可用主题名：{themes}\n"
            f"可用动作：{INTENT_ACTIONS}\n"
            f"注意：听众说「下一首/上一首/跳过/暂停/继续/停止」等是在操作播放器，必须输出对应控制动作，不要自己选歌。\n"
            f"可选歌单:\n{titles}\n\n"
            '输出 JSON: {"reply":"口播文本或空","actions":[动作对象...]}')
    try:
        raw = llm_json(user, max_tokens=700)
    except Exception as e:
        print("intent LLM 失败:", e)
        raw = {"reply": f"嗯，你说的是「{msg}」吗？我接着放歌陪你。", "actions": []}
    reply = (raw.get("reply") or "").strip()
    actions = raw.get("actions") if isinstance(raw.get("actions"), list) else []

    segs = []
    if reply:
        segs.append({"type": "talk", "text": reply})
    valid_actions = []
    for a in actions:
        if not isinstance(a, dict):
            continue
        t = a.get("type")
        if t == "play_song":
            title = (a.get("title") or "").strip()
            hit = find_song(library, title)
            if hit:
                segs.append({"type": "song", "title": hit["title"]})
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
    return {"items": items, "actions": valid_actions}


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
# 避免每次现场调 DeepSeek+MiniMax (7~30s) 拖垮 EasyInput 的列表请求
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
    if kind == "local":
        return song_url(obj["rel"]), obj["title"]
    # ncm: 用池内 id 现场取链 (URL 有时效, 必须播前现取)
    u = _ncm_by_liked_id(obj["id"])
    if not u:
        return None
    disp = f"{obj['title']} - {obj['artist']}" if obj.get("artist") else obj["title"]
    return u, disp

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
        r = _resolve_candidate(library, liked, best[0], best[1])
        if not r:
            continue
        u, disp = r
        if (it.get("talk") or "").strip():
            segs.append(("talk", str(it["talk"]).strip()))
        segs.append(("song", u, disp))
        chosen += 1

    if chosen == 0 and library:
        # 极端兜底: 本地几首模板串
        picks = _random.sample(library, min(3, len(library)))
        segs = [("talk", f"{tod}，欢迎回来。"),
                ("song", song_url(picks[0]["rel"]), picks[0]["title"]),
                ("talk", "继续陪你听。"),
                ("song", song_url(picks[1]["rel"]), picks[1]["title"])]

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
    """本地曲库外点歌: 搜网易云并取可播 URL.
    返回 dict(id/title/url/artist/artist_match) 或 None.
    artist_match: 指定了歌手时, 选中的结果是否真的由该歌手演唱
    (false 说明多半是翻唱/演奏版, 用于让主持人如实串词)."""
    hit = _ncm_search(title, artist)
    if not hit:
        return None
    sid, real_title, who = hit
    u = _ncm_song_url(sid)
    if not u:
        return None
    match = False
    if artist:
        who_list = [a for a in who.replace("/", "、").split("、") if a]
        match = any(artist in a or a in artist for a in who_list)
    return {"id": sid, "title": real_title, "url": u, "artist": who,
            "artist_match": match, "want_artist": artist}

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
                f"歌单里没有的流行/常见歌也可以点，歌名填在 song_title，我们会去网易云找。"
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
        # 口播 + (本地或网易云)歌曲 -> 直接产出最终行, 不走 segments_to_items
        # (segments_to_items 只能放本地曲库歌曲, 会丢掉网易云 URL)
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
        st = (raw_llm.get("song_title") or "").strip()
        ar = (raw_llm.get("artist") or "").strip()
        if st:
            hit = find_song(library, st)
            if hit:
                items2.append({"kind": "song", "url": song_url(hit["rel"]), "title": hit["title"]})
            else:
                ncm = _ncm_resolve(st, ar)   # 本地没有 -> 网易云兜底(带歌手找原唱)
                if ncm:
                    print(f"网易云点歌: {st!r} + {ar!r} -> {ncm['title']} by {ncm.get('artist','')} (id {ncm['id']}, match={ncm.get('artist_match')})")
                    note = ""
                    if ar and not ncm.get("artist_match"):
                        # 想要原唱但只搜到翻唱/演奏: 主持人如实串一句
                        note = (f"{ar}的《{st}》原版这边暂时没有，"
                                f"我放一个「{ncm['title']}」的版本给你，先听着。")
                    if note:
                        fnote = f"{key}_01.mp3"
                        if await tts_to_mp3(note, VOICE_DIR / fnote):
                            items2.append({"kind": "talk", "url": f"{RADIO_BASE}/voice/{fnote}"})
                    items2.append({"kind": "song", "url": ncm["url"], "title": ncm["title"]})
                else:
                    f2 = f"{key}_02.mp3"
                    miss = f"《{st}》我这边暂时找不到能播的，换一首试试？"
                    if await tts_to_mp3(miss, VOICE_DIR / f2):
                        items2.append({"kind": "talk", "url": f"{RADIO_BASE}/voice/{f2}"})
        final_lines = [it["url"] for it in items2 if it["kind"] in ("talk", "song")]

    if not final_lines:
        raise HTTPException(502, "无可用回应")
    return Response("\n".join(final_lines), media_type="text/plain; charset=utf-8")

@app.get("/api/themes")
def api_themes():
    return THEMES

@app.get("/voice/{name}")
def voice_file(name: str):
    path = VOICE_DIR / name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/mpeg")

@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)   # 浏览器请求站点图标, 返回空即可

app.mount("/", StaticFiles(directory=str(Path(__file__).parent / "static"), html=True), name="web")
