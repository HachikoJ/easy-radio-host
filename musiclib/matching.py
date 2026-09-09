"""Recording identity shared by online search and playlist maintenance."""
import re
import unicodedata

import zhconv

SOURCES = ("netease", "kuwo", "joox", "bilibili", "tencent", "tidal",
           "qobuz", "apple", "ytmusic", "spotify")
VERSION_MARKERS = {
    "live": r"\blive\b|现场|演唱会|演唱會|音乐节|音樂節",
    "cover": r"\bcover\b|翻唱|翻弹|翻彈",
    "remix": r"\bremix\b|\bdj\b|混音|慢摇|慢搖",
    "instrumental": r"instrumental|伴奏|纯音乐|純音樂|消音|卡拉ok|karaoke",
    "acoustic": r"acoustic|不插电|不插電|弹唱|彈唱|钢琴版|鋼琴版",
    "sped": r"sped\s*up|slowed|加速|减速|減速|降调|降調|升调|升調",
    "rerecorded": r"re-record|rerecord|taylor.s version|重录|重錄",
}


def simplified(value):
    return zhconv.convert(unicodedata.normalize("NFKC", str(value or "")), "zh-cn").casefold()


def normalize(value):
    return re.sub(r"[\W_]+", "", simplified(value))


def versions(value):
    text = simplified(value)
    return frozenset(key for key, pattern in VERSION_MARKERS.items() if re.search(pattern, text))


def base_title(value):
    text = simplified(value)
    # Preserve real subtitles; ignore only recognized version/OST annotations.
    def annotation(match):
        value = match.group(0)
        if versions(value) or re.search(r"电影|电视剧|主题曲|插曲|片尾曲|片头曲|ost|remaster|重制|原版|完整版", value):
            return ""
        return value
    text = re.sub(r"\([^)]*\)|\[[^]]*\]|【[^】]*】", annotation, text)
    return normalize(text)


def artists(value):
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"\s*(?:、|/|;|；|,|，|&| feat\. | featuring )\s*", value) if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(part).strip() for part in value if isinstance(part, (str, int)) and str(part).strip()]
    return []


def artist_match(want, got):
    requested = {normalize(name) for name in artists(want)} - {""}
    actual = {normalize(name) for name in artists(got)} - {""}
    return bool(actual) and (not requested or requested == actual)


def recording_match(title, artist, row):
    if not isinstance(row, dict):
        return False
    name = row.get("name", row.get("title", ""))
    if not isinstance(name, str) or not base_title(title) or base_title(name) != base_title(title):
        return False
    if not artist_match(artist, row.get("artist")):
        return False
    requested_versions = versions(title)
    actual_versions = versions(name + " " + str(row.get("album") or "") + " " + str(row.get("note") or ""))
    return actual_versions == requested_versions
