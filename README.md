# AI 电台主持人 · easy-radio-host

项目维护与 GitHub 协作规则见 [AGENTS.md](AGENTS.md)。

项目地址：[github.com/HachikoJ/easy-radio-host](https://github.com/HachikoJ/easy-radio-host) · 问题反馈：[Issues](https://github.com/HachikoJ/easy-radio-host/issues) · 当前状态：实验性公开项目

[English](#english) · [产品定位](#ai-电台主持人) · [核心体验](#效果) · [产品预览](#产品预览) · [快速开始](#部署云服务器--linux) · [API](#api) · [歌单维护](#歌单维护) · [项目治理](#项目治理) · [联系作者](#联系作者)

用 **DeepSeek 大模型**当电台主持人 + **MiniMax TTS** 口播 + **在线音乐多音源曲库**，在浏览器里生成并连续播放一期"电台节目"（主持人口播与歌曲交替）。适合部署到**云服务器**，无需自己准备/下载任何 mp3。

> ⚠️ 在线曲库涉及第三方歌曲版权。本项目仅用于**个人学习与体验**，请遵守相关平台规则，不要用于商业或侵权场景。

## 效果
- 点一下"生成一期节目" → **约 4~6 秒**出整期
- 主持人会基于歌单**智能选歌、串联话题**，口播由女声（MiniMax 或 edge-tts 降级）合成
- 网页自动连播：口播 → 歌 → 口播 → 歌…
- **音乐不落盘**：歌单只存「歌名、歌手、音源+id」，播放时经在线 API 动态拉取真实直链

## 产品预览

桌面端：

![小蓝电台桌面端界面，展示主题选择、节目生成和播放控制](/docs/screenshot-desktop.png)

移动端：

![小蓝电台移动端界面，展示响应式播放控制](/docs/screenshot-mobile.png)

截图来自当前仓库页面的本地预览；实际播放需要配置 AI 服务和在线音乐 API。

## 架构（云服务器版 / Python 裸跑）

```
用户浏览器                              云服务器
   │ GET / 静态页                         Server A: 主应用(8100, FastAPI)
   │ POST /api/show  ──────────────────► │   1) 读在线歌单 /songs.txt
   │                                     │   2) DeepSeek 生成节目 JSON(口播+选歌)
   │                                     │   3) 口播 → MiniMax TTS → mp3
   │ ◄──── {items: 口播mp3 + 歌URL} ───── │   4) 输出播放清单(歌曲 rel=s/<源>/<id>)
   │ 顺序播放 <audio>                     Server B: 曲库代理(8001)
   │   歌曲URL 302 → 第三方CDN直链 ◄────── │     读 playlist.tsv → /songs.txt
   │                                        + /s/<source>/<id>.mp3 动态取可播直链
```

## 在线曲库
曲库由 `musiclib/playlist.tsv` 管理，每行保存歌名、歌手、音源和歌曲 ID。播放时由 `musiclib/proxy_server.py` 调用在线音乐 API 获取可播直链，服务本身不保存音频文件。

在线音乐 API 提供多音源搜索与取链能力（搜索 `types=search`、播放取链 `types=url`）。

## 部署（云服务器 / Linux）
完整可执行手册见 **[DEPLOY-HANDOFF.md](DEPLOY-HANDOFF.md)**（给 codex / 新服务器一键对照）。要点：
1. `python3 -m venv .venv && pip install -r backend/requirements.txt zhconv`
2. 填 `radio.env`：`DEEPSEEK_KEY`、`MINIMAX_KEY`，并将曲库地址配置为 `http://127.0.0.1:8001/songs.txt` 和 `http://<公网IP>:8001`
3. 两个 systemd 服务：主应用 8100 + 曲库代理 8001（单元文件见 DEPLOY-HANDOFF.md）
4. 云安全组放行 8100、8001
5. 浏览器打开 `http://<公网IP>:8100`

## API
- `backend/app.py`
  | 方法 | 路径 | 说明 |
  |---|---|---|
  | POST | /api/show | 生成一期节目 `{items:[{kind:talk|song,url,text,title}],meta}` |
  | POST | /api/chat | 对话/点歌 |
  | GET | /voice/*.mp3 | 口播语音 |
- `musiclib/proxy_server.py`（8001）
  | 方法 | 路径 | 说明 |
  |---|---|---|
  | GET | /songs.txt | 曲库列表(供 app) |
  | GET | /s/<source>/<id>.mp3 | 在线取直链 → 302 |

## 歌单维护
编辑 `musiclib/playlist-source.tsv`（歌名<TAB>歌手），删掉旧 `musiclib/playlist.tsv`，运行：
```bash
/opt/easy-radio-host/.venv/bin/python3 musiclib/resolve_multi.py
```
会自动多音源裁决出每首歌的原唱可播版本。

---

## 致谢 / Credits（避免侵权）
本项目使用以下第三方资源，并保留相应版权归属：

- **easy-radio-host 原始项目**（作者 `weak0001`）
  - 原仓库：https://gitee.com/weak0001/easy-radio-host
  - 原作的全部署名与版权归原作者 `weak0001` 所有
- **在线音乐 API**（music-api.gdstudio.xyz）：提供**搜索/取链**接口
  - API 地址：https://music-api.gdstudio.xyz/api.php
  - 其版权归平台方，详见其站内声明；**歌词/歌曲版权属于相应权利人**
- **DeepSeek**：主持人大脑（`deepseek-chat`），版权归 DeepSeek
- **MiniMax TTS（海螺）**：口播语音合成，版权归 MiniMax
- 其余第三方依赖见各项目 LICENSE

**免责声明**：本项目不存储、不提供任何音频文件；在线曲库仅作 API 转发。请仅用于学习和测试合法内容，商用或再发布请自行确认授权。

## 项目治理

- [贡献指南](CONTRIBUTING.md)：本地运行、验证、Issue 和 Pull Request 规范
- [行为准则](CODE_OF_CONDUCT.md)：社区交流边界
- [安全政策](SECURITY.md)：敏感信息和安全问题报告方式
- [变更记录](CHANGELOG.md)：版本变更摘要
- [GitHub Actions](.github/workflows/validate.yml)：提交和 PR 的 Python 语法校验

关注项目：[![GitHub stars](https://img.shields.io/github/stars/HachikoJ/easy-radio-host?style=flat)](https://github.com/HachikoJ/easy-radio-host) [![Star History](https://api.star-history.com/svg?repos=HachikoJ/easy-radio-host&type=Date)](https://star-history.com/#HachikoJ/easy-radio-host&Date)

## 联系作者

请通过 [GitHub Issues](https://github.com/HachikoJ/easy-radio-host/issues) 提交 Bug、功能建议和部署问题；安全问题请使用 [Security Advisories](https://github.com/HachikoJ/easy-radio-host/security/advisories/new)。作者主页：[HachikoJ](https://github.com/HachikoJ)。

## English

[中文 README](README.md) · [Repository](https://github.com/HachikoJ/easy-radio-host) · [Issues](https://github.com/HachikoJ/easy-radio-host/issues) · [Preview](#产品预览) · [Quick start](#quick-start) · [API](#api)

`easy-radio-host` is an online AI radio host. DeepSeek creates themed show scripts, MiniMax or edge-tts synthesizes the host voice, and an online music API resolves playable tracks at request time. Audio tracks are not stored by this project.

### Features

- Generate a themed show with alternating host segments and songs.
- Chat with the host and request songs.
- Maintain a metadata-only playlist and resolve tracks from multiple online sources.
- Run the FastAPI app and music proxy on a Linux server.

### Product preview

![Xiaolan Radio desktop interface](/docs/screenshot-desktop.png)

![Xiaolan Radio mobile interface](/docs/screenshot-mobile.png)

### Quick start

Requirements: Python 3.10+ and API keys for the enabled AI services. Create a virtual environment, install `backend/requirements.txt` and `zhconv`, configure `radio.env`, then run the app on port 8100 and `musiclib/proxy_server.py` on port 8001. Full instructions are in [DEPLOY-HANDOFF.md](DEPLOY-HANDOFF.md).

### Privacy and limitations

API keys are supplied by the operator and must stay outside Git. Requests are sent to DeepSeek, MiniMax/edge-tts and the configured music API. Availability, licensing and playback rights belong to those services and the respective rights holders. AI-generated scripts are not guaranteed to be factual.

### Support and license

Please use [GitHub Issues](https://github.com/HachikoJ/easy-radio-host/issues) for reproducible bugs and feature requests. Contribution rules are in [CONTRIBUTING.md](CONTRIBUTING.md); security reports should use [Security Advisories](https://github.com/HachikoJ/easy-radio-host/security/advisories/new). A repository license is not yet selected because the upstream copyright terms need confirmation.
