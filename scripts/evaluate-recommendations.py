"""Reproducible offline policy checks; not listening satisfaction or playback tests."""
import argparse
import csv
import json
from pathlib import Path
import random
import statistics
import sys
import time
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.recommendations import artist_of, select_songs, track_key


def evaluate(rounds=100):
    catalog = json.loads((ROOT / "backend/recommendation_catalog.json").read_text("utf-8"))
    with (ROOT / "musiclib/playlist.tsv").open(encoding="utf-8") as stream:
        rows = list(csv.reader((line for line in stream if not line.startswith("#")), delimiter="\t"))
    library = [{"title": f"{row[1]} - {row[0]}", "artist": row[1],
                "rel": f"s/{row[2]}/{urllib.parse.quote(row[3])}.mp3",
                "themes": catalog["songs"].get(f"{row[1]} - {row[0]}", [])} for row in rows]
    themes = sorted({theme for song in library for theme in song["themes"]})
    coverage, latencies, theme_results = set(), [], {}
    for theme in themes:
        duplicates, replays, adjacent, tracks, unique_artists, theme_matches = 0, 0, 0, 0, [], 0
        for iteration in range(rounds):
            rng = random.Random(20260909 + iteration)
            recent = [song["title"] for song in rng.sample(library, min(30, max(0, len(library) - 4)))]
            start = time.perf_counter()
            selected, _ = select_songs(library, theme, recent, rng=rng)
            latencies.append((time.perf_counter() - start) * 1000)
            tracks += len(selected)
            duplicates += len(selected) - len({track_key(song) for song in selected})
            replays += sum(song["title"] in recent for song in selected)
            artists = [artist_of(song) for song in selected]
            adjacent += sum(bool(left) and left == right for left, right in zip(artists, artists[1:]))
            unique_artists.append(len(set(artists) - {""}))
            theme_matches += sum(theme in song["themes"] for song in selected)
            coverage.update(track_key(song) for song in selected)
        theme_results[theme] = {
            "shows": rounds, "tracks": tracks, "within_show_duplicate_rate": duplicates / tracks if tracks else 0,
            "recent_replay_rate": replays / tracks if tracks else 0,
            "adjacent_same_artist_count": adjacent,
            "mean_unique_artists_per_show": statistics.mean(unique_artists),
            "curated_scene_match_rate": theme_matches / tracks if tracks else 0,
        }
    return {
        "scope": "Offline catalog selection only; no network, audio analysis, playback, or user satisfaction measurement.",
        "seed": 20260909, "catalog_count": len(library), "rounds_per_theme": rounds,
        "themes": theme_results, "catalog_coverage_count": len(coverage),
        "catalog_coverage_rate": len(coverage) / len(library) if library else 0,
        "selection_latency_ms": {"median": round(statistics.median(latencies), 3),
                                 "p95": round(sorted(latencies)[int(len(latencies) * 0.95)], 3)},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 10000:
        parser.error("--rounds must be between 1 and 10000")
    print(json.dumps(evaluate(args.rounds), ensure_ascii=False, indent=2))
