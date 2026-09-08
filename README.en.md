<a id="top"></a>

# Tingjian · 听间

<p align="center">
  <img src="assets/brand/tingjian-logo.png" alt="Tingjian logo: a blue sound-wave speech bubble with a coral on-air signal" width="144">
</p>

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-009688)
![DeepSeek](https://img.shields.io/badge/DeepSeek-AI-1677E8)
[![GitHub stars](https://img.shields.io/github/stars/HachikoJ/easy-radio-host?style=flat)](https://github.com/HachikoJ/easy-radio-host)

[中文](README.md) · [Personal site](https://www.deline.top) · [Features](#features) · [Preview](#product-preview) · [Quick start](#quick-start) · [Resources](#project-resources) · [Contact](#contact)

**Choose a theme. Let music take it from here.**

Tingjian is an AI music radio for listeners who enjoy themed listening and are comfortable hosting their own service. The host, Xiaolan, selects tracks, connects them with commentary, and synthesizes narration. Your browser plays narration and songs in sequence. Tracks come from an online music API, so no local music collection is required.

**Repository:** [HachikoJ/easy-radio-host](https://github.com/HachikoJ/easy-radio-host)

**Access:** After deployment, open port 8100 on your server. This repository does not provide a hosted listening service.

## Features

- **Six themes:** Afternoon Coffee, City Walk, Sleep at Night, Nostalgic Hits, Morning Energy, and Mood Station; DeepSeek arranges shows around the theme and playlist.
- **Host narration:** MiniMax synthesizes the voice, with edge-tts fallback support.
- **Continuous playback:** A show queue, previous/next segments, seeking and volume, automatic continuation, and stop controls.
- **Focused listening:** Desktop and mobile layouts, light/dark appearance, immersive mode, keyboard controls, and system media controls in supported browsers.
- **Favorites and history:** Store up to 100 favorites and 50 recent tracks locally in your browser, deduplicated by title; history records songs only once playback actually starts.
- **Song requests:** Chat with Xiaolan, request tracks, or control playback; cancel generation, retry failures, and keep your draft when a request fails.
- **Online library:** Store track names, artists, sources, and IDs; resolve playback URLs on demand.

## Product preview

### Desktop

<p>
  <img src="docs/radio-desktop.png" alt="Tingjian desktop demo: theme selection, show queue, chat, and bottom player" width="100%">
</p>

### Mobile

<p>
  <img src="docs/radio-mobile.png" alt="Tingjian mobile demo: theme artwork, show, and playback controls" width="375">
</p>

### Immersive mode

<p>
  <img src="docs/radio-focus.png" alt="Tingjian immersive demo: current segment, theme artwork, and playback controls" width="100%">
</p>

Screenshots show the current frontend in local demo mode, labeled “演示节目” (demo show). The demo uses audio synthesized for this project and fixed replies; theme photos are not actual album artwork. Real show generation and online music playback require configured services.

## How it works

```text
Browser
  → Main app :8100
      → DeepSeek arranges the show
      → MiniMax / edge-tts synthesizes narration
      → Online library proxy :8001 reads the playlist
  ← Narration and song playback queue
  → Proxy resolves track URLs through the music API and redirects playback
```

The proxy reads `musiclib/playlist.tsv` and exposes titles and relative paths at `/songs.txt`. The `/s/<source>/<id>.mp3` endpoint resolves a track URL and returns a 302 redirect. Songs are not stored locally; generated narration is stored under `data/voice/` on the server.

## Quick start

Requires Python 3.10+. See the [deployment guide](DEPLOY-HANDOFF.md) for Linux setup, systemd configuration, and troubleshooting. The detailed guide is currently in Chinese.

```bash
git clone https://github.com/HachikoJ/easy-radio-host.git
cd easy-radio-host
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt zhconv
```

1. Create `radio.env` using the deployment guide; configure DeepSeek, MiniMax, and service URLs.
2. Start the main app (8100) and online library proxy (8001).
3. Make both ports accessible from your browser, open the main app, and generate a show.

### Try the interface without API keys

With Node.js 22+ already installed, start the local demo without third-party services:

```bash
node scripts/serve-demo.mjs
```

Open the [local demo](http://127.0.0.1:8131/?demo=1). Fixed demo shows are enabled only with an explicit `?demo=1`; the demo does not call AI or music APIs and does not establish online service availability. Follow the deployment steps above for real listening.

### Key configuration

| Variable | Purpose |
| --- | --- |
| `DEEPSEEK_KEY` | API key for show planning and chat |
| `MINIMAX_KEY` | API key for host narration |
| `NAS_LIST_URL` | Playlist URL, typically `http://127.0.0.1:8001/songs.txt` |
| `NAS_BASE_URL` | Online library proxy URL accessible from the browser |
| `RADIO_BASE` | Main app URL accessible from the browser |
| `DATA_DIR` | Narration and runtime data directory |

The `NAS_*` names are retained for compatibility and point to the online library proxy. A remote browser cannot reach the server through the server's own `127.0.0.1`; use reachable server URLs for playback.

## API

| Service | Method | Path | Description |
| --- | --- | --- | --- |
| Main app :8100 | POST | `/api/show` | Generate a show playback queue |
| Main app :8100 | POST | `/api/intent` | Frontend chat, song requests, and playback controls |
| Main app :8100 | POST | `/api/chat` | Retained compatibility endpoint for chat and song requests |
| Main app :8100 | GET | `/voice/*.mp3` | Host narration |
| Library proxy :8001 | GET | `/songs.txt` | Online playlist metadata |
| Library proxy :8001 | GET | `/s/<source>/<id>.mp3` | Resolve a track URL and redirect |

## Playlist maintenance

In the deployment directory `/opt/easy-radio-host`, edit `musiclib/playlist-source.tsv` with one track name and artist per line, separated by a tab. Back up the existing `musiclib/playlist.tsv`, then run:

```bash
/opt/easy-radio-host/.venv/bin/python3 /opt/easy-radio-host/musiclib/resolve_multi.py
```

The script rewrites the resolved playlist, searches multiple sources, filters versions, and checks candidate playback URLs. Matching and availability depend on third-party services; review missing tracks and incorrect versions.

## Privacy and limitations

- Never commit API keys, cookies, or `radio.env` to GitHub.
- Show themes, conversations, and track metadata are sent to the relevant AI or music services; narration and runtime data are stored on the server.
- Favorites and history store only titles, themes, and timestamps in the current browser, without cross-device sync; demo and real listening records are separate. Clearing site data removes these records. If local storage is unavailable, records last only for the current page.
- Replaying a saved title requests a fresh match and playback URL. Favorites do not retain exact track IDs or permanent audio links, so a different version may be selected.
- DeepSeek, MiniMax, and other services may incur charges. Pricing and quotas are set by each provider.
- AI narration is not guaranteed to be factual. Track availability, version matching, and response times depend on third-party services.
- The project is for personal learning and experimentation. Song rights belong to their respective owners; follow platform rules.
- The project is experimental. The full upstream licensing terms have not been confirmed, and the repository does not yet declare a unified open-source license.

## Project resources

- [Deployment guide](DEPLOY-HANDOFF.md): service configuration, playlist maintenance, and troubleshooting.
- [Contributing](CONTRIBUTING.md): validation commands and Pull Request guidelines.
- [Code of Conduct](CODE_OF_CONDUCT.md) · [Security Policy](SECURITY.md).
- [Changelog](CHANGELOG.md) · [Collaboration guidelines](AGENTS.md).
- [Design guidelines](DESIGN.md) · [Claudio adaptation and roadmap](docs/CLAUDIO-ADAPTATION.md).
- [Continuous integration](https://github.com/HachikoJ/easy-radio-host/actions): Python syntax, API contracts, and frontend static-server checks.

## Credits

- [Original easy-radio-host project](https://gitee.com/weak0001/easy-radio-host) by `weak0001`; original attribution and copyright ownership are retained.
- [Claudio](https://github.com/hllqkb/Claudio) by `hllqkb`, MIT; the Tingjian frontend independently implements interaction ideas from its immersive playback, light/dark themes, favorites/history, and system media controls. See [third-party sources and licenses](THIRD_PARTY_NOTICES.md), including the source revision and complete license text.
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
