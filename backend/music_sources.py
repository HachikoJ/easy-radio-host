"""Client for the music proxy's shared, rate-limited availability checks."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

import zhconv
import aiohttp

SOURCES = frozenset(("netease", "tencent", "kuwo", "tidal", "qobuz", "joox",
                     "bilibili", "apple", "ytmusic", "spotify"))
IDENTIFIER = re.compile(r"[A-Za-z0-9_+=.-]{1,200}")


def normalized(text):
    return re.sub(r"\s+", "", zhconv.convert(str(text), "zh-cn")).casefold()


def artist_key(text):
    return frozenset(normalized(part) for part in re.split(r"[,，、/;&；]+", text) if part.strip())


def identity(song):
    display = song.get("title", "").strip()
    artist = song.get("artist", "").strip()
    parts = display.split(" - ", 1)
    if len(parts) == 2 and (not artist or artist_key(parts[0]) == artist_key(artist)):
        artist, display = parts
    result = {"title": display, "artist": artist}
    match = re.fullmatch(r"s/([a-z]+)/([^/]+)\.mp3", song.get("rel", ""))
    if match:
        source, sid = match.groups()
        sid = urllib.parse.unquote(sid)
        if source in SOURCES and IDENTIFIER.fullmatch(sid):
            result.update(source=source, id=sid)
    for key in ("source", "id"):
        if key in song:
            result[key] = song[key]
    return result


def catalog_match(library, title, artist=""):
    """Only exact identities; a title substring can name a different song."""
    exact = [song for song in library if normalized(song["title"]) == normalized(title)]
    if artist:
        exact = [song for song in exact if artist_key(identity(song)["artist"]) == artist_key(artist)]
    if len(exact) == 1:
        return exact[0]
    hits = [song for song in library if normalized(identity(song)["title"]) == normalized(title)
            and (not artist or artist_key(identity(song)["artist"]) == artist_key(artist))]
    return hits[0] if len(hits) == 1 else None


def resolve_song(list_url, song, exclude=()):
    payload = {**identity(song), "exclude": list(exclude)}
    request = urllib.request.Request(
        urllib.parse.urljoin(list_url, "resolve"), data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=50) as response:
            body = response.read(128 * 1024 + 1)
        if len(body) > 128 * 1024:
            raise ValueError("oversized music response")
        return parse_resolution(body, song)
    except urllib.error.HTTPError as error:
        status = "limited" if error.code == 429 else "temporary"
        error.close()
        return {"status": status, "searched": []}
    except (OSError, ValueError, TypeError):
        return {"status": "temporary", "searched": []}


async def resolve_song_async(list_url, song, exclude=()):
    # Cancelling this task closes the socket so the proxy stops its search.
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=50)) as client:
            async with client.post(urllib.parse.urljoin(list_url, "resolve"),
                                   json={**identity(song), "exclude": list(exclude)}) as response:
                if response.status != 200:
                    return {"status": "limited" if response.status == 429 else "temporary",
                            "retry_after": int(response.headers.get("Retry-After", 30)), "searched": []}
                body = bytearray()
                async for chunk in response.content.iter_chunked(16 * 1024):
                    body.extend(chunk)
                    if len(body) > 128 * 1024:
                        break
                return parse_resolution(body, song)
    except (aiohttp.ClientError, OSError, ValueError, TypeError):
        return {"status": "temporary", "searched": []}


async def proxy_availability(list_url):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as client:
            async with client.get(urllib.parse.urljoin(list_url, "availability")) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("status") not in ("ready", "limited"):
                    raise ValueError("invalid quota status")
                return data
    except (aiohttp.ClientError, OSError, ValueError, TypeError):
        return {"status": "temporary", "retry_after": 30, "remaining": 0}


def parse_resolution(body, song):
    try:
        if len(body) > 128 * 1024:
            raise ValueError("oversized music response")
        data = json.loads(body)
        if not isinstance(data, dict) or data.get("status") not in {"available", "unavailable", "limited", "temporary"}:
            raise ValueError("invalid music response")
        if data["status"] == "available":
            track = data.get("track")
            if (not isinstance(track, dict) or track.get("source") not in SOURCES
                    or not IDENTIFIER.fullmatch(str(track.get("id", "")))
                    or not isinstance(track.get("title"), str) or not track["title"].strip()
                    or not isinstance(track.get("artist"), str)):
                raise ValueError("invalid verified track")
            source, sid = track["source"], str(track["id"])
            lyric_id = str(track.get("lyric_id") or sid)
            if not IDENTIFIER.fullmatch(lyric_id):
                lyric_id = sid
            result = dict(song, rel=f"s/{source}/{urllib.parse.quote(sid, safe='')}.mp3",
                          source=source, id=sid, lyric_id=lyric_id,
                          artist=track["artist"], _verified=True)
            # Preserve a catalog identity for favorites and recommendation reasons.
            if not song.get("rel"):
                result["title"] = f"{track['artist']} - {track['title']}" if track["artist"] else track["title"]
            data["song"] = result
        return data
    except (OSError, ValueError, TypeError):
        return {"status": "temporary", "searched": []}


def availability_notice(status, title):
    label = f"《{title}》"
    if status == "unavailable":
        return f"{label}未找到歌名、歌手和版本相符的可用音源，将继续下一曲。"
    if status == "limited":
        return f"{label}的音源检索遇到调用限额，暂未完成，将尝试下一首推荐；没有可播歌曲时会等待额度恢复后自动继续。"
    return f"{label}的音源服务暂时未响应，检索尚未完成，将尝试下一首推荐。"
