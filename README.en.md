<a id="top"></a>

<p align="center">
  <img src="assets/brand/tingjian-logo.png" alt="Tingjian logo: a blue sound-wave speech bubble with a coral on-air signal" width="144">
</p>

<h1 align="center">Tingjian · 听间</h1>

<p align="center"><strong>Choose a theme. Let music take it from here.</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/FastAPI-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/DeepSeek-AI-1677E8" alt="DeepSeek AI">
  <a href="https://github.com/HachikoJ/easy-radio-host"><img src="https://img.shields.io/github/stars/HachikoJ/easy-radio-host?style=flat" alt="GitHub stars"></a>
</p>

<p align="center">
  <a href="https://audio.deline.top">Listen online</a> · <a href="README.md">中文</a> · <a href="https://www.deline.top">Personal site</a>
</p>

<p align="center">
  <a href="#features">Features</a> · <a href="#product-preview">Preview</a> · <a href="#quick-start">Quick start</a> · <a href="#project-resources">Resources</a> · <a href="#contact">Contact</a>
</p>

Tingjian is an AI music radio for listeners who enjoy themed listening and are comfortable hosting their own service. Its recommendation engine selects tracks using themes and optional preferences; the host, Xiaolan, connects them with commentary and synthesizes narration. Your browser plays narration and songs in sequence. Tracks come from an online music API, so no local music collection is required.

**Repository:** [HachikoJ/easy-radio-host](https://github.com/HachikoJ/easy-radio-host)

**Listen online:** [audio.deline.top](https://audio.deline.top). Choose a theme and click "开始收听" (Start listening). You can also self-host using the steps below.

## Features

- **Six themes:** Afternoon Coffee, City Walk, Sleep at Night, Nostalgic Hits, Morning Energy, and Mood Station; the program selects tracks, and DeepSeek writes narration in the selected order.
- **Multiple recommendation sources:** Combine themes, favorite tracks, favorite artists, artist preferences configured by the deployment owner, and exploration candidates. Extend a current track with more works by the same artist and see the actual selection reasons.
- **Deduplication and variety:** No repeated tracks within a show; recent tracks are avoided where possible and artists are spread out. Shows shorten when candidates are scarce, and any recent-track reuse or relaxed artist limits are disclosed.
- **Optional preferences:** Listening settings bring together continuous playback, translations, lyric timing, and song preferences. "按我的偏好选歌" (Use my preferences) is off by default. Enabling it allows local favorites, history, and "Recommend less" titles to inform the current recommendation, with privacy details available before opting in. "Recommend less" can be undone; ordinary skips and playback failures are not treated as dislikes, and explicit song requests remain available.
- **Host narration:** MiniMax uses `Chinese (Mandarin)_Warm_Girl` by default, with edge-tts fallback support. ffmpeg balances newly generated narration, while songs play at 85% of the master volume to reduce level differences between speech and music. Original narration is retained when ffmpeg is unavailable or processing fails.
- **Continuous playback:** A show queue, previous/next segments, seeking and volume, automatic continuation, and stop controls.
- **Focused listening:** A single listening view adapts the disc and lyrics to viewport height to keep the main experience on one screen. The track title shares a row with right-aligned following, animation, and settings controls. Theme stations, the queue/favorites/history, and chat open on demand while the bottom player stays available. Light/dark appearance, keyboard controls, and system media controls in supported browsers are included. Credits and the author's GitHub open in new tabs from the top right; credits display Chinese by default, with English shown after selecting English.
- **Favorites and history:** Store up to 100 favorites and 50 recent tracks locally in your browser, deduplicated by title; history records songs only once playback actually starts.
- **Song requests:** Chat with Xiaolan, request tracks, or control playback; cancel generation, retry failures, and keep your draft when a request fails.
- **Online library:** Store track names, artists, sources, and IDs; resolve playback URLs on demand. Unavailable URLs can fall back to an available bitrate for the same track ID. Playback failures trigger one automatic refresh, followed by retry and next-segment controls if playback still fails.
- **Synchronized lyrics:** A spacious lyric view is visible by default, with faded theme photography behind highlighted text and independent scrolling inside the lyric area; the same area shows the transcript during host narration. The fixed player shows the current line; tapping its lyric preview focuses the lyric view and resumes following. LRC lyrics follow playback by default, with tap-to-seek including 0 seconds. Following resumes 3 seconds after manual browsing; only explicitly switching it off keeps it disabled. Delay adjustment from -10 to +10 seconds and optional timestamped translations are available. Loading, missing lyrics, failure, and timeout have distinct states; plain text stays untimed.
- **Playback animation:** A rotating disc displays a theme image at its center, surrounded by a black ring supporting colorful glowing edges and layered translucent 3D waves. When the browser and audio source support analysis, the waves flow with actual frequency bands, bass, and volume; otherwise, a smooth playback animation takes over. A 2D ripple fallback is available without WebGL. Motion stops during buffering, pauses, or when the page is hidden. The animation toggle is remembered and system reduced-motion preferences are respected. The theme image is not the track's album artwork.

## Product preview

### Desktop

<p align="center">
  <a href="docs/radio-desktop.png"><img src="docs/radio-desktop.png" alt="Tingjian desktop: disc and current track, spacious lyrics, and bottom player" width="100%"></a>
</p>

### Mobile

<table>
  <tr>
    <th width="33%">Listening</th>
    <th width="33%">Lyrics and animation</th>
    <th width="33%">Listening settings</th>
  </tr>
  <tr>
    <td align="center" valign="top"><a href="docs/radio-mobile.png"><img src="docs/radio-mobile.png" alt="Tingjian mobile: compact disc area, lyrics, and bottom playback controls" width="100%"></a></td>
    <td align="center" valign="top"><a href="docs/radio-lyrics-mobile.png"><img src="docs/radio-lyrics-mobile.png" alt="Tingjian mobile lyrics view: compact track details, lyrics, and bottom playback controls" width="100%"></a></td>
    <td align="center" valign="top"><a href="docs/radio-recommendations-mobile.png"><img src="docs/radio-recommendations-mobile.png" alt="Tingjian mobile listening settings: playback options, lyric timing, and local song preferences" width="100%"></a></td>
  </tr>
</table>

<details>
<summary>More desktop screenshots: dark appearance, lyrics and animation, listening settings</summary>

#### Dark appearance

<p align="center">
  <a href="docs/radio-focus.png"><img src="docs/radio-focus.png" alt="Tingjian dark appearance: rotating disc, current track, lyrics, and playback controls" width="100%"></a>
</p>

#### Lyrics and animation

<p align="center">
  <a href="docs/radio-lyrics.png"><img src="docs/radio-lyrics.png" alt="Tingjian desktop lyrics: soft theme background, highlighted text, and compact following and animation toggles" width="100%"></a>
</p>

#### Listening settings

<p align="center">
  <a href="docs/radio-recommendations.png"><img src="docs/radio-recommendations.png" alt="Tingjian desktop listening settings: preference toggle, privacy details, and Recommend less management" width="100%"></a>
</p>

</details>

Screenshots show the actual interface in the explicitly labeled demo mode, using original instrumental audio and original sample text without reproducing third-party song lyrics. Theme photos represent listening settings, not actual album artwork. Fixed demo tracks and reasons are previews and do not establish recommendation quality; online tracks and availability on the [live site](https://audio.deline.top) depend on third-party services. Click any screenshot to view the full-size image.

## How it works

```text
Browser
  → Main app :8100
      → Candidate fusion, recent-track filtering, deduplication, and artist variety
      → DeepSeek writes narration in the selected track order
      → MiniMax / edge-tts synthesizes narration
      → Online library proxy :8001 reads the playlist
  ← Narration and song playback queue
  → Proxy resolves track URLs through the music API and redirects playback
```

The proxy reads `musiclib/playlist.tsv` and exposes titles and relative paths at `/songs.txt`. The `/s/<source>/<id>.mp3` endpoint resolves a track URL and returns a 307 redirect. Songs are not stored locally; generated narration is stored under `DATA_DIR/voice/` (`/var/lib/tingjian/voice/` in the Tencent Cloud deployment).

Recommendations use the current catalog and available metadata without connecting to Embeat models, vector databases, or datasets. Theme matching uses tags curated by this project, not acoustic analysis or collaborative filtering. Shows target four tracks and shorten when candidates are scarce. If the model fails, template narration uses the same selected tracks. See [recommendation design and the Embeat reference record](docs/EMBEAT-ADAPTATION.md) for rules, privacy boundaries, and validation.

## Quick start

Requires Python 3.10+; install ffmpeg to normalize newly generated narration. See the [deployment guide](DEPLOY-HANDOFF.md) for Linux setup, systemd configuration, and troubleshooting. The detailed guide is currently in Chinese.

```bash
git clone https://github.com/HachikoJ/easy-radio-host.git
cd easy-radio-host
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt zhconv
```

1. Follow the deployment guide to create `/etc/tingjian/radio.env` with DeepSeek, MiniMax, and service URLs, using file permissions of 600.
2. Start the main app (8100) and online library proxy (8001), both listening only on `127.0.0.1`.
3. Configure Nginx and HTTPS to serve the page, `/api/`, `/voice/`, and `/music/` on the same domain, then generate a show. Only ports 80 and 443 need public access.

### Try the interface without API keys

With Node.js 22+ already installed, start the local demo without third-party services:

```bash
node scripts/serve-demo.mjs
```

Open the [local demo](http://127.0.0.1:8131/?demo=1). Fixed demo shows are enabled only with an explicit `?demo=1`; the demo does not call AI or music APIs and does not establish online service availability. Follow the deployment steps above for real listening.

The demo uses original synthesized instrumental music and clearly labeled original demo copy. Text in the demo lyrics view is not the song's lyrics.

### Key configuration

| Variable | Purpose |
| --- | --- |
| `DEEPSEEK_KEY` | API key for show planning and chat |
| `MINIMAX_KEY` | API key for host narration |
| `MINIMAX_VOICE` | Host voice, defaulting to `Chinese (Mandarin)_Warm_Girl` |
| `NAS_LIST_URL` | Playlist URL, typically `http://127.0.0.1:8001/songs.txt` |
| `NAS_BASE_URL` | Online library proxy URL accessible from the browser |
| `RADIO_BASE` | Main app URL accessible from the browser |
| `DATA_DIR` | Narration and runtime data directory |

The `NAS_*` names are retained for compatibility and point to the online library proxy. A remote browser cannot reach the server through the server's own `127.0.0.1`; use reachable server URLs for playback.

Normalization uses two-pass ffmpeg `loudnorm`, targeting -14 LUFS with a -1.5 dBTP true-peak limit and `dual_mono` enabled. Missing ffmpeg, timeouts, or processing failures retain the original audio without blocking narration playback. This applies only to newly generated narration, without reprocessing existing narration or third-party songs. The 0.85 song volume factor leaves the displayed master volume unchanged and does not guarantee identical perceived loudness across all sources.

## API

| Service | Method | Path | Description |
| --- | --- | --- | --- |
| Main app :8100 | POST | `/api/show` | Generate a show playback queue |
| Main app :8100 | POST | `/api/intent` | Frontend chat, song requests, and playback controls |
| Main app :8100 | POST | `/api/chat` | Retained compatibility endpoint for chat and song requests |
| Main app :8100 | GET | `/voice/*.mp3` | Host narration |
| Library proxy :8001 | GET | `/songs.txt` | Online playlist metadata |
| Library proxy :8001 | GET | `/s/<source>/<id>.mp3` | Resolve a track URL and redirect |
| Same-origin `/music/` → library proxy :8001 | GET | `/music/lyrics/{source}/{song_id}.json` | Fetch lyrics and available translations for the current song; the direct proxy path is `/lyrics/{source}/{song_id}.json` |

`POST /api/show` retains `theme` and `exclude`, and adds an optional `recommendation` object:

```json
{
  "theme": "午后咖啡",
  "exclude": [],
  "recommendation": {
    "personalize": false,
    "favorites": [],
    "history": [],
    "disliked": [],
    "seed": ""
  }
}
```

`favorites`, `history`, and `disliked` are title arrays used only when `personalize` is `true`. `seed` is the explicitly selected track title for extending an artist. Each song's `recommendation.sources` and `recommendation.reason` provide actual candidate sources and a selection reason; `meta.recommendation` reports candidate and fallback information. Existing clients can omit the new fields. Explicit song requests still use `/api/intent`.

## Playlist maintenance

In the deployment directory `/opt/easy-radio-host`, edit `musiclib/playlist-source.tsv` with one track name and artist per line, separated by a tab. Back up the existing `musiclib/playlist.tsv`, then run:

```bash
/opt/easy-radio-host/.venv/bin/python3 /opt/easy-radio-host/musiclib/resolve_multi.py
```

The script rewrites the resolved playlist, searches multiple sources, filters versions, and checks candidate playback URLs. Matching and availability depend on third-party services; review missing tracks and incorrect versions.

## Privacy and limitations

- Never commit API keys, cookies, or `radio.env` to GitHub.
- Show themes, conversations, and track metadata are sent to the relevant AI or music services; narration and runtime data are stored on the server.
- Favorites, history, and "Recommend less" records are stored in the current browser without cross-device sync; demo and real listening records are separate. Clearing site data removes these records. If local storage is unavailable, records last only for the current page.
- "Use my preferences" is off by default. When enabled, favorite, history, and "Recommend less" titles accompany each show request to the Tingjian server, where they are used only for that request without adding a server-side preference profile. DeepSeek receives selected tracks and show context, not these complete preference lists. Turning the option off stops sending these local preferences. Recent tracks in the current session still help avoid repeats, and extending an artist sends the explicitly selected seed title.
- Existing global artist preferences are configured by the deployment owner, not maintained as individual listener profiles. Recommendation reasons distinguish this source from browser favorites.
- Replaying a saved title requests a fresh match and playback URL. Favorites do not retain exact track IDs or permanent audio links, so a different version may be selected.
- DeepSeek, MiniMax, and other services may incur charges. Pricing and quotas are set by each provider.
- AI narration is not guaranteed to be factual. Track availability, version matching, and response times depend on third-party services.
- Lyrics and translations come from the existing GD music API and may be unavailable or differ from the audio version. Only timestamped lyrics are synchronized; plain text is not assigned estimated timings. The proxy caches up to 128 responses in memory for 300 seconds each, without saving lyric files or distributing a lyric library in the repository. Lyrics belong to their respective rights holders.
- The project is for personal learning and experimentation. Song rights belong to their respective owners; follow platform rules.
- The project is experimental. The full upstream licensing terms have not been confirmed, and the repository does not yet declare a unified open-source license.

## Project resources

- [Deployment guide](DEPLOY-HANDOFF.md): service configuration, playlist maintenance, and troubleshooting.
- [Contributing](CONTRIBUTING.md): validation commands and Pull Request guidelines.
- [Code of Conduct](CODE_OF_CONDUCT.md) · [Security Policy](SECURITY.md).
- [Changelog](CHANGELOG.md) · [Collaboration guidelines](AGENTS.md).
- [Design guidelines](DESIGN.md) · [Claudio adaptation and roadmap](docs/CLAUDIO-ADAPTATION.md).
- [Recommendation design and Embeat reference record](docs/EMBEAT-ADAPTATION.md): candidate fusion, boundaries, fallback rules, and evaluation.
- [Continuous integration](https://github.com/HachikoJ/easy-radio-host/actions): Python syntax, API contracts, and frontend static-server checks.

## Credits

- [Original easy-radio-host project](https://gitee.com/weak0001/easy-radio-host) by `weak0001`; original attribution and copyright ownership are retained.
- [Claudio](https://github.com/hllqkb/Claudio) by `hllqkb`, MIT; the Tingjian frontend independently implements interaction ideas from its immersive playback, light/dark themes, favorites/history, and system media controls. See [third-party sources and licenses](THIRD_PARTY_NOTICES.md), including the source revision and complete license text.
- [Qiaomu Music Player Web](https://github.com/joeseesun/qiaomu-music-player-web) by Qiaomu / 向阳乔木, MIT; common interactions such as lyric following, tap-to-seek, and playback animation informed an independent implementation. No source code or assets were copied.
- [Embeat](https://github.com/gdstudio-org/Embeat/tree/7617a505ec42f109685802d1a3319e1957ac0a99) by GD Studio informed our independent implementation of general ideas around candidate fusion, deduplication, diversity controls, and explainable recommendations. Its reviewed README and root license differ in stated scope. No source code, models, data, or branding were copied; see the [license review record](THIRD_PARTY_NOTICES.md#embeat).
- [lrc-kit 1.2.1](https://www.npmjs.com/package/lrc-kit/v/1.2.1), Copyright (c) 2016 Weirong Xu, MIT; used for LRC parsing with the [full license](backend/static/vendor/lrc-kit/LICENSE) and [source modification record](THIRD_PARTY_NOTICES.md#lrc-kit) retained.
- [Three.js 0.170.0](https://github.com/mrdoob/three.js/tree/r170), Copyright © 2010-2024 three.js authors, MIT; a local module renders the 3D disc and waves, with the [full license](backend/static/vendor/three/LICENSE) retained.
- [Lucide](https://lucide.dev) provides UI icons under ISC; [Unsplash](https://unsplash.com) provides theme photography. See [individual asset sources](backend/static/assets/SOURCES.md).
- [Online music API](https://music-api.gdstudio.xyz/api.php) for multi-source search and URL resolution.
- DeepSeek, MiniMax, edge-tts, and other dependencies; their rights and terms remain with their respective owners.

## GitHub activity

[![Star History Chart](https://api.star-history.com/svg?repos=HachikoJ/easy-radio-host&type=Date)](https://star-history.com/#HachikoJ/easy-radio-host&Date)

[Open Star History](https://star-history.com/#HachikoJ/easy-radio-host&Date)

## Contact

Get in touch to discuss AI music products, share feedback, or support the project:

- Personal site: [www.deline.top](https://www.deline.top)
- GitHub: [HachikoJ](https://github.com/HachikoJ) · [Report an issue](https://github.com/HachikoJ/easy-radio-host/issues)
- WeChat: `hostrow`; please mention “Tingjian”
- Email: [946106011@qq.com](mailto:946106011@qq.com)

<table>
  <tr>
    <td align="center" valign="top" width="33%">
      <strong>WeChat contact</strong><br><br>
      <a href="assets/wechat-contact.png"><img src="assets/wechat-contact.png" alt="Wilson's WeChat contact QR code" width="180"></a>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>WeChat support</strong><br><br>
      <a href="assets/donate-wechat.png"><img src="assets/donate-wechat.png" alt="WeChat support QR code" width="180"></a>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>Alipay support</strong><br><br>
      <a href="assets/donate-alipay.png"><img src="assets/donate-alipay.png" alt="Alipay support QR code" width="180"></a>
    </td>
  </tr>
</table>

## Join the community

Share listening themes, discuss your experience, and report problems.

<p align="center">
  <a href="assets/group-qr.jpg"><img src="assets/group-qr.jpg" alt="WeChat discussion group QR code" width="240"></a>
</p>

<p align="right"><a href="#top">Back to top</a></p>
