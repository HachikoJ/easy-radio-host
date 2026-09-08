# AI 电台主持人 · easy-radio-host

用 **DeepSeek 大模型**当电台主持人 + **MiniMax TTS** 口播 + 你的 **NAS 音乐曲库**，在浏览器里生成并连续播放一期"电台节目"（主持人口播与歌曲交替）。ESP32 播放器接入为 P2 路线。

## 效果
- 点一下"生成一期节目" → **约 4~6 秒**出整期
- 主持人会基于歌单**智能选歌、串联话题**（如"童话主题→Enchanted→Fairytale→山丘→岁月神"），口播由女声（MiniMax）合成
- 网页自动连播：口播 → 歌 → 口播 → 歌…

## 架构

```
浏览器(电台网页)                        群晖 NAS (Docker: ai-radio)
   │ GET / 静态页                        ├─ FastAPI 后端
   │ POST /api/show  ──────────────────► │   1) 拉曲库 list.php (NAS mp3)
   │                                     │   2) DeepSeek 生成节目 JSON(口播+选歌)
   │                                     │   3) 口播并发 → MiniMax TTS → mp3
   │ ◄──── {items: 口播mp3+歌URL 交错} ── │   4) 输出播放清单
   │ 顺序播放 <audio>
```

## 技术栈
- 后端：Python FastAPI 单文件（`backend/app.py`）
- 主持大脑：DeepSeek `deepseek-chat`（json 输出模式）
- 语音：MiniMax TTS v2（`speech-02-turbo`，voice 可配，默认 `female-chengshu`；无 key 自动降级文稿/edge-tts）
- 曲库：复用 NAS Web Station `list.php`（自动目录扫描）
- 前端：单页深蓝风（`backend/static/index.html`），自动连播 + 无语音时文稿停留降级

## 部署 (群晖 Docker)

1. 把本项目放到 NAS（如 `/volume1/docker/radio`）
2. `docker-compose.yml` 填环境变量（**密钥只放 NAS 上，不入 git**）：
   - `DEEPSEEK_KEY`：DeepSeek API key
   - `MINIMAX_KEY`：MiniMax key（T2A）；`MINIMAX_GROUP` 可空（新平台免 GroupId）
   - `NAS_LIST_URL` / `NAS_BASE_URL`：你的曲库列表与站点前缀
   - `HOST_NAME`：主持人名；`MINIMAX_VOICE`：音色
3. 启动：
```bash
sudo /var/packages/ContainerManager/target/usr/bin/docker compose up -d --build
```
4. 浏览器打开 `http://NAS:8100`；群晖防火墙放行 8100

改动代码后（`./backend` 已 bind mount）：
```bash
sudo docker restart ai-radio    # 代码热更新
```

## API
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/show | 生成一期节目 → `{items:[{kind:talk|song,url,text,title}], host}` |
| GET | /api/library | 曲库数量 |
| GET | /voice/xx.mp3 | 口播 mp3 |

## 关键坑
- MiniMax T2A v2 返回的 `data.audio` 是 **hex 字符串**（不是 base64！）
- 新版 MiniMax（api.minimaxi.com）鉴权仅需 Bearer key，GroupId 可空
- FastAPI `.mount("/", StaticFiles)` 要在 `/voice` 路由之后注册

## 网易云口味接入 (P2 已落地核心)
- `netease-api` 容器(xgxdmx/NeteaseMusic-API, 端口3001)扫码登录 → cookie 存 NAS
- 拉 歌单/930红心/听歌排行 → DeepSeek 归纳**口味画像** → 存 `data/profile.json`
- ai-radio 后端 `/api/show`、`/api/intent` 自动注入画像：主持人开场呼应听众口味、按画像选歌
- 重新生成画像: 登录态在 NAS cookie(`/tmp/nmcookies`), 抓取脚本见 tools/ 说明(未入库密钥)
- 注: 非官方接口有版权/风控风险(原作者已停更), 本项目作为个人只读口味数据使用; 画像驱动为主、直链为辅(A+B分层)

## Roadmap (P2+)
- ESP 播放器接入电台：S8 切换"本地曲库 ↔ 电台节目列表"（播放器现有流播能力，加一个"电台列表 URL"入口即可）
- 点歌/向主持人提问聊天、语录历史、定时节目
- 主持人人设与节奏打磨、更多 TTS 音色管理
- 误报：DeepSeek 需在 prompt 中说明输出 JSON；MiniMax 免费额度注意
