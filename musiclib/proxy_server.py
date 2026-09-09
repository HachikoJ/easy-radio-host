#!/usr/bin/env python3
# easy-radio-host 多音源在线曲库代理 (端口 8001)
# 读取 resolve_multi.py 生成的新歌单 (歌名\t歌手\tsource\tsource_id)
# 1) /songs.txt -> 供 app fetch_library: 每行 "<DeepSeek标题>TAB<s/<src>/<id>.mp3>"
# 2) /s/<src>/<id>.mp3 -> 从该音源取真实播放直链 -> 307 跳转
import json
import re
import time
from collections import OrderedDict, deque
from concurrent.futures import Future
from threading import Lock
import urllib.parse
import urllib.error
import urllib.request

from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.responses import RedirectResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

try:
    from musiclib.matching import SOURCES, artists, base_title, recording_match, simplified
except ModuleNotFoundError:
    from matching import SOURCES, artists, base_title, recording_match, simplified

PLAYLIST = "/opt/easy-radio-host/musiclib/playlist.tsv"
API = "https://music-api.gdstudio.xyz/api.php"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

app = FastAPI(title="radio-online-musiclib")
LYRIC_SOURCES = frozenset(SOURCES)
LYRIC_MAX_BYTES = 256 * 1024
LYRIC_CACHE_TTL = 300
LYRIC_CACHE_SIZE = 128
_lyric_cache = OrderedDict()
_lyric_cache_lock = Lock()
PLAY_MAX_BYTES = 64 * 1024
PLAY_PROBE_BYTES = 512
PLAY_TIMEOUT = 5
PLAY_BUDGET = 20
PLAY_CACHE_TTL = 45
PLAY_CACHE_SIZE = 128
PLAY_CDN_DOMAINS = ("joox.com", "126.net", "163.com", "qq.com", "kuwo.cn", "sycdn.kuwo.cn",
                    "bilivideo.com", "bilivideo.cn", "bilibili.com", "akamaized.net",
                    "tidal.com", "qobuz.com", "mzstatic.com", "apple.com", "googlevideo.com",
                    "scdn.co", "spotifycdn.com")
_play_cache = OrderedDict()
_play_cache_lock = Lock()
API_LIMIT = 50
API_WINDOW = 300
API_CACHE_SIZE = 512
_api_times = deque()
_api_cache = OrderedDict()
_api_pending = {}
_api_lock = Lock()
_api_blocked_until = 0
_unsupported = {}
_resolve_pending = {}
_resolve_lock = Lock()
RESOLVE_BUDGET = 44


class ResolveFailure(Exception):
    def __init__(self, status, retry_after=0):
        self.status = status
        self.retry_after = retry_after
        super().__init__(status)


def http_get(url, tries=1, timeout=PLAY_TIMEOUT):
    """All GD traffic shares one rolling quota, bounded cache and in-flight work."""
    global _api_blocked_until
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    source = params.get("source", [""])[0]
    kind = params.get("types", [""])[0]
    now = time.monotonic()
    with _api_lock:
        while _api_times and _api_times[0] <= now - API_WINDOW:
            _api_times.popleft()
        cached = _api_cache.get(url)
        if cached and cached[0] > now:
            _api_cache.move_to_end(url)
            return cached[1]
        if _unsupported.get(source, 0) > now:
            return 400, b"unsupported source"
        pending = _api_pending.get(url)
        if pending is None:
            if _api_blocked_until > now or len(_api_times) >= API_LIMIT:
                return 429, b""
            _api_times.append(now)
            pending = _api_pending[url] = Future()
            owner = True
        else:
            owner = False
    if not owner:
        try:
            return pending.result(timeout=timeout)
        except TimeoutError:
            return 0, b""
    result = (0, b"")
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": UA,
                          "Referer": "https://music.gdstudio.xyz/"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                limit = LYRIC_MAX_BYTES if kind == "lyric" else PLAY_MAX_BYTES
                body = r.read(limit + 1)
                result = (r.status, body) if len(body) <= limit else (502, b"")
        except urllib.error.HTTPError as e:
            result = (e.code, b"")
            if e.code == 429:
                try:
                    retry = max(1, min(300, int(e.headers.get("Retry-After", "300"))))
                except (ValueError, TypeError, AttributeError):
                    retry = 300
                with _api_lock:
                    _api_blocked_until = max(_api_blocked_until, time.monotonic() + retry)
            e.close()
        except (OSError, ValueError):
            pass
        if b"source is not supported" in result[1].lower():
            with _api_lock:
                _unsupported[source] = time.monotonic() + 3600
            result = (400, b"unsupported source")
        if result[0] == 200:
            try:
                json.loads(result[1])
            except (ValueError, TypeError):
                result = (502, b"")
            else:
                ttl = 300 if kind in ("search", "lyric") else PLAY_CACHE_TTL
                with _api_lock:
                    _api_cache[url] = (time.monotonic() + ttl, result)
                    _api_cache.move_to_end(url)
                    while len(_api_cache) > API_CACHE_SIZE:
                        _api_cache.popitem(last=False)
        return result
    finally:
        with _api_lock:
            _api_pending.pop(url, None)
            pending.set_result(result)


def _retry_after():
    with _api_lock:
        now = time.monotonic()
        remaining = max(0, _api_blocked_until - now)
        if len(_api_times) >= API_LIMIT:
            remaining = max(remaining, _api_times[0] + API_WINDOW - now)
        return max(1, int(remaining) + 1)


def _api_data(kind, source, deadline, **params):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ResolveFailure("temporary")
    query = urllib.parse.urlencode({"types": kind, "source": source, **params})
    code, body = http_get(f"{API}?{query}", timeout=min(PLAY_TIMEOUT, remaining))
    if code == 429:
        raise ResolveFailure("limited", _retry_after())
    if time.monotonic() >= deadline:
        raise ResolveFailure("temporary")
    if code == 400 and body == b"unsupported source":
        return None
    if code != 200:
        raise ResolveFailure("temporary")
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        raise ResolveFailure("temporary") from None


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
    try:
        code, body = http_get(f"{API}?{query}", timeout=10)
        if code == 429:
            raise HTTPException(status_code=429, detail="lyrics rate limited",
                                headers={"Retry-After": str(_retry_after())})
        if code != 200:
            raise ValueError("unexpected lyric status")
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


def _allowed_media_url(url):
    if not isinstance(url, str):
        return False
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        return (parts.scheme in ("https", "http") and not parts.username and not parts.password
                and parts.port in (None, 80, 443)
                and any(host == domain or host.endswith("." + domain) for domain in PLAY_CDN_DOMAINS))
    except ValueError:
        return False


class _MediaRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed_media_url(newurl):
            raise urllib.error.URLError("unsupported media host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _has_audio_header(body):
    return (body.startswith((b"ID3", b"fLaC", b"OggS"))
            or (len(body) >= 2 and body[0] == 0xff and body[1] & 0xe0 == 0xe0)
            or (len(body) >= 12 and body[4:8] == b"ftyp")
            or (body.startswith(b"RIFF") and body[8:12] == b"WAVE"))


def _media_available(url, timeout):
    if not _allowed_media_url(url):
        return False
    request = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": "https://music.gdstudio.xyz/",
        "Range": f"bytes=0-{PLAY_PROBE_BYTES - 1}",
    })
    try:
        opener = urllib.request.build_opener(_MediaRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            return (response.status in (200, 206)
                    and _has_audio_header(response.read(PLAY_PROBE_BYTES)))
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        if status == 429:
            raise ResolveFailure("temporary", 30) from None
        if status >= 500:
            raise ResolveFailure("temporary") from None
    except (OSError, ValueError):
        raise ResolveFailure("temporary") from None
    return False


def _resolve_play_url(source, sid, refresh=False, deadline=None, strict=False):
    key = (source, sid)
    with _play_cache_lock:
        cached = _play_cache.get(key)
        if not refresh and cached and cached[0] > time.monotonic():
            _play_cache.move_to_end(key)
            return cached[1]
        _play_cache.pop(key, None)

    deadline = deadline or time.monotonic() + PLAY_BUDGET
    checked = set()
    temporary = False
    # A nonempty signed URL can still return a CDN 404. Check a small range
    # before redirecting, keeping every fallback on the same recording ID.
    for br in ("320", "192", "128"):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            if refresh:
                query = urllib.parse.urlencode({"types": "url", "source": source, "id": sid, "br": br})
                with _api_lock:
                    _api_cache.pop(f"{API}?{query}", None)
            d = _api_data("url", source, deadline, id=sid, br=br)
            if d is not None and (not isinstance(d, dict) or "url" not in d):
                raise ResolveFailure("temporary")
            url = d.get("url") if isinstance(d, dict) else None
            remaining = deadline - time.monotonic()
            if url and not _allowed_media_url(url):
                temporary = True
            if not _allowed_media_url(url) or url in checked or remaining <= 0:
                continue
            checked.add(url)
            if _media_available(url, min(PLAY_TIMEOUT, remaining)):
                if time.monotonic() >= deadline:
                    raise ResolveFailure("temporary")
                with _play_cache_lock:
                    _play_cache[key] = (time.monotonic() + PLAY_CACHE_TTL, url)
                    _play_cache.move_to_end(key)
                    while len(_play_cache) > PLAY_CACHE_SIZE:
                        _play_cache.popitem(last=False)
                return url
        except ResolveFailure as failure:
            if failure.status == "limited":
                if strict:
                    raise
                break
            temporary = True
    if strict and (temporary or time.monotonic() >= deadline):
        raise ResolveFailure("temporary")
    return None


class ExcludedTrack(BaseModel):
    source: str = Field(max_length=32)
    id: str = Field(max_length=200)


class ResolveRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    artist: str = Field(default="", max_length=500)
    source: str = Field(default="", max_length=32)
    id: str = Field(default="", max_length=200)
    exclude: list[ExcludedTrack] = Field(default_factory=list, max_length=100)


def _valid_id(value):
    return isinstance(value, (str, int)) and re.fullmatch(r"[A-Za-z0-9_+=.-]{1,200}", str(value))


def _resolve_recording(payload):
    title, artist = payload.title.strip(), payload.artist.strip()
    if not base_title(title):
        raise HTTPException(status_code=400, detail="song title required")
    excluded = {(item.source, item.id) for item in payload.exclude}
    deadline = time.monotonic() + RESOLVE_BUDGET
    searched, checked, failed = [], set(), False

    def attempt(source, row):
        sid = row.get("url_id") or row.get("id", row.get("sid"))
        key = (source, str(sid))
        if not _valid_id(sid) or key in checked or key in excluded or not recording_match(title, artist, row):
            return None
        checked.add(key)
        url = _resolve_play_url(source, str(sid), deadline=deadline, strict=True)
        if not url:
            return None
        lyric_id = row.get("lyric_id") or sid
        return {"status": "available", "track": {
            "title": row.get("name", row.get("title")), "artist": " / ".join(artists(row.get("artist"))),
            "source": source, "id": str(sid), "lyric_id": str(lyric_id) if _valid_id(lyric_id) else str(sid),
            "rel": f"s/{source}/{urllib.parse.quote(str(sid), safe='')}.mp3",
        }, "searched": searched.copy()}

    try:
        # An old playlist ID is only a hint when its stored version also matches.
        if payload.source in SOURCES and _valid_id(payload.id):
            for row in load_playlist():
                if row["source"] != payload.source or row["sid"] != payload.id:
                    continue
                recorded = row.get("note", "").rsplit(" - ", 1)
                if len(recorded) != 2 or not all(part.strip() for part in recorded):
                    continue
                recorded_row = dict(row, title=recorded[0].strip(), artist=recorded[1].strip())
                if recording_match(title, artist, recorded_row):
                    searched.append(payload.source)
                    try:
                        result = attempt(payload.source, recorded_row)
                        if result:
                            return result
                    except ResolveFailure as error:
                        if error.status == "limited":
                            raise
                        failed = True
                    break

        queries = list(dict.fromkeys(filter(None, [f"{title} {artist}".strip(),
                                                   f"{simplified(title)} {simplified(artist)}".strip(),
                                                   title])))
        # Visit every supported channel before spending the next page on one channel.
        exhausted = set()
        for page in (1, 2, 3):
            for query in queries:
                for source in SOURCES:
                    if time.monotonic() >= deadline:
                        raise ResolveFailure("temporary")
                    if (source, query) in exhausted:
                        continue
                    if source not in searched:
                        searched.append(source)
                    try:
                        rows = _api_data("search", source, deadline, name=query, count=30, pages=page)
                        if rows is None:
                            exhausted.add((source, query))
                            continue
                        if not isinstance(rows, list):
                            raise ResolveFailure("temporary")
                        if len(rows) < 30:
                            exhausted.add((source, query))
                        for row in rows:
                            try:
                                result = attempt(source, row) if isinstance(row, dict) else None
                            except ResolveFailure as error:
                                if error.status == "limited":
                                    raise
                                failed = True
                                continue
                            if result:
                                return result
                    except ResolveFailure as error:
                        if error.status == "limited":
                            raise
                        failed = True
        # Full pages beyond the bounded traversal are not proof of absence.
        if any((source, query) not in exhausted for source in SOURCES for query in queries):
            failed = True
        return {"status": "temporary" if failed else "unavailable", "searched": searched}
    except ResolveFailure as error:
        result = {"status": error.status, "searched": searched}
        if error.retry_after:
            result["retry_after"] = error.retry_after
        return result


@app.post("/resolve")
def resolve(payload: ResolveRequest):
    key = (payload.title.strip(), payload.artist.strip(), payload.source, payload.id,
           tuple(sorted((item.source, item.id) for item in payload.exclude)))
    with _resolve_lock:
        future = _resolve_pending.get(key)
        owner = future is None
        if owner:
            future = _resolve_pending[key] = Future()
    if not owner:
        try:
            return future.result(timeout=RESOLVE_BUDGET + 1)
        except TimeoutError:
            return {"status": "temporary", "searched": []}
    try:
        result = _resolve_recording(payload)
        future.set_result(result)
        return result
    except Exception as error:
        future.set_exception(error)
        raise
    finally:
        with _resolve_lock:
            _resolve_pending.pop(key, None)


def _stream_audio(url, range_header):
    if not _allowed_media_url(url):
        raise HTTPException(status_code=502, detail="audio temporarily unavailable")
    if range_header and not re.fullmatch(r"bytes=(?:\d+-\d*|-\d+)", range_header):
        raise HTTPException(status_code=416, detail="single byte range required")
    headers = {"User-Agent": UA, "Referer": "https://music.gdstudio.xyz/"}
    if range_header:
        headers["Range"] = range_header
    try:
        upstream = urllib.request.build_opener(_MediaRedirectHandler()).open(
            urllib.request.Request(url, headers=headers), timeout=PLAY_TIMEOUT)
    except urllib.error.HTTPError as error:
        status = 416 if error.code == 416 else 502
        error.close()
        raise HTTPException(status_code=status, detail="audio temporarily unavailable") from None
    except (OSError, ValueError):
        raise HTTPException(status_code=502, detail="audio temporarily unavailable") from None
    content_type = upstream.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0]
    if upstream.status not in (200, 206) or content_type in ("text/html", "application/json", "application/xml", "text/xml"):
        upstream.close()
        raise HTTPException(status_code=502, detail="audio temporarily unavailable")
    response_headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    for name in ("Content-Length", "Content-Range", "Accept-Ranges"):
        value = upstream.headers.get(name)
        if value:
            response_headers[name] = value

    def chunks():
        try:
            while True:
                block = upstream.read(64 * 1024)
                if not block:
                    break
                yield block
        finally:
            upstream.close()
    return StreamingResponse(chunks(), status_code=upstream.status, media_type=content_type,
                             headers=response_headers, background=BackgroundTask(upstream.close))


@app.get("/s/{source}/{song_id}.mp3")
def play(source: str, song_id: str, refresh: bool = False, stream: bool = False, request: Request = None):
    # FastAPI already decodes the path once; the library URLs may encode IDs twice.
    song_id = urllib.parse.unquote(song_id)
    source = "netease" if source == "id" else source
    if source not in LYRIC_SOURCES or not re.fullmatch(r"[A-Za-z0-9_+=.-]{1,200}", song_id):
        raise HTTPException(status_code=400, detail="invalid song identifier")
    url = _resolve_play_url(source, song_id, refresh=refresh)
    if url:
        if stream:
            return _stream_audio(url, request.headers.get("range") if request else None)
        return RedirectResponse(url, headers={"Cache-Control": "no-store"})
    return Response(status_code=502, content="audio temporarily unavailable",
                    headers={"Cache-Control": "no-store"})


# 兼容旧路径: /s/id/<id>.mp3  -> netease
@app.get("/s/id/{song_id}.mp3")
def play_legacy(song_id: str, refresh: bool = False):
    return play("netease", song_id, refresh=refresh)


@app.get("/_health")
def health():
    return {"status": "ok", "songs": len(load_playlist())}
