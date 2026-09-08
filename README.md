# AI 电台主持人 · easy-radio-host

用 **DeepSeek 大模型**当电台主持人 + **MiniMax TTS** 口播 + **在线音乐多音源曲库**，在浏览器里生成并连续播放一期"电台节目"（主持人口播与歌曲交替）。适合部署到**云服务器**，无需自己准备/下载任何 mp3。

> ⚠️ 在线曲库涉及第三方歌曲版权，本改造仅用于**个人学习/体验**低成本跑通"主持人+语音+放歌"，请勿用于商业或侵权场景，播放版权歌曲请遵守相关平台规则。

## 效果
- 点一下"生成一期节目" → **约 4~6 秒**出整期
- 主持人会基于歌单**智能选歌、串联话题**，口播由女声（MiniMax 或 edge-tts 降级）合成
- 网页自动连播：口播 → 歌 → 口播 → 歌…
- **音乐不落盘**：歌单只存「歌名、歌手、音源+id」，播放时经在线 API 动态拉取真实直链

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

## 与传统(群晖/NAS)版的差异
原项目设计为**群晖 NAS + 本地 mp3 曲库(list.php)**；本改造将其改为**通用云服务器 + 在线多音源曲库**：
- 曲库不再依赖 NAS 上的 mp3 文件，改为读取 `musiclib/playlist.tsv`（歌名/歌手/音源/id）
- 新增 `musiclib/proxy_server.py`（8001）：把歌单暴露成 app 需要的 `/songs.txt`，并把 `/s/<source>/<id>.mp3` 通过在线 API 取真实可播直链后 302
- 新增 `musiclib/resolve_multi.py`：多渠道(joox/netease)裁决，锁定每首歌的**原唱原版**（简繁归一匹配、排除翻唱/Remix/Live/伴奏、验证可播）
- 用 **Python venv 裸跑**替代 Docker（规避国内拉不到基础镜像）；也可自行套 Docker

在线音乐 API：**多音源搜索/取链**（搜索 `types=search`、播放取链 `types=url`）

## 部署（云服务器 / Linux）
完整可执行手册见 **[DEPLOY-HANDOFF.md](DEPLOY-HANDOFF.md)**（给 codex / 新服务器一键对照）。要点：
1. `python3 -m venv .venv && pip install -r backend/requirements.txt zhconv`
2. 填 `radio.env`：`DEEPSEEK_KEY`、`MINIMAX_KEY`、`NAS_LIST_URL=http://127.0.0.1:8001/songs.txt`、`NAS_BASE_URL=http://<公网IP>:8001`
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

## 曲库维护
编辑 `musiclib/playlist-source.tsv`（歌名<TAB>歌手），删掉旧 `musiclib/playlist.tsv`，运行：
```bash
/opt/easy-radio-host/.venv/bin/python3 musiclib/resolve_multi.py
```
会自动多音源裁决出每首歌的原唱可播版本。

---

## 致谢 / Credits（避免侵权）
本项目是在他人基础上改造的**二次开发学习项目**，对以下原始资源表达感谢与版权归属：

- **原项目 easy-radio-host**：基于开头与整体改造的母本
  - 原仓库：https://gitee.com/weak0001/easy-radio-host
  - 原作的全部署名与版权归原作者 `weak0001` 所有
- **在线音乐 API**（music-api.gdstudio.xyz）：本改造使用其**搜索/取链**接口作为多音源数据源
  - API 地址：https://music-api.gdstudio.xyz/api.php
  - 其版权归平台方，详见其站内声明；**歌词/歌曲版权属于相应权利人**
- **DeepSeek**：主持人大脑（`deepseek-chat`），版权归 DeepSeek
- **MiniMax TTS（海螺）**：口播语音合成，版权归 MiniMax
- 其余第三方依赖见各项目 LICENSE

**免责声明**：本项目不存储、不提供任何音频文件；在线曲库仅作 API 转发。请仅用于学习/测试合法内容，商用或再发布请自行确认对应平台与版权方授权，侵权风险自负。
