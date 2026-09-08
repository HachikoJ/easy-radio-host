# 听间 Tingjian · 腾讯云部署

本手册适用于已有 Nginx 的 Ubuntu 服务器，沿用 Python venv 和 systemd 部署。产品入口为 `https://audio.deline.top`，正式前端位于 `backend/static/`。

## 访问链路与目录

```text
浏览器 → Nginx HTTPS :443
           ├─ /、/api/、/voice/ → 127.0.0.1:8100 主应用
           └─ /music/          → 127.0.0.1:8001 在线曲库代理

主应用 → DeepSeek 编排节目 → MiniMax 合成口播
曲库代理 → 在线音乐 API → 307 跳转到第三方音频地址
```

| 资源 | 位置 |
| --- | --- |
| 代码和虚拟环境 | `/opt/easy-radio-host`、`/opt/easy-radio-host/.venv` |
| 运行用户 | `tingjian` |
| 系统服务 | `tingjian.service`、`tingjian-musiclib.service` |
| 运行配置 | `/etc/tingjian/radio.env`，root 所有、权限 600 |
| 运行数据 | `/var/lib/tingjian` |
| Nginx 站点 | `/etc/nginx/conf.d/audio.deline.top.conf` |
| ACME 验证目录 | `/var/www/letsencrypt` |

歌曲音频不落盘；口播保存在 `/var/lib/tingjian/voice/`。`NAS_*` 为兼容变量名，实际指向在线曲库代理，无需群晖或本地音乐库。

## 1. 前置检查

- 域名 A 记录指向目标服务器；如配置 AAAA，IPv6 也必须能到达同一站点。
- 腾讯云安全组允许 TCP 80、443，SSH 保留管理所需访问范围。8100、8001 仅绑定回环地址，无需公网放行。
- 检查已有站点、监听端口和证书，保留其他业务的配置。
- 服务器能够访问 PyPI、DeepSeek、MiniMax、在线音乐 API 及其音频 CDN。

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
sudo apt-get install -y python3-venv nginx certbot
sudo useradd --system --home-dir /var/lib/tingjian --shell /usr/sbin/nologin tingjian
sudo install -d -o root -g root -m 755 /opt/easy-radio-host
sudo install -d -o root -g root -m 700 /etc/tingjian
sudo install -d -o root -g root -m 755 /var/www/letsencrypt
sudo tar -xzf /tmp/tingjian-release.tar.gz -C /opt/easy-radio-host
sudo python3 -m venv /opt/easy-radio-host/.venv
sudo /opt/easy-radio-host/.venv/bin/pip install -r /opt/easy-radio-host/backend/requirements.txt
```

已有 `tingjian` 用户时跳过创建用户，先核对其用途。代码由管理员维护；systemd 的 `StateDirectory=tingjian` 为主服务创建可写数据目录，运行用户只需读取代码。服务启用 `ProtectSystem=strict`，将写入限制在所需运行目录。

## 3. 配置密钥与地址

首次部署从模板创建环境文件；已有文件直接编辑，避免覆盖现有密钥。

```bash
sudo install -o root -g root -m 600 /opt/easy-radio-host/deploy/radio.env.example /etc/tingjian/radio.env
sudoedit /etc/tingjian/radio.env
```

填写 `DEEPSEEK_KEY`、`MINIMAX_KEY`，并确认：

```dotenv
NAS_LIST_URL=http://127.0.0.1:8001/songs.txt
NAS_BASE_URL=https://audio.deline.top/music
RADIO_BASE=https://audio.deline.top
DATA_DIR=/var/lib/tingjian
HOST_NAME=小蓝
DEEPSEEK_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
MINIMAX_BASE=https://api.minimaxi.com
MINIMAX_MODEL=speech-02-turbo
MINIMAX_VOICE=female-chengshu
```

`MINIMAX_GROUP` 按账号接口要求填写，可为空。密钥仅放服务器运行配置，不放入 Git、前端或命令行参数。systemd 管理器读取 root 所有的环境文件后，以 `tingjian` 用户启动主服务；曲库服务不读取带密钥的配置。

供应商调用可能产生费用。缺少配置或调用失败时可能走模板节目、edge-tts 或纯文字降级，HTTP 200 不能单独证明 DeepSeek 和 MiniMax 调用成功。

## 4. 启动服务

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

模板保留 HTTP ACME 验证路径，其余 HTTP 请求跳转至 HTTPS。`/music/` 的 `proxy_pass` 末尾保留 `/`，将 `/music/s/...` 转发为曲库服务的 `/s/...`。Nginx API 读取超时为 300 秒；前端请求超时为 90 秒，浏览器不会等待满 300 秒。模板还提供每 IP 12 次/分钟、突发 8 次、每 IP 3 个并发及全站 8 个 API 并发的限制；超限返回 429。限流不能替代供应商预算管理。

`deploy/renew-nginx.sh` 会在证书续期成功后检查配置并重新加载 Nginx；已有同用途 hook 时复用。上述 dry-run 命令通过 `--run-deploy-hooks` 同时验证续期流程与 Nginx reload hook。

## 6. 验收

```bash
curl --silent --show-error --dump-header - --output /dev/null http://audio.deline.top/
curl --fail --silent --show-error --output /dev/null --write-out '%{http_code}\n' https://audio.deline.top/
curl --fail --silent https://audio.deline.top/music/_health
sudo ss -ltnp
sudo systemctl status tingjian tingjian-musiclib --no-pager
```

检查 HTTP 跳转 HTTPS、证书域名及有效期、首页 200、曲库非空，以及 8100/8001 只监听 `127.0.0.1`。

真实节目验证会调用供应商服务：

```bash
curl --fail --silent --show-error --max-time 360 \
  https://audio.deline.top/api/show \
  -H 'Content-Type: application/json' \
  -d '{"theme":"午后咖啡","exclude":[]}'
```

检查返回的 `items` 中有歌曲和口播；歌曲地址应以 `https://audio.deline.top/music/` 开头，口播使用本站 `/voice/`。跟随歌曲 307 跳转验证实际音频可访问，检查最终音频地址支持 HTTPS。结合供应商请求结果与服务日志确认真实模型、语音调用，不能用降级结果代替验证。

在桌面和手机浏览器打开正式入口，验证主题生成、口播到歌曲连续播放、暂停与恢复、下一首、点歌、聊天、收藏和历史。检查布局无横向溢出、控制台无混合内容错误。`?demo=1` 只能验证演示交互，不能作为真实 API 验收。

## 7. 更新与恢复

保留上次发布的代码包和提交 SHA。每次更新前备份配置、代码与用户数据，备份只允许管理员访问，不上传仓库：

```bash
backup_dir="/var/backups/tingjian/$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 700 "$backup_dir"
sudo cp -a /etc/tingjian "$backup_dir/config"
sudo cp -a /etc/nginx/conf.d/audio.deline.top.conf "$backup_dir/nginx.conf"
sudo cp -a /etc/systemd/system/tingjian.service /etc/systemd/system/tingjian-musiclib.service "$backup_dir/"
sudo tar -czf "$backup_dir/code.tar.gz" --exclude=.venv -C /opt easy-radio-host
sudo tar -czf "$backup_dir/data.tar.gz" -C /var/lib tingjian
```

使用第 2 节方法生成、上传新的已提交代码包。先比较发布差异；若服务器修改过代码或歌单，合并并保留这些修改后再更新。上传包会覆盖同路径文件，尤其需要保留用户维护的 `musiclib/playlist.tsv`。确认备份和合并后停止本项目两项服务，将新包解压到固定代码目录，再安装依赖并启动：

```bash
sudo systemctl stop tingjian tingjian-musiclib
sudo tar -xzf /tmp/tingjian-release.tar.gz -C /opt/easy-radio-host
sudo /opt/easy-radio-host/.venv/bin/pip install -r /opt/easy-radio-host/backend/requirements.txt
sudo systemctl start tingjian-musiclib tingjian
```

如果更新涉及 `deploy/`，审阅后重新安装对应配置，再执行 `systemctl daemon-reload` 或 `nginx -t` 与 reload。保留真实 `radio.env`，只补齐必要变量。重新执行第 6 节验收。

若新版未通过验收，停止本项目两项服务，将当前代码目录改名保留，然后从 `code.tar.gz` 恢复 `/opt/easy-radio-host`，按旧版 requirements 重建 venv。必要时恢复备份中的 systemd/Nginx 配置，校验后启动服务并复验。改名后的目录保留到恢复确认完成，不直接删除。用户口播等数据独立存放，普通代码回退无需回退数据；涉及数据迁移时先核对兼容性再恢复备份。

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
| 只有文字或模板节目 | 模型/语音调用结果、音色配置、edge-tts 网络 |
| 歌曲不播放 | 公网 `NAS_BASE_URL`、`/music/` 映射、歌曲源与最终音频 HTTPS |
| 曲库为空 | `playlist.tsv` 路径、权限、TSV 格式 |
| 口播 404 | `DATA_DIR`、服务写权限、`/voice/` 转发 |
| HTTP 429 | API 请求频率和并发限制，稍后重试 |
| 证书续期失败 | DNS、80 端口、ACME 目录、timer 和 reload hook |

排障时不要公开包含凭证、用户输入或个人数据的完整日志。AI 编排内容不保证事实准确；公开服务会使用部署者的供应商额度，应按访问规模配置预算和访问范围。

## 版权与致谢

- 原始项目：[weak0001 / easy-radio-host](https://gitee.com/weak0001/easy-radio-host)。原始许可证尚未核实，不因此将整个仓库重新声明为 MIT。
- 交互参考：[hllqkb / Claudio](https://github.com/hllqkb/Claudio)，MIT 许可；参考范围与许可全文见 [第三方说明](THIRD_PARTY_NOTICES.md)。
- 在线音乐 API：[GD 音乐台 API](https://music-api.gdstudio.xyz/api.php)。歌曲版权归来源平台和相应权利人，服务不提供自有音源或歌曲授权。
