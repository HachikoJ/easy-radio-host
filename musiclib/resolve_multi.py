#!/usr/bin/env python3
"""Build a verified playlist through the running proxy's shared search quota."""
import json
import os
import sys
import urllib.request

SRC = "/opt/easy-radio-host/musiclib/playlist-source.tsv"
OUT = "/opt/easy-radio-host/musiclib/playlist.tsv"
PROXY = os.environ.get("MUSICLIB_PROXY_URL", "http://127.0.0.1:8001").rstrip("/")


def resolve(name, artist):
    request = urllib.request.Request(PROXY + "/resolve", method="POST",
                                     data=json.dumps({"title": name, "artist": artist}).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=50) as response:
        result = json.load(response)
    if result.get("status") in ("limited", "temporary"):
        raise RuntimeError("Search deferred: " + result["status"])
    track = result.get("track") if result.get("status") == "available" else None
    if track:
        return track["source"], track["id"], f"{track['title']} - {track['artist']}"
    return None, None, None


def main():
    with open(SRC, encoding="utf-8") as source:
        lines = [line.strip().split("\t")[:2] for line in source
                 if line.strip() and not line.startswith("#") and "\t" in line]
    resolved, missing = [], []
    try:
        for name, artist in lines:
            source, sid, description = resolve(name.strip(), artist.strip())
            if source:
                resolved.append(f"{name}\t{artist}\t{source}\t{sid}\t{description}\n")
            else:
                missing.append(f"{artist} - {name}")
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Playlist preserved; verification incomplete: {error}", file=sys.stderr)
        return 1
    # Preserve the playlist until the whole requested replacement is verified.
    if missing:
        print("Playlist preserved; no matching playable source: " + ", ".join(missing), file=sys.stderr)
        return 1
    with open(OUT, "w", encoding="utf-8") as output:
        output.write("# Title\tArtist\tSource\tID\tVerified recording\n")
        output.writelines(resolved)
    print(f"Verified {len(resolved)} songs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
