# easy-radio-host 服务器部署手册

> 目标：在一台**全新的阿里云 Linux（64位，公网有 IP）**服务器上，部署这个「AI 电台」，供浏览器访问生成口播+在线音乐的电台节目。
> 公网 IP 示例用 `<SERVER_IP>` 占位，部署时替换成你自己的。

---

## 0. 总览 / 架构

```
用户浏览器
   │  GET /                (8100: 主应用 index.html)
   │  POST /api/show 等     生成一期节目
   ▼
easy-radio-host  FastAPI  ──(8100)── backend/app.py
   │  DeepSeek 生成「口播+选歌」JSON
   │  MiniMax TTS 把口播合成 mp3 (无 key 降级 edge-tts)
   │  歌曲 rel 形如 s/joox/<id>.mp3
   ▼
musiclib Proxy  FastAPI ──(8001)── musiclib/proxy_server.py
   │   serve /songs.txt  (给 app 当曲库列表，含 歌名\trel)
   │   serve /s/<source>/<id>.mp3 → 向第三方音乐API取直链 → 302 跳转
   ▼
music-api.gdstudio.xyz  (多音源 search/url)
```
- 主应用通过曲库代理读取 `/songs.txt`，并使用代理提供的歌曲地址播放。
- 音乐**不落盘**，全部来自在线 API；歌单只存「歌名、歌手、source、source_id」。

---

## 1. 运行方式：Python venv

推荐使用 **Python venv 裸跑**：
- 依赖仅 3 行 requirements：`fastapi / uvicorn[standard] / edge-tts`(+ 解析脚本用 `zhconv`)。
- PyPI 用清华源很快。


---

## 2. 克隆代码并放好

```bash
# 将仓库部署到 /opt/easy-radio-host
git clone <你的仓库URL> /opt/easy-radio-host
cd /opt/easy-radio-host
```

需要具备的文件（GitHub 仓库里应有）：
```
backend/app.py            # 主应用
backend/requirements.txt
backend/static/index.html
musiclib/proxy_server.py  # 8001 在线曲库代理(多音源取播)
musiclib/resolve_multi.py # 解析歌单→多渠道裁决锁定(joox/netease)
musiclib/resolve_ids.py   # 单源解析工具
musiclib/scan.sh          # 本地文件导入工具（在线曲库无需使用）
musiclib/playlist-source.tsv  # 源歌单样例(歌名<TAB>歌手)
musiclib/playlist.tsv     # 已裁决锁定的歌单(73首样例)
```

> ⚠️ **不要把 `radio.env`、`*.bak`、`data/`(运行时 mp3) 推进仓库。** `radio.env` 含真实 API key，必须用 `.gitignore` 排除。仓库只放代码与歌单样例。

---

## 3. 配置说明

- `backend/app.py` 的 `fetch_library()` 支持在线格式 `标题<TAB>rel`。
- 关键 env（app 读的）：
  - `NAS_LIST_URL` = `http://127.0.0.1:8001/songs.txt`（兼容变量名，指向在线曲库列表）
  - `NAS_BASE_URL` = `http://<SERVER_IP>:8001`（兼容变量名，指向在线歌曲代理）
  - `RADIO_BASE` = `http://<SERVER_IP>:8100`（串场/口播完整 URL 用）
  - `DEEPSEEK_KEY`、`DEEPSEEK_MODEL=deepseek-chat`
  - `MINIMAX_KEY`、`MINIMAX_VOICE`（如 `Chinese_huolishaonv` / `female-chengshu`）
  - `DATA_DIR=/opt/easy-radio-host/data`

---

## 4. 准备 venv 并安装依赖

```bash
# Python3.10+ 即可
python3 -m venv /opt/easy-radio-host/.venv   # 或 /home/<特立>/venvs/radio-venv
source /opt/easy-radio-host/.venv/bin/activate
pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install -r backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install zhconv -i https://pypi.tuna.tsinghua.edu.cn/simple   # 解析脚本简繁归一用
```
> requirements 已有 fastapi/uvicorn/edge-tts；`zhconv` 供 `resolve_multi.py` 用（不在原 requirements 里，需单装）。

创建数据目录与 env（**先看第 7 步的 .env.example**）：
```bash
mkdir -p /opt/easy-radio-host/data/voice   # TTS 产物目录
chown -R <运行用户> /opt/easy-radio-host
```

---

## 5. 系统服务化

创建版源（两进程，均 `Restart=always`）：

**A. 主应用 8100** — `/etc/systemd/system/easy-radio-host.service`
```ini
[Unit]
Description=AI Radio Host (easy-radio-host) FastAPI on 8100
After=network.target

[Service]
Type=simple
User=admin            # 改你的运行用户
WorkingDirectory=/opt/easy-radio-host/backend
EnvironmentFile=/opt/easy-radio-host/radio.env
ExecStart=/opt/easy-radio-host/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8100
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

**B. 在线曲库代理 8001** — `/etc/systemd/system/easy-radio-musiclib.service`
```ini
[Unit]
Description=Online Music Library Proxy (8001)
After=network.target easy-radio-host.service

[Service]
Type=simple
User=admin
WorkingDirectory=/opt/easy-radio-host/musiclib
EnvironmentFile=/opt/easy-radio-host/radio.env
ExecStart=/opt/easy-radio-host/.venv/bin/uvicorn proxy_server:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
```bash
systemctl daemon-reload
systemctl enable --now easy-radio-host easy-radio-musiclib
```

---

## 6. 防火墙 / 安全组放行

**云厂商安全组放行 8100、8001（TCP，来源 0.0.0.0/0 或你的访问网段）。**
- 8100：主页面 + `/api/*` + `/voice/*.mp3`（口播）
- 8001：歌曲播放——浏览器通过公网 IP:8001 拿歌，8001 再 302 到第三方 CDN。**必须公网可达**，否则浏览器端 402306。

系统防火墙如启用也要放行：
```bash
firewall-cmd --permanent --add-port=8100/tcp --add-port=8001/tcp && firewall-cmd --reload  # 或 ufw/iptables 同理
```

---

## 7. radio.env（含 key，需你自填）—— 建议提供 `radio.env.example`

真实机里 `/opt/easy-radio-host/radio.env`（chmod 600）：
```env
NAS_LIST_URL=http://127.0.0.1:8001/songs.txt
NAS_BASE_URL=http://<SERVER_IP>:8001
RADIO_BASE=http://<SERVER_IP>:8100
DATA_DIR=/opt/easy-radio-host/data
PORT=8100
HOST_NAME=小蓝

DEEPSEEK_KEY=<你的DeepSeek API key>
DEEPSEEK_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

MINIMAX_KEY=<你的MiniMax T2A key>
MINIMAX_VOICE=Chinese_huolishaonv   # 也可 female-chengshu / female-shaonv
```
> 记得 `chmod 600 radio.env`。别提交。

---

## 8. 初始化/扩展歌单（可选，仓库已带73首样例）

样例歌单 `musiclib/playlist-source.tsv` 已是「歌名<TAB>歌手」。想重新按多源裁决锁定：
```bash
cd /opt/easy-radio-host/musiclib
# 1) 编辑 playlist-source.tsv 增删
# 2) 删除旧结果，重跑多源裁决（joox 优先, netease 兜底, 会自动排除翻唱/验可播）
rm -f playlist.tsv
/opt/easy-radio-host/.venv/bin/python3 resolve_multi.py
```
`resolve_multi.py` 逻辑：对每歌并行搜 joox/netease → 歌名精确 + 歌手简繁归一匹配 + 排除 翻唱/Remix/Live/伴奏/深情/治愈 等 → 验证候选能取到可播直链 → joox 命中优先；joox 无则 netease。
`proxy_server.py` 读 `playlist.tsv`（格式 `歌名\t歌手\tsource\tsource_id\t备注`），动态生成 `/songs.txt` 并 302 播放。

---

## 9. 验证

```bash
# 服务
systemctl status easy-radio-host easy-radio-musiclib   # active
# 端口
ss -tln | grep -E ':8100|:8001'
# 前端
curl -s -o /dev/null -w "%{http_code}\n" http://<SERVER_IP>:8100/            # 200
# 曲库列表(应有歌)
curl -s http://<SERVER_IP>:8001/songs.txt | head
# 生成一期节目(需已填 DEEPSEEK_KEY；口播会实时合成)
curl -s -X POST http://127.0.0.1:8100/api/show -H 'Content-Type: application/json' -d '{"theme":"怀旧金曲"}'
# 抽一首歌确认能拉通到音频(浏览器会跟随302)
curl -sL -o /dev/null -w "%{http_code} %{content_type} %{size_download}\n" \
     "http://<SERVER_IP>:8001/s/joox/<某id>.mp3"   # 期望 200 audio/mpeg 有 size
```

---

## 10. 关键排坑清单

| 现象 | 原因与处理 |
|---|---|
| 说话后不出歌 | 歌曲 URL 若含 `127.0.0.1` → 在用户浏览器=用户自己机器。务必用公网 `NAS_BASE_URL` |
| 播的是翻唱/错版本 | 单源(网易)周杰伦版权下架→全是翻唱。改用多音源裁决 `resolve_multi.py`(joox 主源) |
| 第三方 API 报 403/503 | 需带浏览器 UA(见 proxy_server.py)；请求过快会软限流→`can_play` 要退避 |
| 简/繁匹配不上(周杰倫=周杰伦) | resolve_multi 已内置 zhconv 归一 |
| Docker 拉不到 python 镜像 | 直接用 Python venv 裸跑(本节方案) |

---

## 11. 排障日志

```bash
journalctl -u easy-radio-host -f          # 主应用
journalctl -u easy-radio-musiclib -f      # 曲库代理
ls /opt/easy-radio-host/data/voice/       # TTS 产物
```

---

### 附：致谢 / Credits
- easy-radio-host 原始项目：https://gitee.com/weak0001/easy-radio-host （作者 weak0001）
- 在线音乐 API：https://music-api.gdstudio.xyz/api.php（搜索/取链为多音源数据源，版权归平台方与相应**唱片权利人**）
- DeepSeek / MiniMax 语音：版权归各自公司
- 本项目不落盘音乐，仅作 API 转发；仅供学习/合法内容体验，商用或再发布请自行确认授权，侵权风险自负。

默认 `musiclib/playlist-source.tsv` 已含 73 首华语精选（晴天/七里香/稻香/成都/后来/平凡之路…），推送仓库即含，目标机 clone 后无需再跑解析即可直接出歌。
