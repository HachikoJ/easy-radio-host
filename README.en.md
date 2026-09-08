# AI Radio Host · easy-radio-host

[中文 README](README.md) · [Repository](https://github.com/HachikoJ/easy-radio-host) · [Issues](https://github.com/HachikoJ/easy-radio-host/issues) · [Product preview](#product-preview) · [Quick start](#quick-start) · [API](#api) · [Contact](#contact)

**An online AI radio host that turns a playlist into a narrated, continuously playable show.** DeepSeek writes the show flow, MiniMax or edge-tts synthesizes the host voice, and an online music API resolves playable tracks on demand. Audio tracks are not stored by this project.

## Features

- Generate themed shows with alternating host segments and songs.
- Chat with the host and request songs.
- Maintain a metadata-only playlist resolved from multiple online sources.
- Run the FastAPI app and music proxy on a Linux server.

## Product preview

![Xiaolan Radio desktop interface, showing show generation and playback controls](/docs/screenshot-desktop.png)

![Xiaolan Radio mobile interface, showing responsive playback controls](/docs/screenshot-mobile.png)

Screenshots are captured from the current repository page. Actual playback requires configured AI services and the online music API.

## Quick start

Requirements: Python 3.10+ and API keys for the enabled AI services.

```bash
python3 -m venv .venv
pip install -r backend/requirements.txt zhconv
```

Configure `radio.env`, run `backend/app.py` on port 8100 and `musiclib/proxy_server.py` on port 8001. See [DEPLOY-HANDOFF.md](DEPLOY-HANDOFF.md) for the complete deployment guide.

## API

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/show` | Generate a narrated show |
| POST | `/api/chat` | Chat and request a song |
| GET | `/songs.txt` | Online playlist metadata |
| GET | `/s/<source>/<id>.mp3` | Resolve a playable track |

## Privacy and limitations

API keys are supplied by the operator and must stay outside Git. Requests are sent to DeepSeek, MiniMax/edge-tts and the configured music API. Availability, licensing and playback rights belong to those services and their respective rights holders. AI-generated scripts are not guaranteed to be factual.

## Project governance

- [Contributing](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)
- [Changelog](CHANGELOG.md)
- [Validation workflow](.github/workflows/validate.yml)

[![GitHub stars](https://img.shields.io/github/stars/HachikoJ/easy-radio-host?style=flat)](https://github.com/HachikoJ/easy-radio-host) [![Star History](https://api.star-history.com/svg?repos=HachikoJ/easy-radio-host&type=Date)](https://star-history.com/#HachikoJ/easy-radio-host&Date)

## Contact

- GitHub: [HachikoJ](https://github.com/HachikoJ)
- Issues: [project issue tracker](https://github.com/HachikoJ/easy-radio-host/issues)
- Email: `946106011@qq.com`
- WeChat: `hostrow` (please mention “AI Radio” when adding)

<table>
  <tr>
    <td align="center"><strong>WeChat contact</strong><br><img src="assets/wechat-contact.png" alt="WeChat contact QR code" width="220"></td>
    <td align="center"><strong>WeChat payment</strong><br><img src="assets/donate-wechat.png" alt="WeChat payment QR code" width="220"></td>
    <td align="center"><strong>Alipay payment</strong><br><img src="assets/donate-alipay.png" alt="Alipay payment QR code" width="220"></td>
  </tr>
</table>

WeChat group for discussion and feedback:

<p align="center"><img src="assets/group-qr.jpg" alt="WeChat discussion group QR code" width="260"></p>

The repository license is pending confirmation of the upstream copyright terms.
