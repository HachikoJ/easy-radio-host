# 第三方来源与致谢 / Third-Party Notices

## Claudio

- 项目 / Project: [hllqkb/Claudio](https://github.com/hllqkb/Claudio)
- 作者与版权 / Author and copyright: **Copyright (c) 2026 hllqkb**
- 许可证 / License: [MIT 原文 / Full MIT text](backend/static/licenses/Claudio-MIT.txt)
- 研究版本 / Reviewed revision: [`c2eb8111dfba34437c047315ab827cbc58e33761`](https://github.com/hllqkb/Claudio/tree/c2eb8111dfba34437c047315ab827cbc58e33761)，2026-09-08 核查。

听间前端参考了 Claudio 的当前歌曲布局、明暗主题、收藏与播放历史、MediaSession 系统媒体控制交互。对应的 `backend/static/listening.js`、`backend/static/listening.css` 及页面接入由本项目独立实现，适配既有 FastAPI 接口和 song/talk/text 混合队列；没有复制其 React/Fastify 源文件。完整 MIT 文本随参考记录保留，不代表本仓库整体改用 MIT。

The Tingjian frontend draws interaction ideas from Claudio's current-track layout, light/dark themes, favorites, listening history, and MediaSession controls. `backend/static/listening.js`, `backend/static/listening.css`, and the page integration were independently implemented for the existing FastAPI contracts and mixed song/talk/text queue. No React/Fastify source files were copied. The complete MIT notice accompanies this reference record and does not relicense this repository as a whole.

未复用 Claudio 的品牌、截图、歌曲、唱片封面、账号凭证或音源解锁逻辑。音乐、图片、商标及第三方服务另有权利与条款，MIT 许可不替代它们的授权。未来复制或改编其代码时，须更新来源文件映射并随副本保留版权与完整许可。

Claudio's branding, screenshots, tracks, album artwork, account credentials, and music-unblocking implementation are not redistributed here. Music, images, trademarks, and third-party services remain subject to their own rights and terms. Any future copied or adapted code must be recorded with file mappings and retain its copyright and full license notice.

## Qiaomu Music Player Web

- 项目 / Project: [joeseesun/qiaomu-music-player-web](https://github.com/joeseesun/qiaomu-music-player-web)
- 作者与版权 / Author and copyright: **Qiaomu / 向阳乔木 · Copyright (c) 2026 Qiaomu**
- 许可证 / License: [MIT 原文 / Full MIT text](https://github.com/joeseesun/qiaomu-music-player-web/blob/a8519a23e0038a49cfa9495cc0b420a3b4e4825d/LICENSE)
- 研究版本 / Reviewed revision: [`a8519a23e0038a49cfa9495cc0b420a3b4e4825d`](https://github.com/joeseesun/qiaomu-music-player-web/tree/a8519a23e0038a49cfa9495cc0b420a3b4e4825d)

听间参考该项目及常见音乐播放器的歌词逐行高亮、点按跳播、自动跟随和可关闭播放动效等通用交互，围绕现有播放器独立实现。未复制其源码、品牌、视觉皮肤、截图、歌曲、歌词或封面。听间的播放动效是随真实播放状态启停的 CSS 动画，不是实时音频频谱，也不接管音频输出。

Tingjian independently implements common player interactions informed by this project and familiar music players: synchronized lyric highlighting, line seeking, automatic following, and optional playback animation. No upstream source code, branding, visual skin, screenshots, songs, lyrics, or artwork were copied. Tingjian's CSS animation follows actual playback state; it is not a real-time spectrum and does not intercept audio output.

## lrc-kit

- 项目与版本 / Project and version: [lrc-kit 1.2.1](https://www.npmjs.com/package/lrc-kit/v/1.2.1)
- 作者与版权 / Author and copyright: **Copyright (c) 2016 Weirong Xu**
- 许可证 / License: [完整 MIT 文本 / Full MIT text](backend/static/vendor/lrc-kit/LICENSE)
- 随附源码 / Vendored source: `backend/static/vendor/lrc-kit/lrc.js`, `backend/static/vendor/lrc-kit/line-parser.js`

上述文件用于解析 LRC 时间戳；唯一上游修改是在 `lrc.js` 的相对导入中补充 `.js` 扩展名，以支持浏览器 ES Modules。版权与完整许可随源码保留。界面、歌词获取、跟随、译文与时间偏移逻辑由本项目实现。

These files parse LRC timestamps. The only upstream change adds the `.js` extension to the relative import in `lrc.js` for browser ES Modules. Copyright and the full license are retained alongside the source. The interface, lyric fetching, following, translation display, and timing-offset logic are implemented by this project.

## 原始项目 / Original Project

[easy-radio-host](https://gitee.com/weak0001/easy-radio-host)，作者 / author **weak0001**。保留原作者署名和版权归属。原始代码的完整授权尚未核清，本仓库尚未声明统一开源许可证；Claudio 的 MIT 授权不改变这一状态。

Original attribution and ownership are retained. The original source's complete licensing terms have not been verified, and this repository does not currently declare a unified open-source license. Claudio's MIT license does not change that status.

## 前端资产 / Frontend Assets

- UI 图标：Lucide，ISC；[许可 / license](backend/static/assets/LICENSE-lucide)。图标从 Lucide 图标库导出。
- 主题摄影：Unsplash；[逐图来源 / per-image sources](backend/static/assets/SOURCES.md)，[使用条款 / terms](https://unsplash.com/license)。图片标为主题封面，不作为实际唱片封面。
- 听间标记复用本项目此前创建的声波对话 Logo；未使用 Claudio 标记。
- 演示音频由本项目合成为原创器乐，歌词区域的演示文案也为原创并明确标注「非歌曲原词」；固定回应仅用于明确的演示模式，不包含参考项目音频或第三方歌曲文件。

UI icons come from Lucide under ISC. Theme photos are documented individually and are not presented as actual album artwork. Tingjian reuses this project's existing speech-wave mark. Demo audio is original synthesized instrumental music; text in the demo lyrics view is original and explicitly labeled as demo copy, not the song's lyrics. Fixed responses are limited to explicit demo mode.

## 服务 / Services

DeepSeek、MiniMax、edge-tts、在线音乐 API 及其依赖继续遵循各自的授权、服务与音乐使用条款。项目致谢不表示获得额外音源再分发权，也不表示第三方对本项目背书。

DeepSeek, MiniMax, edge-tts, the online music API, and their dependencies remain governed by their respective licenses and service/music terms. Attribution does not grant additional music redistribution rights or imply endorsement.

歌词通过现有 GD 音乐 API 代理按当前歌曲的来源和 ID 获取，并展示来源说明。代理仅在内存中缓存最多 128 条结果、每条 300 秒，不写入磁盘，不随仓库再分发歌词库。歌词与译文版权归原权利人；软件 MIT 许可不授予歌词、歌曲或封面的使用权。

Lyrics are requested through the existing GD music API proxy using the current song's source and ID, with attribution in the player. The proxy caches up to 128 responses in memory for 300 seconds each, without writing lyrics to disk or bundling a lyric library with the repository. Lyrics and translations belong to their respective rights holders; software MIT licenses do not grant rights to lyrics, music, or artwork.
