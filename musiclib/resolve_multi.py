#!/usr/bin/env python3
# 多音源裁决锁定解析器
# 输入: playlist-source.tsv (每行 歌名<TAB>歌手)
# 输出: playlist.tsv (歌名<TAB>歌手<TAB>source<TAB>source_id)
# 策略: 对每首歌, 按源优先级 joox > netease 多源检索,
#       用 "歌手原唱匹配 + 歌名精确 + 排除翻唱/Remix/Live/伴奏" 打分,
#       再到该候选验证能取到可播播放url, 取分最高且可播者锁定。
import json
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
import zhconv  # 简繁转换: 统一到简体便于匹配

API = "https://music-api.gdstudio.xyz/api.php"
SRC = "/opt/easy-radio-host/musiclib/playlist-source.tsv"
OUT = "/opt/easy-radio-host/musiclib/playlist.tsv"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
# 源优先级: joox 华语原唱全且可播; netease 兜底(有版权缺但有可播)
SOURCES = ["joox", "netease"]
# 明显非原唱的标记(名称或别名)
COVER_MARK = ["翻唱", "cover", "cover版", "深情", "弹唱", "串烧", "慢摇",
              "DJ", "伴奏", "remix", "Remix", "摇滚版", "live", "Live",
              "演唱會", "演唱会", "女声版", "男声版", "钢琴版", "治愈版",
              "复原版", "正式版", "3D", "环绕", "加速", "消音", "纯音乐"]

BAD_ARTIST_WORD = ["&", "vs", "联合", "feat", "伴奏"]


def http_get(url, tries=3):
    for n in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                     "Referer": "https://music.gdstudio.xyz/"})
        try:
            with urllib.request.urlopen(req, timeout=18) as r:
                return r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code in (403, 503, 429, 400):
                time.sleep(1.0 * (n + 1))
                continue
            return None
        except Exception:
            return None
    return None


def api(types, source, **kw):
    u = f"{API}?types={types}&source={source}"
    if types == "url":
        for k in ("id", "br"):
            if k in kw:
                u += f"&{k}={urllib.parse.quote(str(kw[k]))}"
    else:
        for k in ("name", "count"):
            if k in kw:
                u += f"&{k}={urllib.parse.quote(str(kw[k]))}"
    raw = http_get(u)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def norm_title(s):
    s = zhconv.convert(s, "zh-cn")  # 繁体歌手/歌名转简体
    s = s.lower()
    s = re.sub(r"\((.*?)\)|（.*?）|\[.*?\]", "", s).strip()
    s = re.sub(r"\s+", "", s)
    return s


def is_cover(name, name_n, album=""):
    low = zhconv.convert(name, "zh-cn").lower()
    alb = zhconv.convert(album or "", "zh-cn").lower()
    joined = low + "|" + alb
    return any(m.lower() in joined for m in COVER_MARK)


def artist_match(want, got_artists):
    """want=目标歌手; got=结果歌手列表. 原唱: 任一命中且非合作挂靠"""
    for ga in got_artists:
        if not ga:
            continue
        a = norm_title(ga)
        w = norm_title(want)
        # 完全或包含匹配(处理 简/繁 同人 不同前缀如"周杰伦."角)
        cond = (a == w) or (w in a) or (a in w)
        if cond:
            # 排除目标歌手名里夹带别人的合作情况依赖bad词即可
            return True
    return False


def score_name(name_n, want_n):
    if name_n == want_n:
        return 3
    if want_n in name_n and len(name_n) - len(want_n) <= 6:
        return 2   # 如 "晴天(深情)" -> 1; "稻香(治愈版)" -> 2 but cover caught
    return 0


def search_single(name, artist, source):
    rows = api("search", source, name=f"{name} {artist}", count=12)
    if not rows:
        return []
    want_n = norm_title(name)
    want_a = artist
    cands = []
    for r in rows:
        got_name = r.get("name", "")
        got_art = r.get("artist", []) or []
        nm = norm_title(got_name)
        if is_cover(got_name, nm, r.get("album", "")):
            continue
        if not artist_match(want_a, got_art):
            continue
        s = score_name(nm, want_n)
        if s <= 0:
            continue
        cands.append((s, r.get("id"), got_name, got_art))
    cands.sort(key=lambda x: -x[0])
    return cands


def can_play(id_, source):
    """验证某 id 能否取到可播放直链; 加短退避抗瞬时限流"""
    for br in ("320", "128"):
        for attempt in range(3):
            d = api("url", source, id=id_, br=br)
            if d and d.get("url"):
                return True
            time.sleep(0.8)   # 抗瞬时空url/限流
    return False


def resolve(name, artist):
    best = None
    for source in SOURCES:
        cands = search_single(name, artist, source)
        for sc, cid, gname, gart in cands:
            if can_play(cid, source):
                cand = (sc * 10 + (2 if source == "joox" else 1), source, cid,
                        f"{gname} - {','.join(gart)}")
                best = best if best and best[0] >= cand[0] else cand
                break
        time.sleep(0.6)
    if best:
        return best[1], best[2], best[3]
    return None, None, None


def main():
    lines = []
    with open(SRC, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#") or "\t" not in ln:
                continue
            t = ln.split("\t")
            if len(t) >= 2:
                lines.append((t[0].strip(), t[1].strip()))
    print(f"共 {len(lines)} 首, 多源裁决锁定中...")
    ok = 0
    fail = []
    with open(OUT, "w", encoding="utf-8") as out:
        out.write("# 歌名\t歌手\tsource\tsource_id\t备注\n")
        for i, (name, artist) in enumerate(lines):
            src, cid, disp = resolve(name, artist)
            if src and cid:
                ok += 1
                out.write(f"{name}\t{artist}\t{src}\t{cid}\t{disp}\n")
                sys.stdout.write(f"\r[{i+1}/{len(lines)}] ✓ {name} -> {src}/{cid}")
            else:
                fail.append((name, artist))
                sys.stdout.write(f"\r[{i+1}/{len(lines)}] ✗ {artist}-{name}")
            sys.stdout.flush()
            time.sleep(0.5)
    print(f"\n\n成功锁定 {ok}/{len(lines)}")
    if fail:
        print("未命中需人工:")
        for n, a in fail:
            print("  ", a, "-", n)


if __name__ == "__main__":
    main()
