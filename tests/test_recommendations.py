"""Offline recommendation invariants and mocked API behavior."""
import csv
import importlib.util
import json
import random
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from backend.recommendations import artist_of, select_songs, track_key

ROOT = Path(__file__).resolve().parents[1]


def song(index, artist=None, themes=()):
    artist = artist or f"Artist {index}"
    return {"title": f"{artist} - Track {index}", "artist": artist,
            "rel": f"s/netease/{index}.mp3", "themes": list(themes)}


class RecommendationSelection(unittest.TestCase):
    def pick(self, library, **kwargs):
        return select_songs(library, "午后咖啡", rng=random.Random(23), **kwargs)

    def test_empty_and_small_catalogs(self):
        for size in range(4):
            result, meta = self.pick([song(i) for i in range(size)])
            self.assertEqual(len(result), size)
            self.assertEqual(meta["count"], size)

    def test_all_library_entries_participate_beyond_eighty(self):
        library = [song(i) for i in range(130)]
        result, _ = self.pick(library, exclude=[row["title"] for row in library[:126]])
        self.assertEqual({row["title"] for row in result}, {row["title"] for row in library[126:]})

    def test_artist_title_dedup_across_sources_preserves_other_artists(self):
        library = [{"title": "Shared title", "artist": "Artist A", "rel": "s/a/1"},
                   {"title": "Shared title", "artist": "Artist A", "rel": "s/b/2"},
                   {"title": "Shared title", "artist": "Artist B", "rel": "s/a/3"}]
        result, meta = self.pick(library)
        self.assertEqual(len(result), 2)
        self.assertEqual(meta["catalog_count"], 2)
        self.assertEqual({artist_of(row) for row in result}, {"artist a", "artist b"})

    def test_recent_exclusion_and_artist_diversity_over_repeated_runs(self):
        library = [song(i, artist=f"Artist {i % 8}") for i in range(80)]
        recent = [row["title"] for row in library[:30]]
        for seed in range(50):
            result, meta = select_songs(library, "午后咖啡", recent, rng=random.Random(seed))
            self.assertEqual(len({track_key(row) for row in result}), 4)
            self.assertEqual(len({artist_of(row) for row in result}), 4)
            self.assertFalse(set(recent) & {row["title"] for row in result})
            self.assertFalse(meta["recent_relaxed"])

    def test_small_catalog_reuses_oldest_recent_first(self):
        library = [song(i) for i in range(8)]
        recent = [row["title"] for row in library]
        result, meta = self.pick(library, exclude=recent)
        self.assertEqual([row["title"] for row in result], recent[:4])
        self.assertTrue(meta["recent_relaxed"])
        self.assertEqual(meta["recent_relaxed_count"], 4)

    def test_dislikes_are_hard_exclusions_and_do_not_leak_into_metadata(self):
        library = [song(i) for i in range(4)]
        titles = [row["title"] for row in library]
        result, meta = self.pick(library, signals={"personalize": True, "disliked": titles, "history": titles})
        self.assertEqual(result, [])
        self.assertEqual(meta["candidate_count"], 0)
        self.assertNotIn("Artist", json.dumps(meta))

    def test_signals_are_ignored_without_opt_in(self):
        library = [song(i) for i in range(10)]
        baseline = self.pick(library)
        result = self.pick(library, signals={"personalize": False, "favorites": [library[0]["title"]], "history": [library[0]["title"]], "disliked": [row["title"] for row in library]})
        self.assertEqual(result, baseline)

    def test_factual_channels_and_exploration(self):
        library = [song(0, themes=["午后咖啡"]), song(1), song(2, artist="Artist 1"), *[song(i) for i in range(3, 20)]]
        result, meta = self.pick(library, signals={"personalize": True, "favorites": [library[1]["title"]]}, profile={"artists": ["Artist 4"]})
        self.assertTrue({"theme", "favorites", "favorite_artist", "profile_artist", "explore"} <= set(meta["available_channels"]))
        self.assertIn("explore", meta["channels"])
        self.assertIn("theme", meta["channels"])
        for row in result:
            evidence = row["recommendation"]
            self.assertTrue(evidence["reason"])
            if "theme" in evidence["sources"]:
                self.assertIn("午后咖啡", row["themes"])

    def test_seed_uses_only_same_artist_and_excludes_seed_itself(self):
        library = [song(0, "Seed Artist"), song(1, "Seed Artist"), *[song(i) for i in range(2, 8)]]
        result, meta = self.pick(library, signals={"seed": library[0]["title"]})
        self.assertNotIn(library[0]["title"], [row["title"] for row in result])
        self.assertTrue(meta["seed_artist_available"])
        related = [row for row in result if "seed_artist" in row["recommendation"]["sources"]]
        self.assertEqual(len(related), 1)
        self.assertEqual(artist_of(related[0]), "seed artist")
        _, unknown = self.pick(library, signals={"seed": "Unknown - Song"})
        self.assertFalse(unknown["seed_artist_available"])
        self.assertIn("暂无可用歌手资料", unknown["notice"])

    def test_explicit_seed_precedes_competing_theme_and_favorites(self):
        library = [song(0, "Seed Artist"), song(1, "Seed Artist"),
                   song(2, "Seed Artist", themes=["午后咖啡"]), *[song(i) for i in range(3, 20)]]
        result, _ = self.pick(library, signals={"seed": library[0]["title"], "personalize": True,
                                              "favorites": [library[2]["title"]]})
        self.assertTrue(any("seed_artist" in row["recommendation"]["sources"] for row in result))

    def test_repeated_artists_are_separated_when_possible(self):
        for library in ([song(0, "A"), song(1, "B"), song(2, "B")],
                        [song(0, "A"), song(1, "B"), song(2, "C"), song(3, "C")]):
            result, _ = select_songs(library, "午后咖啡", rng=random.Random(5))
            artists = [artist_of(row) for row in result]
            self.assertTrue(all(left != right for left, right in zip(artists, artists[1:])))

    def test_explicit_seed_can_revisit_same_artist_with_notice(self):
        library = [song(0, "Seed Artist"), song(1, "Seed Artist"), *[song(i) for i in range(2, 9)]]
        result, meta = self.pick(library, exclude=[library[1]["title"]], signals={"seed": library[0]["title"]})
        self.assertIn(library[1]["title"], [row["title"] for row in result])
        self.assertIn("同歌手选择", meta["notice"])
        self.assertTrue(meta["recent_relaxed"])

    def test_limited_artists_relax_without_duplicate_songs(self):
        result, meta = self.pick([song(i, "Only Artist") for i in range(6)])
        self.assertEqual(len({track_key(row) for row in result}), 4)
        self.assertTrue(meta["artist_limit_relaxed"])

    def test_curated_scenes_cover_current_catalog_and_all_six_themes(self):
        data = json.loads((ROOT / "backend/recommendation_catalog.json").read_text("utf-8"))
        with (ROOT / "musiclib/playlist.tsv").open(encoding="utf-8") as stream:
            rows = list(csv.reader((line for line in stream if not line.startswith("#")), delimiter="\t"))
        self.assertEqual(set(data["songs"]), {f"{row[1]} - {row[0]}" for row in rows})
        self.assertEqual({theme for labels in data["songs"].values() for theme in labels}, {"怀旧金曲", "午后咖啡", "元气早班", "深夜安眠", "城市漫游", "心情小站"})


# Reuse the repository's direct ASGI harness, without network services or keys.
if importlib.util.find_spec("fastapi") is not None:
    from test_frontend_contract import radio, request, verified
else:
    radio = None


@unittest.skipIf(radio is None, "FastAPI dependencies or ASGI harness unavailable")
class RecommendationAPI(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch.object(radio, "verify_song", side_effect=verified)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def show(self, library, llm, body=None):
        with patch.object(radio, "fetch_library", return_value=library), \
             patch.object(radio, "llm_json", side_effect=llm), \
             patch.object(radio, "tts_to_mp3", new=AsyncMock(return_value=False)), \
             patch.object(radio, "ensure_fallback_voice", new=AsyncMock(return_value=False)):
            status, content = await request("/api/show", body or {"theme": "午后咖啡"})
        return status, json.loads(content)

    async def test_shared_titles_keep_distinct_song_urls_in_narration_and_fallback(self):
        library = [{"title": "Shared title", "artist": "Artist A", "rel": "s/netease/11.mp3"},
                   {"title": "Shared title", "artist": "Artist B", "rel": "s/netease/22.mp3"}]
        for response in ({"introductions": ["Artist A intro", "Artist B intro"]}, {}):
            status, data = await self.show(library, lambda _: response)
            self.assertEqual(status, 200)
            urls = [row["url"] for row in data["items"] if row["kind"] == "song"]
            self.assertEqual(len(urls), 2)
            self.assertEqual(len(set(urls)), 2)
            self.assertEqual({url.split("?")[0].rsplit("/", 1)[-1] for url in urls}, {"11.mp3", "22.mp3"})

    async def test_model_cannot_change_duplicate_or_reorder_songs(self):
        library = [song(i) for i in range(5)]
        responses = [{"show": [{"type": "song", "title": "Invented"}]},
                     {"show": [{"type": "song", "title": library[0]["title"]}] * 4},
                     {"introductions": []}, [], {"introductions": [None] * 4}]
        for response in responses:
            status, data = await self.show(library, lambda _: response)
            self.assertEqual(status, 200)
            songs = [row for row in data["items"] if row["kind"] == "song"]
            self.assertEqual(len({row["title"] for row in songs}), 4)
            self.assertTrue(data["meta"]["recommendation"]["narration_fallback"])
            self.assertTrue(all("recommendation" in row for row in songs))

    async def test_model_failure_keeps_recent_exclusion_and_small_library(self):
        def unavailable(_):
            raise TimeoutError()
        library = [song(i) for i in range(5)]
        status, data = await self.show(library, unavailable, {"exclude": [library[0]["title"]]})
        self.assertEqual(status, 200)
        self.assertNotIn(library[0]["title"], [row["title"] for row in data["items"]])
        status, data = await self.show(library[:1], unavailable)
        self.assertEqual(status, 200)
        self.assertEqual(len([row for row in data["items"] if row["kind"] == "song"]), 1)

    async def test_legacy_response_cannot_reorder_selected_songs(self):
        library = [song(i) for i in range(4)]
        selected, meta = select_songs(library, "午后咖啡", rng=random.Random(23))
        with patch.object(radio, "select_songs", return_value=(selected, meta)):
            status, data = await self.show(library, lambda _: {"show": [
                part for row in reversed(selected) for part in
                ({"type": "talk", "text": "Reordered"}, {"type": "song", "title": row["title"]})]})
        self.assertEqual(status, 200)
        self.assertEqual([row["title"] for row in data["items"] if row["kind"] == "song"], [row["title"] for row in selected])
        self.assertTrue(data["meta"]["recommendation"]["narration_fallback"])

    async def test_valid_narration_and_privacy_gated_dislikes(self):
        library = [song(i) for i in range(4)]
        status, data = await self.show(library, lambda _: {"introductions": ["引介"] * 4, "closing": "结束"})
        self.assertEqual(status, 200)
        self.assertFalse(data["meta"]["recommendation"]["narration_fallback"])
        self.assertEqual(data["items"][-1]["text"], "结束")
        status, data = await self.show(library, lambda _: {}, {"recommendation": {"personalize": True, "disliked": [row["title"] for row in library]}})
        self.assertEqual(status, 422)
        self.assertIn("没有可推荐歌曲", data["detail"])

    async def test_private_lists_are_not_sent_to_narrator(self):
        prompts = []
        def narrate(prompt):
            prompts.append(prompt)
            return {"introductions": ["引介"] * 4}
        status, _ = await self.show([song(i) for i in range(5)], narrate, {
            "recommendation": {"personalize": True, "favorites": ["Private favorite"],
                               "history": ["Private history"], "disliked": ["Private dislike"]}})
        self.assertEqual(status, 200)
        self.assertEqual(len(prompts), 1)
        for private in ("Private favorite", "Private history", "Private dislike"):
            self.assertNotIn(private, prompts[0])

    async def test_input_limits_and_direct_requests_preserve_song_selection(self):
        status, _ = await self.show([song(1)], lambda _: {}, {"recommendation": {"favorites": ["x"] * 101}})
        self.assertEqual(status, 422)
        library = [song(1)]
        with patch.object(radio, "fetch_library", return_value=library), \
             patch.object(radio, "tts_to_mp3", new=AsyncMock(return_value=False)), \
             patch.object(radio, "ensure_fallback_voice", new=AsyncMock(return_value=False)), \
             patch.object(radio, "llm_json", return_value={"reply": "", "actions": [{"type": "play_song", "title": library[0]["title"]}]}):
            status, content = await request("/api/intent", {"message": "再放这首", "exclude": [library[0]["title"]]})
        self.assertEqual(status, 200)
        self.assertEqual(next(row for row in json.loads(content)["items"] if row["kind"] == "song")["title"], library[0]["title"])


if __name__ == "__main__":
    unittest.main()
