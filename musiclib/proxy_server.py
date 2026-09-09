#!/usr/bin/env python3
# easy-radio-host 多音源在线曲库代理 (端口 8001)
# 读取 resolve_multi.py 生成的新歌单 (歌名\t歌手\tsource\tsource_id)
# 1) /songs.txt -> 供 app fetch_library: 每行 "<DeepSeek标题>TAB<s/<src>/<id>.mp3>"
# 2) /s/<src>/<id>.mp3 -> 从该音源取真实播放直链 -> 307 跳转
import json
import re
import time
from collections import OrderedDict
from threading import Lock
import urllib.parse
import urllib.error
import urllib.request

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import RedirectResponse, PlainTextResponse

PLAYLIST = "/opt/easy-radio-host/musiclib/playlist.tsv"
API = "https://music-api.gdstudio.xyz/api.php"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

app = FastAPI(title="radio-online-musiclib")
LYRIC_SOURCES = frozenset({"joox", "netease"})
LYRIC_MAX_BYTES = 256 * 1024
LYRIC_CACHE_TTL = 300
LYRIC_CACHE_SIZE = 128
_lyric_cache = OrderedDict()
_lyric_cache_lock = Lock()


def http_get(url, tries=3):
    for n in range(tries):
        req = urllib.request.Request(
            url, headers={"User-Agent": UA,
                          "Referer": "https://music.gdstudio.xyz/"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 503, 429):
                time.sleep(1.0 * (n + 1))
                continue
            return e.code, e.read()
        except Exception:
            return 0, b""
    return 503, b"limit"


def load_playlist():
    """-> list[{title, artist, source, sid, note}]"""
    rows = []
    try:
        with open(PLAYLIST, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                p = [c.strip() for c in ln.split("\t")]
                # 新格式 4+列; 兼容旧 3列(id-only, source=netease)
                if len(p) >= 4:
                    rows.append({"title": p[0], "artist": p[1],
                                 "source": p[2], "sid": p[3], "note": p[4] if len(p) > 4 else ""})
                elif len(p) == 3:
                    rows.append({"title": p[0], "artist": p[1],
                                 "source": "netease", "sid": p[2], "note": ""})
    except FileNotFoundError:
        pass
    return rows


@app.get("/songs.txt")
def songs_txt():
    rows = load_playlist()
    buf = ["# 在线精选歌单 (多音源, 自动生成)", ]
    for r in rows:
        t = f"{r['artist']} - {r['title']}"
        buf.append(f"{t}\ts/{r['source']}/{urllib.parse.quote(r['sid'])}.mp3")
    return PlainTextResponse("\n".join(buf) + "\n", media_type="text/plain; charset=utf-8")


@app.get("/lyrics/{source}/{song_id}.json")
def lyrics(source: str, song_id: str):
    if source not in LYRIC_SOURCES or not re.fullmatch(r"[A-Za-z0-9_+=.-]{1,200}", song_id):
        raise HTTPException(status_code=400, detail="invalid song identifier")
    key = (source, song_id)
    now = time.monotonic()
    with _lyric_cache_lock:
        cached = _lyric_cache.get(key)
        if cached and cached[0] > now:
            _lyric_cache.move_to_end(key)
            return cached[1]

    query = urllib.parse.urlencode({"types": "lyric", "source": source, "id": song_id})
    req = urllib.request.Request(f"{API}?{query}", headers={
        "User-Agent": UA, "Referer": "https://music.gdstudio.xyz/",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status != 200:
                raise ValueError("unexpected lyric status")
            body = response.read(LYRIC_MAX_BYTES + 1)
        if len(body) > LYRIC_MAX_BYTES:
            raise ValueError("lyric response too large")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("invalid lyric response")
        if data and not {"lyric", "tlyric"}.intersection(data):
            raise ValueError("unexpected lyric response")
        lyric = data.get("lyric", "")
        translation = data.get("tlyric", "")
        lyric = "" if lyric is None else lyric
        translation = "" if translation is None else translation
        if not isinstance(lyric, str) or not isinstance(translation, str):
            raise ValueError("invalid lyric fields")
    except (OSError, ValueError, TypeError):
        raise HTTPException(status_code=502, detail="lyrics temporarily unavailable") from None

    result = {"lyric": lyric, "translation": translation, "source": source}
    # Cache only successful responses in memory; lyrics are never written to disk.
    with _lyric_cache_lock:
        _lyric_cache[key] = (time.monotonic() + LYRIC_CACHE_TTL, result)
        _lyric_cache.move_to_end(key)
        while len(_lyric_cache) > LYRIC_CACHE_SIZE:
            _lyric_cache.popitem(last=False)
    return result


def _resolve_play_url(source, sid):
    # 逐档取真实播放直链
    for br in ("320", "192", "128"):
        u = f"{API}?types=url&source={source}&id={sid}&br={br}"
        code, body = http_get(u)
        if code == 200:
            try:
                d = json.loads(body)
                url = (d or {}).get("url") or ""
                if url:
                    return url
            except Exception:
                pass
    return None


@app.get("/s/{source}/{song_id}.mp3")
def play(source: str, song_id: str):
    url = _resolve_play_url(source, song_id)
    if url:
        return RedirectResponse(url)
    return Response(status_code=404, content="audio unavailable")


# 兼容旧路径: /s/id/<id>.mp3  -> netease
@app.get("/s/id/{song_id}.mp3")
def play_legacy(song_id: str):
    url = _resolve_play_url("netease", song_id)
    if url:
        return RedirectResponse(url)
    return Response(status_code=404, content="audio unavailable")


@app.get("/_health")
def health():
    return {"status": "ok", "songs": len(load_playlist())}
