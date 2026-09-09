# 音源检索与恢复 / Source Resolution

歌曲进入节目或点歌插播前，必须先匹配录音身份并读取真实音频。搜索命中、非空 URL、HTTP HEAD 成功均不能单独证明可播。`/songs.txt` 是候选目录，不是可用性承诺。

## 匹配与校验

- 按歌名、歌手和版本匹配，统一简繁体与标点；歌手不能用子串猜测，不将翻唱、现场、伴奏或重混替代用户指定的录音。
- 旧歌单 ID 只有在记录的版本也匹配时才优先验证；旧 ID 失效后搜索其他候选及渠道。
- 检索范围为 GD Studio 官方列出的 `netease`、`kuwo`、`joox`、`bilibili`、`tencent`、`tidal`、`qobuz`、`apple`、`ytmusic`、`spotify`。渠道开放情况由上游决定。
- 先跨渠道查完整关键词，再尝试简体关键词、仅歌名和后续页。每次最多三页、44 秒；超时或仍有未查完的候选返回“检索未完成”，不宣告歌曲不存在。
- 匹配候选逐个取链，按 320 / 192 / 128 码率寻找可播版本，对受限 CDN 发起小范围 GET，验证状态和音频文件头。歌曲、签名地址和歌词不落盘。
- 网页音频由本站流转发并透传单 Range，Nginx `/music/` 关闭响应缓冲与临时文件；原 `/s/<source>/<id>.mp3` 的 307 形式仍兼容。歌词使用对应的 `lyric_id`，不假定它等于音频 ID。

## 额度与结果

搜索、取链和歌词经过同一个常驻代理，共享滚动 300 秒最多 45 次 GD 请求，在上游每 5 分钟 50 次的政策下保留 5 次余量；不再另行降低该总额度。缓存命中与合并中的相同请求不重复计费。SQLite 以事务协调共享数据库的进程，保存请求时间和上游冷却，服务重启不会重置额度。不支持的渠道冷却一小时。收到 429 后遵守完整 `Retry-After`，超过 300 秒也不缩短，不靠切换渠道绕过限额。

短期音频校验缓存过期后，可以重新探测仍在内存中的签名地址；该 CDN 音频探针不调用 GD API，只有再次验证可播才使用。额度状态查询也不调用 GD。独立运行且未共享数据库的程序不在此预算内，上游的其他风控仍可能影响服务。

| 状态 | 含义 | 网页处理 |
| --- | --- | --- |
| `available` | 匹配录音已通过真实音频探针 | 入队或替换当前失效地址 |
| `unavailable` | 本次开放渠道、关键词和结果已查完，无可播匹配 | 明确提示曲名并播报无相关音源，再尝试下一首推荐 |
| `limited` | 本地请求预算或上游限额阻止继续 | 提示并播报限流原因，尝试可播缓存或下一首；无可播项时自动等待额度恢复 |
| `temporary` | 超时、网络错误或仍有未查完的分页 | 提示并播报暂时无法完成检索，再尝试下一首；无可播项时等待重试 |

推荐先校验再生成对应口播，失败候选按原偏好规则补位；只输出已验证歌曲。主动点歌不受近期过滤或少推荐记录限制。播放期间失效时先刷新原地址，再检索未失败的匹配音源。故障原因先用文字说明并播放缓存的原因播报，再自动推进；不会为每次故障重新调用 TTS。无可播队列时给出等待提示，按服务允许的时间自动恢复，不连续生成失败节目或密集查询被限流的 API。

暂停会取消节目、点歌、音源恢复与歌词请求，停止原因播报和等待计时，并卸载音频连接；队列与当前位置保留，用户恢复播放后再加载。关闭页面同样终止本页资源。服务端协作取消已断开的请求，避免继续发起后续上游检索；已经发送的外部请求仍计入额度，不因取消退还。手动切曲或旧请求晚到不会覆盖用户的新播放状态。

## 接口与维护

- 主应用 `POST /api/playback/resolve` 接收 `title`、可选 `artist/source/id` 和失败候选 `exclude`，返回状态及已验证 `item`，不接受任意媒体 URL。
- 主应用 `GET /api/playback/availability` 查询恢复时机；代理 `GET /availability` 返回 `status`（`ready` 或 `limited`）、`retry_after` 秒数及 `remaining` 次数。查询不消耗 GD 额度。
- 主应用 `GET /api/playback/announcement/{reason}.mp3` 提供缓存的故障原因语音；网页在音频不可用时尝试浏览器语音降级。
- 曲库代理 `POST /resolve` 提供共享解析服务，返回 `track` 元数据、相对路径、已查渠道，限流时附等待秒数。
- 原点歌接口的 `items/actions` 保持兼容；所有音源失败均返回 `notice/availability` 和 `next` 动作，客户端先播报后推进。旧 `/api/chat` 同样走校验，返回可见提示。
- `/api/show` 无可播歌曲时仍使用相应错误状态码，但 `detail` 由纯文字改为包含原因与恢复信息的对象；自建客户端需兼容该结构。
- `resolve_multi.py` 通过常驻代理解析维护歌单。任何歌曲未验证成功时保持原文件，不用不完整结果覆盖已有歌单。

范围涉及故障后的连续播放、暂停资源释放、节目错误响应和代理额度存储，不迁移歌单或收藏。默认额度数据库为 `data/gd-quota.sqlite3`；可用 `GD_QUOTA_DB` 指定共享路径，systemd 部署使用 `/var/lib/tingjian/gd-quota.sqlite3`。数据库只保存请求计数与冷却，不保存歌曲、签名地址、歌词或用户输入。

从旧内存额度版本首次升级时，先停止旧代理并设置至少 300 秒的迁移冷却；若已知上游等待更长，应保留更晚的恢复时间。回退代码与对应服务配置可恢复旧行为，但须保留当前 SQLite 额度状态，不能用旧备份覆盖来重置预算。旧实现不读取该状态，重启前必须等待已记录冷却结束且最后一次 GD 请求已过去 300 秒，恢复后仍须保持每 300 秒最多 45 次的限制。具体操作见[部署手册](../DEPLOY-HANDOFF.md#7-更新与恢复)。

## English

Every recommendation and explicit song request must pass recording identity matching and a real audio range probe before admission. The resolver searches the ten channels listed by GD Studio, respecting artist and version constraints. Searches, URLs, and lyrics share exactly 45 allowed requests per rolling 300 seconds. SQLite transactions coordinate processes sharing the same database and preserve counts and cooldowns across restarts. Cache hits and merged requests do not consume additional slots. Upstream `Retry-After` is never shortened, including waits longer than 300 seconds. Rate limits and incomplete searches are never reported as proof that a song does not exist.

Missing sources, rate limits, and temporary failures produce a text notice and a cached spoken explanation before the player tries the next recommendation. Explicit missing-song notices identify the requested track. Cached URLs are probed again without GD requests; with nothing playable, the player announces the wait and automatically resumes when permitted. Pausing or closing the page cancels requests, announcements, waiting timers, and audio connections; pause retains the queue and playback position. Cooperative server cancellation stops further searches, while requests already sent still count. Same-origin streaming supports seeking without saving song audio.

The new availability and cached announcement endpoints support this recovery flow. Song-request failures include a `next` action; `/api/show` errors now use a structured `detail` object. The quota database contains counts and cooldowns, not media, signed URLs, lyrics, or user input. Upgrading from in-memory accounting requires an initial 300-second migration cooldown, or a longer known upstream wait. Keep the current database during rollback. Before running an older implementation that cannot read it, wait until the recorded cooldown has ended and 300 seconds have elapsed since the last GD request, and retain the 45-request limit. Playlists and favorites require no migration.

官方参考 / Reference: [GD 音乐台 API](https://music-api.gdstudio.xyz/api.php)，文档更新日期 2026-06-26，核验日期 2026-09-09。GD Studio 的服务规则与项目致谢继续适用。
