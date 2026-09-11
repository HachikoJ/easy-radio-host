# 听间 Tingjian · 腾讯云部署

本手册适用于已有 Nginx 的 Ubuntu 服务器，沿用 Python venv 和 systemd 部署。产品入口为 `https://audio.deline.top`，正式前端位于 `backend/static/`。

## 访问链路与目录

```text
浏览器 → Nginx HTTPS :443
           ├─ /、/api/、/voice/ → 127.0.0.1:8100 主应用
           └─ /music/          → 127.0.0.1:8001 在线曲库代理

主应用 → Command Code（DeepSeek）编排节目 → 本地 TTS :8101（sherpa-onnx MeloTTS）合成口播，失败时降级到 Qwen / MiniMax / edge-tts
曲库代理 → 在线音乐 API → 校验音频、同源流转发（旧 307 跳转兼容）
```

| 资源 | 位置 |
| --- | --- |
| 代码和虚拟环境 | `/opt/easy-radio-host`、`/opt/easy-radio-host/.venv`、本地 TTS 的 `/opt/easy-radio-host/.venv-tts` |
| 运行用户 | `tingjian` |
| 系统服务 | `tingjian.service`、`tingjian-musiclib.service`、`tingjian-tts.service`（可选） |
| 本地 TTS 模型 | `/opt/easy-radio-host/models/vits-melo-tts-zh_en`，163 MB 权重，由 `scripts/install-local-tts.sh` 安装 |
| 运行配置 | `/etc/tingjian/radio.env`，root 所有、权限 600 |
| 运行数据 | `/var/lib/tingjian` |
| GD 额度状态 | `/var/lib/tingjian/gd-quota.sqlite3`，计数与冷却跨重启保留 |
| Nginx 站点 | `/etc/nginx/conf.d/audio.deline.top.conf` |
| ACME 验证目录 | `/var/www/letsencrypt` |

歌曲音频和歌词不落盘；节目口播、故障播报与版本化限流陪伴音频保存在 `/var/lib/tingjian/voice/`。`NAS_*` 为兼容变量名，实际指向在线曲库代理，无需群晖或本地音乐库。

## 1. 前置检查

- 域名 A 记录指向目标服务器；如配置 AAAA，IPv6 也必须能到达同一站点。
- 腾讯云安全组允许 TCP 80、443，SSH 保留管理所需访问范围。8100、8001 仅绑定回环地址，无需公网放行。
- 检查已有站点、监听端口和证书，保留其他业务的配置。
- 服务器能够访问 PyPI、Command Code、阿里云百炼、可选 MiniMax、在线音乐 API 及其音频 CDN。

```bash
sudo nginx -t
sudo ss -ltnp
python3 --version
```

建议使用 Ubuntu 22.04 或 24.04 的 Python 3.10+。首次安装与已有部署的更新分开执行。

## 2. 上传代码与安装依赖

在本地已检出的仓库中执行，将当前已提交版本打包上传。用已配置的 SSH 目标替换 `<SSH_TARGET>`，服务器无需 GitHub 凭证。

```bash
git status --short
git rev-parse HEAD
git archive --format=tar.gz --output=/tmp/tingjian-release.tar.gz HEAD
scp /tmp/tingjian-release.tar.gz <SSH_TARGET>:/tmp/tingjian-release.tar.gz
```

包中不包含未提交文件。将输出的提交 SHA 作为该次发布记录。以下命令在服务器执行，代码目录应尚未安装本项目：

```bash
sudo apt-get update
sudo apt-get install -y python3-venv nginx certbot ffmpeg
sudo useradd --system --home-dir /var/lib/tingjian --shell /usr/sbin/nologin tingjian
sudo install -d -o root -g root -m 755 /opt/easy-radio-host
sudo install -d -o root -g root -m 700 /etc/tingjian
sudo install -d -o root -g root -m 755 /var/www/letsencrypt
sudo tar -xzf /tmp/tingjian-release.tar.gz -C /opt/easy-radio-host
sudo python3 -m venv /opt/easy-radio-host/.venv
sudo /opt/easy-radio-host/.venv/bin/pip install -r /opt/easy-radio-host/backend/requirements.txt
```

已有 `tingjian` 用户时跳过创建用户，先核对其用途。代码由管理员维护；两项 systemd 服务使用 `StateDirectory=tingjian` 创建可写数据目录，曲库服务将 `GD_QUOTA_DB` 指向 `/var/lib/tingjian/gd-quota.sqlite3`，运行用户只需读取代码。服务启用 `ProtectSystem=strict`，将写入限制在所需运行目录。所有共享 GD 额度的代理进程须指向同一个数据库文件。

## 3. 配置密钥与地址

首次部署从模板创建环境文件；已有文件直接编辑，避免覆盖现有密钥。

```bash
sudo install -o root -g root -m 600 /opt/easy-radio-host/deploy/radio.env.example /etc/tingjian/radio.env
sudoedit /etc/tingjian/radio.env
```

填写 `DEEPSEEK_KEY`、`DASHSCOPE_API_KEY`，并确认：

```dotenv
NAS_LIST_URL=http://127.0.0.1:8001/songs.txt
NAS_BASE_URL=https://audio.deline.top/music
RADIO_BASE=https://audio.deline.top
DATA_DIR=/var/lib/tingjian
HOST_NAME=小蓝
DEEPSEEK_BASE=https://api.commandcode.ai/provider/v1
DEEPSEEK_MODEL=deepseek/deepseek-v4.1-flash
DASHSCOPE_BASE=https://dashscope.aliyuncs.com/api/v1
QWEN_TTS_MODEL=qwen3-tts-instruct-flash
QWEN_TTS_VOICE=Cherry
QWEN_TTS_INSTRUCTIONS=温暖亲切、自然松弛，中速，吐字清晰，像真实电台主持人
LOCAL_TTS_URL=http://127.0.0.1:8101
LOCAL_TTS_CACHE_ID=sherpa-melo-zh-en-v1
LOCAL_TTS_TIMEOUT=60
LOCAL_TTS_SPEED=1.0
EDGE_TTS_VOICE=zh-CN-XiaoxiaoNeural
MINIMAX_BASE=https://api.minimaxi.com
MINIMAX_MODEL=speech-02-turbo
MINIMAX_VOICE="Chinese (Mandarin)_Warm_Girl"
```

`DEEPSEEK_BASE` 使用 Command Code 的 OpenAI 兼容接口，`deepseek/deepseek-v4.1-flash` 是 `DeepSeek-V4.1-Flash` 在该网关中的模型 ID。已有环境文件中的显式配置优先于代码默认值；更新时同步替换 `DEEPSEEK_KEY`、`DEEPSEEK_BASE` 和 `DEEPSEEK_MODEL`，再重启主服务。

百炼专属业务空间使用控制台给出的 DashScope 地址，即 `https://<业务空间主机>/api/v1`；没有专属地址时使用上面的公共地址。`DASHSCOPE_API_KEY` 与可选 `MINIMAX_KEY` 只放服务器运行配置，不放入 Git、前端或命令行参数。systemd 管理器读取 root 所有的环境文件后，以 `tingjian` 用户启动主服务；曲库服务不读取带密钥的配置。

口播按 `本地 MeloTTS -> Qwen -> MiniMax -> edge-tts` 调用。`LOCAL_TTS_URL` 留空时跳过本地服务；云端只配置 Qwen，或只配置 MiniMax，都能工作；两者都未配置时直接使用 edge-tts。`QWEN_TTS_VOICE` 默认 `Cherry`，`MINIMAX_VOICE` 默认 `Chinese (Mandarin)_Warm_Girl`。已有环境文件中的显式值优先于代码默认值，更新代码不会自动覆盖；修改任一声音相关参数并重启后，节目口播、故障播报和固定串场都会使用新的版本文件。

新生成的口播，包括本地 MeloTTS 输出，都通过 `backend/speech_audio.py` 做两遍 ffmpeg `loudnorm`：目标 -14 LUFS、真峰值上限 -1.5 dBTP、LRA 7，启用 `dual_mono`，每遍最长 20 秒。输出为 32 kHz、单声道、128 kbps MP3；缺少 ffmpeg、分析值无效、超时或编码失败时保留原音。处理不改写旧口播，也不下载或归一化第三方歌曲。前端歌曲播放音量为主音量乘以 0.85，口播使用主音量，滑杆数值仍表示主音量。

供应商调用可能产生费用，本地 TTS 正常工作时口播不产生供应商费用，节目编排仍调用 DeepSeek。缺少配置或调用失败时可能走模板节目、云端 TTS 或纯文字降级，HTTP 200 不能单独证明任一渠道调用成功。

主服务启动后在后台检查故障播报和 8 条限流陪伴音频，只生成当前版本中缺失的文件；陪伴音频在配置本地 TTS、Qwen 或 MiniMax 后生成，每项沿用最多 3 次启动期重试。版本形如 `v1-{12位摘要}`，由本地 TTS 地址与模型标识、Qwen/MiniMax 模型、音色、指令、音频参数、edge-tts 音色和文案共同确定，修改任一项会生成新版本，不会在用户已经进入限流等待后临时调用供应商。`/api/playback/cooldown/content.json` 只列出已经成功生成的文件；单项失败不会虚报，清单为空时前端使用固定等待播报及浏览器语音降级，恢复计时仍继续。首次启动或版本变化后须等待清单完整再完成发布验收。

## 4. 启动服务

### 本地 TTS 服务（可选）

本地口播需要独立虚拟环境和约 163 MB 的模型权重，不需要 GPU；加载后 systemd cgroup 常驻约 490 MiB、峰值约 500 MiB，2 vCPU 上实测合成速度约为实时的两倍。只使用云端降级链时跳过本节，并在 `radio.env` 中留空 `LOCAL_TTS_URL`。

```bash
sudo bash /opt/easy-radio-host/scripts/install-local-tts.sh
sudo python3 -m venv /opt/easy-radio-host/.venv-tts
sudo /opt/easy-radio-host/.venv-tts/bin/pip install -r /opt/easy-radio-host/tts/requirements.txt
sudo install -m 644 /opt/easy-radio-host/deploy/tingjian-tts.service /etc/systemd/system/tingjian-tts.service
sudo systemctl daemon-reload
sudo systemctl enable --now tingjian-tts
sudo systemctl is-active tingjian-tts
curl --fail --silent http://127.0.0.1:8101/health
```

首次启动要等模型加载完成才会返回健康状态；模型缺失时进程退出并在 `journalctl -u tingjian-tts` 中留下 `missing local TTS model files`。安装脚本用 SHA256 校验四个模型文件，重复执行只补齐缺失或损坏的部分；`hf-mirror.com` 不可用时可通过 `HF_MIRROR_BASE` 指向其他镜像。`tingjian.service` 通过 `Wants=tingjian-tts.service` 关注本地服务，并在 `LOCAL_TTS_URL` 非空时最多等待 20 秒让 8101 通过健康检查，避免冷启动时把云端音频误存为本地版本；等待超时后主应用仍继续启动并降级到云端 TTS。

### 主应用

```bash
sudo install -m 644 /opt/easy-radio-host/deploy/tingjian.service /etc/systemd/system/tingjian.service
sudo install -m 644 /opt/easy-radio-host/deploy/tingjian-musiclib.service /etc/systemd/system/tingjian-musiclib.service
sudo systemctl daemon-reload
sudo systemctl enable --now tingjian-musiclib tingjian
sudo systemctl is-active tingjian-musiclib tingjian
curl --fail --silent http://127.0.0.1:8001/_health
curl --fail --silent --output /dev/null http://127.0.0.1:8100/
```

曲库健康接口的 `songs` 应大于零。服务读取 `/opt/easy-radio-host/musiclib/playlist.tsv`；迁移代码目录时须同时检查曲库路径。

## 5. 域名与 HTTPS

首次安装 HTTP 模板供证书验证使用。若已存在同域名配置，先核对并备份该文件，避免重复 `server_name`；其他站点保持原配置。

```bash
sudo install -m 644 /opt/easy-radio-host/deploy/nginx-audio-http.conf /etc/nginx/conf.d/audio.deline.top.conf
sudo nginx -t
sudo systemctl reload nginx
sudo certbot certonly --webroot --webroot-path /var/www/letsencrypt --domain audio.deline.top
```

Certbot 首次运行会要求通知邮箱和证书服务条款确认。签发后启用 HTTPS 模板，证书路径为 `/etc/letsencrypt/live/audio.deline.top/fullchain.pem` 与 `privkey.pem`。

```bash
sudo cp -a /etc/nginx/conf.d/audio.deline.top.conf /etc/tingjian/nginx-http.backup
sudo install -m 644 /opt/easy-radio-host/deploy/nginx-audio.conf /etc/nginx/conf.d/audio.deline.top.conf
sudo nginx -t
sudo systemctl reload nginx
sudo install -m 755 /opt/easy-radio-host/deploy/renew-nginx.sh /etc/letsencrypt/renewal-hooks/deploy/tingjian-nginx
sudo systemctl enable --now certbot.timer
sudo certbot renew --dry-run --run-deploy-hooks
```

模板保留 HTTP ACME 验证路径，其余 HTTP 请求跳转至 HTTPS。`/music/` 的 `proxy_pass` 末尾保留 `/`，将 `/music/s/...` 转发为曲库服务的 `/s/...`。Nginx API 读取超时为 300 秒；前端节目/点歌请求超时为 240 秒，音源恢复为 60 秒。模板还提供每 IP 12 次/分钟、突发 8 次、每 IP 3 个并发及全站 8 个 API 并发的限制；超限返回 429。GD 搜索、取链与歌词共享滚动 300 秒最多 45 次的预算，SQLite 事务协调共用数据库的进程。计数与上游冷却在重启后保留，完整遵守上游 `Retry-After`，不因等待超过 300 秒而缩短。独立程序若不使用同一额度数据库，其请求不在该预算内。

Nginx 为 `/api/playback/announcement/`、`/api/playback/cooldown/` 和精确匹配的 `/api/playback/availability` 设置独立 `location`，缓存播报、限流陪伴音频与额度查询不占用 AI 节目生成的每分钟 12 次及并发预算，也不调用 GD API。

`deploy/renew-nginx.sh` 会在证书续期成功后检查配置并重新加载 Nginx；已有同用途 hook 时复用。上述 dry-run 命令通过 `--run-deploy-hooks` 同时验证续期流程与 Nginx reload hook。

## 6. 验收

```bash
curl --silent --show-error --dump-header - --output /dev/null http://audio.deline.top/
curl --fail --silent --show-error --output /dev/null --write-out '%{http_code}\n' https://audio.deline.top/
curl --fail --silent https://audio.deline.top/music/_health
curl --fail --silent https://audio.deline.top/api/playback/availability
curl --fail --silent https://audio.deline.top/api/playback/cooldown/content.json | python3 -c \
  'import json,sys; d=json.load(sys.stdin); assert len(d["items"]) == 8; print(d["version"], len(d["items"]))'
curl --fail --silent http://127.0.0.1:8101/health
sudo ss -ltnp
sudo systemctl status tingjian tingjian-musiclib tingjian-tts --no-pager
```

检查 HTTP 跳转 HTTPS、证书域名及有效期、首页 200、曲库非空、限流陪伴清单正好包含 8 项，以及 8100/8001/8101 只监听 `127.0.0.1`。`/health` 返回 `sample_rate` 44100、`num_threads` 2 时表示本地模型已就绪。逐项读取清单中的 `url`，确认返回可播放 MP3；文件未生成时清单不会虚报该项，可结合主服务日志定位本地 TTS、Qwen、MiniMax 或 edge-tts 失败原因，修复后重启主服务补齐缺失文件。

本地 TTS 启用后，用一次真实节目验证口播确实由本机生成：`sudo journalctl -u tingjian-tts -n 30 --no-pager` 应出现该次合成请求，主服务日志 `sudo journalctl -u tingjian -n 100 --no-pager` 不应出现 `Local TTS 失败`。若出现失败，先按第 8 节定位；本地服务不可用时主应用会自动降级到云端链，但发布验收要求本地链路本身通过。实测 cgroup 常驻约 489 MiB、峰值约 501 MiB，可结合 `systemctl show tingjian-tts -p MemoryPeak` 与 `free -m` 一起核对，1.9 GiB 机型上不应出现 OOM。

真实节目验证会调用供应商服务：

```bash
curl --fail --silent --show-error --max-time 360 \
  https://audio.deline.top/api/show \
  -H 'Content-Type: application/json' \
  -d '{"theme":"午后咖啡","exclude":[]}'
```

检查返回的 `items` 中有歌曲和口播；歌曲地址应以 `https://audio.deline.top/music/` 开头并带 `stream=1`，口播使用本站 `/voice/`。对歌曲发送小范围 GET，验证 206、音频文件头及 Content-Range，并在浏览器确认实际播放时间前进与拖动。原不带 `stream` 的歌曲地址保留 307 兼容。结合本地 TTS 服务日志、供应商请求结果与服务日志确认真实模型、语音调用，不能用降级结果代替验证；中英混读文本（例如「今天放一首 City Pop」）需实听确认英文按中文音系发音、无明显断句错误。音源状态与完整恢复规则见 [音源检索与恢复](docs/MUSIC-SOURCES.md)。

在桌面和手机浏览器打开正式入口，验证主题生成、口播到歌曲连续播放、暂停与恢复、下一首、点歌、聊天、收藏和历史。使用受控模拟验证无音源、限流与临时故障的文字说明、原因播报、自动下一曲及等待恢复；不能为验收主动向上游发送 45 次请求触发限额。限流模拟应覆盖时段内容优先、通用内容轮播、距恢复不足 6 秒不启新段、`ready` 后立即卸载陪伴音频并生成节目，以及再次返回 `limited/retry_after` 时继续等待。等待期间不得出现天气、定位、GD、DeepSeek 或云端 TTS 请求。

歌词用受控响应分别验证：首选渠道有词直接显示；首选渠道 200 空歌词后严格跨渠道命中；429 显示等待秒数并仅按 `retry_after` 自动重试；临时故障与确实无歌词不混淆。核对切歌、暂停或关闭页面后歌词重试不再发生，旧响应不覆盖新歌。暂停或关闭页面也应停止陪伴音频、后续检索和恢复计时，恢复播放保持原位置。缓存播报与陪伴接口应返回可播放语音，故障或等待时不应临时重新合成。检查布局无横向溢出、控制台无混合内容错误。`?demo=1` 只能验证演示交互，不能作为真实 API 验收。

确认服务器 `ffmpeg -version` 可运行。生成新口播后，可用下面的只读命令检查实际文件的响度；将 `<VOICE_FILE>` 换成本次生成的本地口播文件路径：

```bash
ffmpeg -hide_banner -nostdin -i '<VOICE_FILE>' \
  -af 'loudnorm=I=-14:TP=-1.5:LRA=7:dual_mono=true:print_format=json' \
  -f null -
```

核对输出 `input_i`、`input_tp` 与目标是否接近，再以同一主音量实听口播到歌曲的切换。MP3 编码与歌曲来源可能造成差异，HTTP 200 或文件存在不能单独证明响度处理成功。前端验证同时覆盖首屏随视口高度适配、歌词独立滚动、右上角链接在新标签页打开，以及致谢默认中文、手动切换英文。

## 7. 更新与恢复

前端 HTML、CSS 与 JavaScript 返回 `Cache-Control: no-cache`，浏览器再次访问时通过 ETag 校验是否有更新，未变化时仍可返回 304。页面入口及应用模块带版本参数，避免旧浏览器缓存混用新旧界面；更换已发布的资源版本时，入口与应用模块引用应保持一致。部署不会强制刷新正在收听的标签页，更新后重新打开或刷新页面才加载新代码；若此前缓存了旧入口，可在地址后加 `?v=20260909-3` 打开一次。

保留上次发布的代码包和提交 SHA。每次更新前备份配置、代码与用户数据，备份只允许管理员访问，不上传仓库：

```bash
backup_dir="/var/backups/tingjian/$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 700 "$backup_dir"
sudo cp -a /etc/tingjian "$backup_dir/config"
sudo cp -a /etc/nginx/conf.d/audio.deline.top.conf "$backup_dir/nginx.conf"
sudo cp -a /etc/systemd/system/tingjian.service /etc/systemd/system/tingjian-musiclib.service \
  /etc/systemd/system/tingjian-tts.service "$backup_dir/"
sudo tar -czf "$backup_dir/code.tar.gz" --exclude=.venv --exclude=.venv-tts -C /opt easy-radio-host
sudo tar -czf "$backup_dir/data.tar.gz" -C /var/lib tingjian
```

使用第 2 节方法生成、上传新的已提交代码包。先比较发布差异；若服务器修改过代码或歌单，合并并保留这些修改后再更新。上传包会覆盖同路径文件，尤其需要保留用户维护的 `musiclib/playlist.tsv`。确认备份和合并后停止本项目两项服务，将新包解压到固定代码目录，再安装依赖：

```bash
sudo systemctl stop tingjian tingjian-musiclib
sudo tar -xzf /tmp/tingjian-release.tar.gz -C /opt/easy-radio-host
sudo /opt/easy-radio-host/.venv/bin/pip install -r /opt/easy-radio-host/backend/requirements.txt
sudo /opt/easy-radio-host/.venv-tts/bin/pip install -r /opt/easy-radio-host/tts/requirements.txt
sudo systemctl restart tingjian-tts
```

未启用本地 TTS 的部署跳过 `.venv-tts` 与 `tingjian-tts` 两行；启用后主服务会在重启期间继续使用云端降级链，不会因为本地服务正在重启而中断口播。

如果更新涉及 `deploy/`，审阅后重新安装对应配置，再执行 `systemctl daemon-reload` 或 `nginx -t` 与 reload。保留真实 `radio.env`，只补齐必要变量。

从仅有内存计数的版本首次升级至 SQLite 额度管理时，须在停止旧曲库服务后、首次启动新服务前创建共享额度状态，并写入至少 300 秒的迁移冷却。若已知上游 `Retry-After` 尚未结束，则以更晚时间为准。该步骤补偿旧进程无法导出的最近请求，之后重启直接沿用数据库，不重复清零或重新迁移。可在确认数据库尚不存在时执行：

```bash
sudo install -d -o tingjian -g tingjian -m 755 /var/lib/tingjian
sudo -u tingjian /opt/easy-radio-host/.venv/bin/python -c \
  'from musiclib.quota import RollingQuota; q = RollingQuota("/var/lib/tingjian/gd-quota.sqlite3"); q.inspect(cooldown=300)'
```

此命令在 `/opt/easy-radio-host` 执行，且只适用于首次迁移；已有数据库必须保留其当前计数和更长冷却。数据库写权限故障应修复权限，不可通过删除文件绕过限额。完成适用的迁移步骤后启动服务，再执行第 6 节验收；首次迁移时，额度接口应仍处于预期等待期：

```bash
sudo systemctl start tingjian-musiclib tingjian
curl --fail --silent http://127.0.0.1:8100/api/playback/availability
```

本次接口兼容性变化：`/api/show` 的歌曲不可用错误将 `detail` 从字符串改为结构对象，客户端应读取其中的原因与恢复信息；`/api/intent` 的所有音源失败均包含 `next` 动作，须先提示并播报，再切换。新增 `/api/playback/availability`、`/api/playback/announcement/{reason}.mp3`、`/api/playback/cooldown/content.json` 和版本化陪伴音频路径，前后端应一同更新，避免旧客户端忽略恢复信息。歌词旧路径保持可用；新客户端传 `title/artist` 才能启用严格跨渠道补找，并处理 HTTP 429 的 `Retry-After` 头与结构化 `detail`。

从未安装 ffmpeg 的版本更新时，安装系统包 `ffmpeg` 后可启用新口播响度处理；暂未安装仍会保留原音播放。需要采用新的默认音色时，应同时审阅现有 `QWEN_TTS_VOICE` 和 `MINIMAX_VOICE`，不能只依赖更新代码。音色配置恢复使用更新前的环境文件备份；代码回退不会自动改变已显式配置的音色。

本地 TTS 的回退不需要改代码：把 `LOCAL_TTS_URL` 留空并重启主服务即回到 `Qwen -> MiniMax -> edge-tts`，再执行 `sudo systemctl disable --now tingjian-tts` 释放约 490 MiB 内存。模型文件与 `.venv-tts` 可留在磁盘上，重新启用只需恢复 `LOCAL_TTS_URL` 并启动服务。切换渠道后固定播报的版本摘要会变化，主服务会重新生成故障播报和 8 条限流陪伴音频，旧文件保留但不再被引用。

若新版未通过验收，停止 `tingjian`、`tingjian-musiclib` 与 `tingjian-tts`，将当前代码目录改名保留，然后从 `code.tar.gz` 恢复 `/opt/easy-radio-host`，按旧版 requirements 重建 venv。必要时恢复备份中的 systemd/Nginx 配置，校验后启动服务并复验。改名后的目录保留到恢复确认完成，不直接删除。用户口播等数据独立存放，普通代码回退无需回退数据；涉及数据迁移时先核对兼容性再恢复备份。版本化限流陪伴文件可保留，旧代码不会引用它们；歌词只在内存缓存，无数据回退步骤。

额度数据库例外：始终保留最新 `gd-quota.sqlite3` 及当前冷却，不用旧数据备份覆盖它。优先保留兼容的持久额度模块，仅回退播放行为。若必须运行不读取 SQLite 的旧代理，先确认已记录冷却结束，且最后一次 GD 请求已过去 300 秒，再启动；旧代码的预算也必须保持每 300 秒最多 45 次，不能恢复为 50 次。回退不是重新获得请求额度的方式。

## 8. 歌单维护与排障

维护 `musiclib/playlist-source.tsv` 后，可用 `musiclib/resolve_multi.py` 重新解析来源 ID。该脚本另需 `zhconv`，并会写入 `playlist.tsv`；运行前保留原歌单备份。在线来源及可播性可能变化，应重新核对曲目和版本。

```bash
sudo journalctl -u tingjian -n 100 --no-pager
sudo journalctl -u tingjian-musiclib -n 100 --no-pager
sudo nginx -t
sudo certbot certificates
```

| 现象 | 检查项 |
| --- | --- |
| 首页可开，生成超时 | 主服务日志、供应商连通性、额度、Nginx 超时 |
| 只有文字或模板节目 | DeepSeek/Qwen/MiniMax 调用结果、`QWEN_TTS_VOICE` 与备用音色配置、edge-tts 网络 |
| 口播回退到云端渠道 | `curl --fail http://127.0.0.1:8101/health`、`journalctl -u tingjian-tts -n 50`、主服务日志中的 `Local TTS 失败`；模型缺失时重跑安装脚本，改配置后重启 `tingjian-tts` |
| 口播合成变慢或内存告警 | 本地服务是否在用 FP32 `model.onnx`、`systemctl show tingjian-tts -p MemoryPeak`、`free -m`；检查是否改过 `LOCAL_TTS_THREADS`、`LOCAL_TTS_MAX_TEXT_CHARS`，必要时先置空 `LOCAL_TTS_URL` 回到云端链 |
| 歌曲不播放 | 公网 `NAS_BASE_URL`、`/music/` 映射、歌曲源与最终音频 HTTPS |
| 曲库为空 | `playlist.tsv` 路径、权限、TSV 格式 |
| 口播 404 | `DATA_DIR`、服务写权限、`/voice/` 转发 |
| 新口播仍明显偏轻或偏响 | ffmpeg 可用性、`TTS loudness normalization` 日志、实际新文件的响度；旧口播不会重新处理 |
| HTTP 429 | 区分 Nginx 限制、GD 本地预算和上游限制；查询恢复时间并等待，不清空额度数据库或循环切换渠道 |
| 故障提示后没有声音 | 检查缓存播报接口与浏览器音频权限；核对浏览器语音降级及当前主音量 |
| 限流后只有等待提示 | 检查 `/api/playback/cooldown/content.json` 是否为 8 项、对应 MP3 是否可读、Qwen/MiniMax 配置与主服务启动日志；不要在等待流程中临时生成 |
| 歌词长期显示未返回 | 区分 429、502 与 200 空歌词；检查前端是否携带 `title/artist`、是否按 `Retry-After` 重试，以及跨渠道结果的录音身份 |
| 暂停后仍有请求 | 检查前端版本、请求取消及服务端断开检测；已发送的请求仍计入额度 |
| 证书续期失败 | DNS、80 端口、ACME 目录、timer 和 reload hook |

排障时不要公开包含凭证、用户输入或个人数据的完整日志。AI 编排内容不保证事实准确；公开服务会使用部署者的供应商额度，应按访问规模配置预算和访问范围。

当前 Nginx 限制按访客 IP 生效，不能约束大量不同来源的总请求量。常规口播由本地 TTS 承担，`Qwen` 与 `MiniMax` 只在本地服务不可用时才会被调用，但公开服务仍应在上线前增加跨请求的字符预算、并发/RPM 闸门和短文本限制，并监控实际用量；仅保留 `DASHSCOPE_API_KEY` 而不设总额度，会在本地服务持续故障时直接消耗部署者账户余额。本地 TTS 只降低口播成本，不改变 DeepSeek 编排、在线曲库和歌词的用量边界。

## 版权与致谢

- 原始项目：[weak0001 / easy-radio-host](https://gitee.com/weak0001/easy-radio-host)。原始许可证尚未核实，不因此将整个仓库重新声明为 MIT。
- 交互参考：[hllqkb / Claudio](https://github.com/hllqkb/Claudio)，MIT 许可；参考范围与许可全文见 [第三方说明](THIRD_PARTY_NOTICES.md)。
- 在线音乐 API：[GD 音乐台 API](https://music-api.gdstudio.xyz/api.php)。歌曲版权归来源平台和相应权利人，服务不提供自有音源或歌曲授权。
