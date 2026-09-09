"""Metadata-based candidate fusion; no audio models or persistent listener data."""
import random
import re
import unicodedata
from collections import Counter


def normalize(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value))).strip().casefold()


def artist_of(song):
    artist = song.get("artist")
    if isinstance(artist, str) and artist.strip():
        return normalize(artist)
    title = song.get("title", "")
    return normalize(title.split(" - ", 1)[0]) if " - " in title else ""


def track_key(song):
    title = song.get("title", "")
    artist = artist_of(song)
    parts = title.split(" - ", 1)
    name = parts[1] if len(parts) == 2 and normalize(parts[0]) == artist else title
    return (artist_of(song), normalize(name))


def select_songs(library, theme, exclude=(), signals=None, profile=None, count=4, rng=None):
    """Fuse factual channels, preserving exploration and hard dislike exclusions.

    Recent arrays are oldest-first. Only when unseen songs run out are older
    recent tracks allowed back in. Prefer fresh songs even if that requires
    repeating an artist; listener dislikes are never relaxed.
    """
    rng = rng or random.SystemRandom()
    signals = signals or {}
    personalize = signals.get("personalize") is True
    profile = profile or {}
    favorites = {normalize(x) for x in signals.get("favorites", [])} if personalize else set()
    disliked = {normalize(x) for x in signals.get("disliked", [])} if personalize else set()
    history = signals.get("history", []) if personalize else []
    recent = {normalize(title): i for i, title in enumerate([*history, *exclude])}
    seed = normalize(signals.get("seed", ""))
    unique, seen_titles, seen_rels = [], set(), set()
    for song in library:
        key = track_key(song)
        rel = song.get("rel", "")
        if not key[1] or not rel or key in seen_titles or rel in seen_rels:
            continue
        seen_titles.add(key)
        seen_rels.add(rel)
        unique.append(song)
    seed_artist = next((artist_of(song) for song in unique if normalize(song["title"]) == seed), "")
    favorite_artists = {artist_of(song) for song in unique if normalize(song["title"]) in favorites} - {""}
    profile_artists = {normalize(x) for x in profile.get("artists", []) if isinstance(x, str)}
    channels = {name: [] for name in ("seed_artist", "favorites", "theme", "favorite_artist", "profile_artist", "explore")}
    sources = {}
    eligible = []
    for song in unique:
        key = normalize(song["title"])
        if key in disliked or key == seed:
            continue
        eligible.append(song)
        artist = artist_of(song)
        labels = song.get("themes", [])
        labels = list(labels) if isinstance(labels, list) else []
        tags = song.get("tags", [])
        labels += tags if isinstance(tags, list) else []
        names = []
        if normalize(theme) in {normalize(x) for x in labels}:
            names.append("theme")
        if artist and artist == seed_artist:
            names.append("seed_artist")
        if key in favorites:
            names.append("favorites")
        if artist in favorite_artists:
            names.append("favorite_artist")
        if artist in profile_artists:
            names.append("profile_artist")
        names.append("explore")
        sources[track_key(song)] = names
        for name in names:
            channels[name].append(song)
    for candidates in channels.values():
        rng.shuffle(candidates)

    target = min(max(1, count), len(eligible))
    selected, used, artist_counts, chosen_channels = [], set(), Counter(), Counter()
    recent_relaxed = 0
    artist_relaxed = False
    seed_recent = False

    def accept(song, channel, relax_artist=False):
        nonlocal artist_relaxed, recent_relaxed
        key, artist = track_key(song), artist_of(song)
        if key in used:
            return False
        # Prefer one track per artist; unknown artists are not one shared artist.
        if artist and artist_counts[artist] and not relax_artist:
            return False
        if artist and artist_counts[artist]:
            artist_relaxed = True
        reasons = {
            "theme": "曲库主题标签匹配", "seed_artist": "与所选歌曲来自同一歌手",
            "favorites": "来自你的收藏", "favorite_artist": "来自你收藏歌曲的歌手",
            "profile_artist": "匹配电台配置的歌手偏好", "explore": "从在线曲库探索",
        }
        factual_sources = [name for name in sources[key] if name != "explore" or name == channel]
        reason = reasons[channel]
        if normalize(song["title"]) in recent:
            recent_relaxed += 1
            reason += ("；为延伸所选歌手，回补较早听过的歌曲" if channel == "seed_artist" and not selected
                       else "；未播候选不足，回补较早听过的歌曲")
        result = dict(song)
        result["recommendation"] = {"sources": factual_sources, "reason": reason}
        selected.append(result)
        used.add(key)
        artist_counts[artist] += 1
        chosen_channels[channel] += 1
        return True

    # Round-robin channels avoids inventing numeric affinity scores from sparse
    # metadata. Reserve the last position for exploration when it is available.
    active = [name for name in channels if channels[name]]
    if channels["seed_artist"]:
        fresh_seed = [song for song in channels["seed_artist"] if normalize(song["title"]) not in recent]
        seed_song = fresh_seed[0] if fresh_seed else min(channels["seed_artist"], key=lambda song: recent[normalize(song["title"])])
        seed_recent = not bool(fresh_seed)
        accept(seed_song, "seed_artist")
    for relax_artist in (False, True):
        while len(selected) < target:
            changed = False
            order = ["explore"] if len(selected) == target - 1 and not chosen_channels["explore"] else active
            for channel in order:
                if len(selected) == target - 1 and not chosen_channels["explore"]:
                    channel = "explore"
                candidates = channels[channel]
                for song in candidates:
                    if normalize(song["title"]) not in recent and accept(song, channel, relax_artist):
                        changed = True
                        break
                if len(selected) == target:
                    break
            if not changed:
                break
    # When all fresh tracks have been used, favor the least recently heard.
    older = sorted((song for song in eligible if normalize(song["title"]) in recent), key=lambda song: recent[normalize(song["title"])])
    for relax_artist in (False, True):
        for song in older:
            if len(selected) == target:
                break
            accept(song, sources[track_key(song)][0], relax_artist)

    # Separate repeated artists wherever possible without changing membership.
    ordered = []
    remaining = list(selected)
    while remaining:
        last = artist_of(ordered[-1]) if ordered else ""
        frequencies = Counter(artist_of(song) for song in remaining if artist_of(song))
        options = [i for i, song in enumerate(remaining) if not last or artist_of(song) != last]
        choice = max(options, key=lambda i: frequencies.get(artist_of(remaining[i]), 1)) if options else 0
        ordered.append(remaining.pop(choice))
    meta = {
        "strategy": "metadata_fusion_v1", "catalog_count": len(unique),
        "candidate_count": len(eligible), "count": len(ordered),
        "available_channels": active,
        "channels": list(chosen_channels), "channel_counts": dict(chosen_channels), "personalized": personalize,
        "recent_relaxed": bool(recent_relaxed), "recent_relaxed_count": recent_relaxed,
        "artist_limit_relaxed": artist_relaxed,
        "theme_metadata_available": bool(channels["theme"]),
        "seed_artist_available": bool(channels["seed_artist"]),
    }
    notices = []
    if recent_relaxed:
        notices.append("为满足同歌手选择，已回补较早听过的歌曲" if seed_recent else "未播候选不足，已回补较早听过的歌曲")
    if artist_relaxed:
        notices.append("候选歌手有限，已适当放宽歌手去重")
    if seed and not seed_artist:
        notices.append("所选歌曲暂无可用歌手资料，已从曲库推荐")
    elif seed and not channels["seed_artist"]:
        notices.append("暂无这位歌手的其他可用歌曲，已从曲库推荐")
    meta["notice"] = "；".join(notices)
    return ordered, meta
