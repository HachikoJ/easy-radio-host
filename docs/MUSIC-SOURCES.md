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

搜索、取链和歌词经过同一个常驻代理，共享滚动 300 秒最多 50 次 GD 请求；缓存命中与合并中的相同请求不重复计费。不支持的渠道冷却一小时。收到 429 后尊重等待时间，不靠切换渠道绕过限额。该预算不能保证上游永不限流，也不控制服务器外其他程序的请求。

| 状态 | 含义 | 网页处理 |
| --- | --- | --- |
| `available` | 匹配录音已通过真实音频探针 | 入队或替换当前失效地址 |
| `unavailable` | 本次开放渠道、关键词和结果已查完，无可播匹配 | 明确提示曲名与无相关可用音源，之后继续下一段 |
| `limited` | 本地请求预算或上游限额阻止继续 | 提示检索未完成，保留重试及手动下一曲 |
| `temporary` | 超时、网络错误或仍有未查完的分页 | 提示检索未完成，保留重试及手动下一曲 |

推荐先校验再生成对应口播，失败候选按原偏好规则补位；只输出已验证歌曲。主动点歌不受近期过滤或少推荐记录限制。播放期间失效时先刷新原地址，再检索未失败的匹配音源；停止、暂停或手动切歌会取消恢复，不接受迟到结果。无结果通知先展示再推进，不无限生成失败节目。

## 接口与维护

- 主应用 `POST /api/playback/resolve` 接收 `title`、可选 `artist/source/id` 和失败候选 `exclude`，返回状态及已验证 `item`，不接受任意媒体 URL。
- 曲库代理 `POST /resolve` 提供共享解析服务，返回 `track` 元数据、相对路径、已查渠道，限流时附等待秒数。
- 原点歌接口的 `items/actions` 保持兼容；失败时增加 `notice/availability`。旧 `/api/chat` 同样走校验，返回可见提示。
- `resolve_multi.py` 通过常驻代理解析维护歌单。任何歌曲未验证成功时保持原文件，不用不完整结果覆盖已有歌单。

范围涉及歌曲入队校验、音频流转发与自动恢复；不迁移歌单、收藏或配置。回退本次提交并重启两个服务可恢复原实现，新增的简繁转换依赖可以保留。

## English

Every recommendation and explicit song request must pass recording identity matching and a real audio range probe before admission. The resolver searches the ten channels listed by GD Studio, respecting artist and version constraints. It shares a 50-request rolling five-minute budget across searches, URLs, and lyrics, with caching and concurrent request deduplication. Unsupported channels cool down; rate limits and incomplete searches are never reported as proof that a song does not exist.

An exhausted search produces an explicit track-specific notice before the player advances. Temporary failures remain retryable. Playback refreshes expired URLs and searches other matching sources before giving up; cancellation prevents stale responses from changing the current track. Same-origin streaming supports seeking without saving song audio. Roll back the commit and restart both services to restore the earlier behavior; no data migration is needed.

官方参考 / Reference: [GD 音乐台 API](https://music-api.gdstudio.xyz/api.php)，文档更新日期 2026-06-26，核验日期 2026-09-09。GD Studio 的服务规则与项目致谢继续适用。
