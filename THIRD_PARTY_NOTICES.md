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

## 原始项目 / Original Project

[easy-radio-host](https://gitee.com/weak0001/easy-radio-host)，作者 / author **weak0001**。保留原作者署名和版权归属。原始代码的完整授权尚未核清，本仓库尚未声明统一开源许可证；Claudio 的 MIT 授权不改变这一状态。

Original attribution and ownership are retained. The original source's complete licensing terms have not been verified, and this repository does not currently declare a unified open-source license. Claudio's MIT license does not change that status.

## 前端资产 / Frontend Assets

- UI 图标：Lucide，ISC；[许可 / license](backend/static/assets/LICENSE-lucide)。图标从 Lucide 图标库导出。
- 主题摄影：Unsplash；[逐图来源 / per-image sources](backend/static/assets/SOURCES.md)，[使用条款 / terms](https://unsplash.com/license)。图片标为主题封面，不作为实际唱片封面。
- 听间标记复用本项目此前创建的声波对话 Logo；未使用 Claudio 标记。
- 演示音频由本项目合成，固定回应仅用于明确的演示模式；不包含 Claudio 音频或第三方歌曲文件。

UI icons come from Lucide under ISC. Theme photos are documented individually and are not presented as actual album artwork. Tingjian reuses this project's existing speech-wave mark. Demo audio is locally synthesized for this project; fixed responses are limited to explicit demo mode.

## 服务 / Services

DeepSeek、MiniMax、edge-tts、在线音乐 API 及其依赖继续遵循各自的授权、服务与音乐使用条款。项目致谢不表示获得额外音源再分发权，也不表示第三方对本项目背书。

DeepSeek, MiniMax, edge-tts, the online music API, and their dependencies remain governed by their respective licenses and service/music terms. Attribution does not grant additional music redistribution rights or imply endorsement.
