# Claudio 能力吸收与改造方案

核查时间：2026-09-08。参考 [Claudio / hllqkb](https://github.com/hllqkb/Claudio/tree/c2eb8111dfba34437c047315ab827cbc58e33761)，固定版本 `c2eb8111dfba34437c047315ab827cbc58e33761`。结论依据源码与仓库提供的截图；没有启动其服务或验证其线上服务。

## 已接入的能力

目标是个人主题电台：开始收听、看清当前内容、随时点歌、找回喜欢的歌。保留 FastAPI + DeepSeek + MiniMax/edge-tts + 现有音乐代理，首轮不新增运行依赖或服务商。

| 参考能力与证据 | 本项目适配 | 可验证结果 |
| --- | --- | --- |
| [当前歌曲与聚焦布局](https://github.com/hllqkb/Claudio/blob/c2eb8111dfba34437c047315ab827cbc58e33761/apps/web/src/pages/PlayerPage.tsx) | 正常页突出曲目名；可进入沉浸视图，显示当前片段、接下来、口播文稿；播放条持续可用 | 切换视图不重启音频，Escape 返回，主题图片明确标作主题封面 |
| [明暗主题](https://github.com/hllqkb/Claudio/blob/c2eb8111dfba34437c047315ab827cbc58e33761/apps/web/src/hooks/useTheme.ts) | 冷白/石墨灰两套语义色，默认浅色，可保存个人选择 | 刷新保留选择；手机、错误和选中状态均可读 |
| [收藏及历史](https://github.com/hllqkb/Claudio/blob/c2eb8111dfba34437c047315ab827cbc58e33761/apps/server/src/routes/player.ts) | 当前浏览器收藏上限 100 首、最近 50 首去重记录；在实际 `playing` 事件记录 | 生成节目不等于听过，失败不进入历史；列表直接取消收藏 |
| [历史再次播放](https://github.com/hllqkb/Claudio/blob/c2eb8111dfba34437c047315ab827cbc58e33761/apps/web/src/pages/HistoryPage.tsx) | 仅存标题、主题、时间，再次点播走 `/api/intent` | 不保存短期直链或音频；点播不覆盖聊天草稿，失败可再次点播 |
| [MediaSession](https://github.com/hllqkb/Claudio/blob/c2eb8111dfba34437c047315ab827cbc58e33761/apps/web/src/audio/AudioPlayer.ts) | 系统播放/暂停、上一段/下一段、停止和定位接回当前状态机 | 插播恢复与页面按钮遵循同一逻辑；不支持的浏览器仍可操作页面 |
| [键盘操作](https://github.com/hllqkb/Claudio/blob/c2eb8111dfba34437c047315ab827cbc58e33761/apps/web/src/hooks/useKeyboard.ts) | 非输入状态支持空格播放/暂停、左右方向键前后 5 秒；页签支持方向键与 Home/End | 不抢占输入框、链接、按钮或中文输入法的原有键盘行为 |

新增功能位于 `backend/static/listening.js`、`listening.css`，由 `app.js` 接入；保持原有 `song/talk/text` 播放顺序和插播恢复。演示记录与真实接口模式使用不同存储键。

当前元数据没有稳定的歌曲 ID 暴露给前端，因此首轮按曲目标题识别收藏，无法区分同名同版本标识缺失的歌曲。再次点播结果由现有 API 解析，可能匹配不同版本；下一阶段应先补 `(source, id)`，再承诺精确重播或跨设备同步。

## 下一阶段：先补数据，再补效果

| 优先级 | 建议 | 必要条件与验收 |
| --- | --- | --- |
| P1 | 可选歌曲身份、歌手、实际封面 | 当前代理已有 source/sid/artist，主应用输出需保留这些字段。向旧 `kind/title/text/url` 项增添可选元数据，旧客户端不受影响；缺封面时明确回退主题图 |
| P1 | 同步歌词，逐字歌词作为可选增强 | 参考 [lyric.ts](https://github.com/hllqkb/Claudio/blob/c2eb8111dfba34437c047315ab827cbc58e33761/apps/server/src/routes/lyric.ts)。按音源能力提供真实 LRC/YRC；缺歌词、纯音乐、时间偏移正常降级。只有逐行时间戳时不能伪造逐字精度 |
| P1 | 口味与场景进入统一推荐上下文 | 当前 `backend/app.py` 已读取 profile 并用于节目生成，应先统一点歌路径与显式偏好。参考 [context.service.ts](https://github.com/hllqkb/Claudio/blob/c2eb8111dfba34437c047315ab827cbc58e33761/apps/server/src/services/context.service.ts)，时间可本地推导；天气/日历需另行确定服务和个人数据边界 |
| P2 | 刷新后恢复节目 | 保存顺序与位置但以暂停态恢复；显式播放时重取歌曲直链，过期口播给出恢复反馈。需先解决歌曲身份和过期资源，不存永久可播的假承诺 |
| P2 | 实时频谱与下一段预加载 | 当前音乐代理通过 302 跳转到第三方直链。Web Audio 受 CORS 限制，直接接入可能让声音静音；先验证音源策略与单一 AudioContext，再接真实 analyser。预加载限制为一段并能取消，避免重复取链/额外 TTS 开销 |
| P2 | 跨设备收藏与历史 | 需要服务端存储和用户身份，属于独立接口/数据结构改造，不混入纯前端迭代 |

逐字歌词、真正歌曲封面、封面取色、频谱、个性化模型反馈和 PWA 均未宣称在首轮完成。音乐音频不离线缓存；浏览器 MediaSession 支持也不等于所有设备都能后台长期播放。

## 不吸收的实现

- 不搬运整套 React/Fastify/SQLite 技术栈，不更换 Claude、Fish Audio 或网易云账号体系。
- 不复制上游配置、凭证、音源解锁与下载回退逻辑；不将 MIT 解释成音乐资源再分发许可。
- 不采用固定画像统计或默认模拟日程。上游 `plays.repo.ts` 的语言分布有固定值，`dispatch.ts` 在推荐生成时即记 listen，均不能作为真实收听证据。
- 不复制会附带服务端凭证的任意 URL 封面代理；新增代理需限制可信目标与转发头。
- 不采用鼠标光晕、流体光球、满屏粒子、多层发光等装饰，以保证手机可读性和播放稳定性。
- Claudio 当前 `audio.preload = "auto"` 只预加载当前音频，不把它描述成已实现双音频无缝预加载。

## 版权与发布边界

Claudio 为 MIT，版权为 `Copyright (c) 2026 hllqkb`。本项目独立实现交互，没有复制其源文件或截图素材；仍保留完整 MIT 文本、固定来源版本和中英文致谢，见 [第三方来源清单](../THIRD_PARTY_NOTICES.md)。原 Gitee 项目 `weak0001` 的署名与原授权状态保持准确。

正式前端由 `backend/static/` 提供，中文默认 README、独立英文 README 与实际页面截图保持对应。主持人仍为小蓝，原后端接口、歌单及密钥配置保持兼容。必要时可恢复提交 `a8db34a` 中的原前端；本次改造不涉及数据迁移。
