# 推荐设计与 Embeat 参考说明

[返回中文 README](../README.md) · [English README](../README.en.md) · [第三方来源与许可](../THIRD_PARTY_NOTICES.md#embeat)

听间将候选选择、规则校验和主持人口播分开：程序基于当前曲库选歌，DeepSeek 按选定歌曲的顺序生成口播。模型失败时使用同一组歌曲的模板口播，避免失败兜底绕过去重或偏好规则。

## 参考范围

研究来源为 GD Studio 的 [Embeat](https://github.com/gdstudio-org/Embeat/tree/7617a505ec42f109685802d1a3319e1957ac0a99)，核查版本 `7617a505ec42f109685802d1a3319e1957ac0a99`。

| Embeat 的思路 | 听间中的独立实现 | 适用边界 |
| --- | --- | --- |
| 多路候选融合 | 主题、同歌手延伸、收藏、收藏歌手、电台配置歌手偏好、探索候选轮流贡献歌曲 | 仅使用当前在线曲库，没有接入 Spotify 曲库 |
| 曲目去重与结果重排 | 规范化标题与曲库相对路径去重，优先近期未播歌曲，再分散歌手 | 缺少 ISRC，不保证识别不同名称下的同一录音 |
| 控制同歌手占比 | 优先每位歌手一首，并尽量避免相同歌手连续出现 | 小曲库或单歌手曲库允许放宽，返回降级标识 |
| 保留推荐依据 | 歌曲返回实际命中的候选来源及本次选中理由 | 理由来自程序事实，不由大模型猜测听众口味 |
| 推荐评测 | 固定随机种子验证去重、来源、覆盖、多样性与失败回退 | 离线规则验证不等于真实用户满意度提升 |

未复制、改编或分发 Embeat 的源码、权重、训练数据、向量数据库、品牌或媒体资产。未部署 Qdrant、EmbeatMLP、Track2Vec，也不声称听间已经具备声学相似度、歌单协同过滤或关联歌手模型能力。

Embeat 该版本的 README 将代码和权重描述为 MIT、数据集和数据库描述为 CC BY-NC 4.0，而根目录 LICENSE 是 CC BY-NC 4.0。许可适用范围存在歧义；此处记录参考来源，不把 Embeat 整体标注为 MIT，也不改变听间原有的许可状态。

## 候选与选择

| 来源标识 | 触发条件 | 界面理由 |
| --- | --- | --- |
| `theme` | 曲库的本项目策划标签匹配节目主题 | 曲库主题标签匹配 |
| `seed_artist` | 用户主动从某首歌延伸，候选来自相同歌手 | 与所选歌曲来自同一歌手 |
| `favorites` | 开启偏好后，候选标题存在于本地收藏 | 来自你的收藏 |
| `favorite_artist` | 开启偏好后，候选歌手与曲库中可匹配的收藏歌曲歌手一致 | 来自你收藏歌曲的歌手 |
| `profile_artist` | 候选歌手匹配部署者已有的全局歌手偏好 | 匹配电台配置的歌手偏好 |
| `explore` | 从符合条件的完整曲库随机探索 | 从在线曲库探索 |

主题标签是本项目策划的元数据，不推断 BPM、情绪强度、调性、流派或歌曲热度。没有可用标签时使用其他来源；同歌手延伸也不代表两个不同歌手在声学上相似。探索覆盖完整候选曲库，避免固定前 80 首的顺序偏差。候选融合不展示未经验证的口味百分比或亲和分数。

每期目标为 4 首，不足时按实际候选数量缩短。收藏、历史和少推荐记录按曲库标题匹配；不认识的标题不会被当作新歌曲加入节目。主动点歌走原有点歌接口，不受自动推荐的近期过滤或少推荐规则限制。

选择遵循以下边界：

1. 规范化标题和相对路径去重，排除同歌手延伸的起点歌曲。启用偏好时，「少推荐」歌曲始终排除，不因候选不足回补。
2. 优先选择近期未播歌曲，在候选融合中保留探索机会，并尽量每位歌手一首。
3. 未播候选不足时，允许放宽歌手数量限制；仍不足时按较早播放优先回补近期歌曲。用户主动发起同歌手延伸时，优先保留一首该歌手作品，必要时回补该歌手最早听过的一首。少推荐始终排除，歌曲理由及节目元数据标记这些降级。
4. 对已选歌曲重排，尽量避免同歌手相邻；单歌手候选等情况下不保证能够完全分散。
5. 没有可用候选时明确报错，不绕过少推荐记录，也不暗中插入曲库第一首。DeepSeek 仅生成口播，不能添加、替换或重复选定歌曲。

## 偏好与隐私

「按我的偏好选歌」默认关闭。收藏、历史和「少推荐」记录保存在当前浏览器；演示与正式模式隔离。开启后，仅将这些记录中的标题随本次 `/api/show` 请求发送给听间服务器，用于本次内存计算，不创建服务端个人偏好档案，不写入推荐日志。DeepSeek 只看到选中歌曲与节目上下文，不接收完整收藏、历史或少推荐列表。

关闭开关后不再发送这些本地偏好，记录仍留在浏览器。原有当前会话的近期标题 `exclude` 继续用于减少重复；点击同歌手延伸会发送主动选定的 `seed` 标题，这两项不需要开启个人偏好。部署者配置的全局歌手偏好独立于浏览器偏好，并以「电台配置」说明来源。

「少推荐」是用户明确的负向选择，可以撤回。普通下一首、跳过口播、播放失败、缓冲或离开页面都不记录为不喜欢。收听历史在歌曲实际开始播放后记录，不以加入队列代表听过；现有历史未测量听完比例，不能用来宣称用户喜欢整首歌曲。

## API 与兼容性

`POST /api/show` 保留 `theme` 和 `exclude`，新增可选 `recommendation` 对象，默认值如下：

```json
{
  "personalize": false,
  "favorites": [],
  "history": [],
  "disliked": [],
  "seed": ""
}
```

标题列表和单个标题都有请求长度上限。近期列表按从早到晚排序，最新记录在最后。只有 `personalize: true` 时才读取 `favorites`、`history` 和 `disliked`；`seed` 表示明确发起的同歌手延伸。

歌曲项新增 `recommendation.sources` 和 `recommendation.reason`。来源数组记录实际命中的来源，理由说明本次采用的候选来源，必要时附近期回补说明。节目 `meta.recommendation` 包括候选总数、可选数、选中数、可用来源、实际选用来源及以下状态：

- `personalized`：是否启用浏览器偏好。
- `recent_relaxed`：是否回补近期歌曲。
- `recent_relaxed_count`：回补的近期歌曲数量。
- `artist_limit_relaxed`：是否放宽每位歌手一首的约束。
- `theme_metadata_available`：是否存在当前主题的标签候选。
- `seed_artist_available`：是否存在同歌手延伸候选。
- `narration_fallback`：是否使用模板口播。
- `notice`：候选不足或同歌手延伸不可用等情况的提示。

旧客户端可以省略推荐对象，仍能收到兼容的 `meta` 和 `items`。无在线曲库时返回曲库错误；偏好排除后无可推荐歌曲时返回可处理的错误提示。此改动不替换音乐来源、取链接口、歌词接口或音频输出。

## 验证口径

推荐验证使用人工构造的小曲库及固定随机种子，覆盖近期优先、较早记录回补、一期去重、少推荐硬排除、歌手分散、来源真实性、完整曲库探索、小曲库和模型失败。前端验证偏好默认关闭、开启后的请求内容、少推荐撤回、主动点歌及桌面与手机布局。

推荐规则位于 `backend/recommendations.py`，对应回归测试位于 `tests/test_recommendations.py`。按 README 安装项目依赖并激活虚拟环境后，在仓库根目录执行：

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

上述命令包含项目现有 Python 回归测试；需要 FastAPI 等依赖，并非只检查推荐模块。测试结果应以实际执行记录为准，依赖缺失不视为通过。

覆盖率和歌手多样性是规则行为的离线指标；它们不能证明推荐更符合个人口味。没有引入真实用户完成率、满意度或 A/B 实验数据，不引用上游的少量 LLM 盲评作为听间效果证据。

运行 `python3 scripts/evaluate-recommendations.py` 可基于当前曲库与人工主题标签重复离线评测，报告节目内重复、近期重播、歌手多样性、曲库覆盖及纯选择计算耗时；不调用 AI、TTS 或歌曲服务，不代表网络播放性能。

## English Summary

Tingjian independently implements general ideas informed by Embeat: multiple candidate sources, deduplication, artist diversity, and factual recommendation reasons. The program selects up to four tracks from the current catalog; DeepSeek writes narration in that fixed order, with a template fallback that preserves selection rules. No Embeat code, models, datasets, vector databases, branding, or media are reused. Curated theme tags are not acoustic analysis or collaborative filtering.

Browser preferences are off by default. When enabled, only favorite, history, and "Recommend less" titles accompany each show request; the server uses them for that request without persisting a listener profile. DeepSeek receives selected songs, not the complete preference lists. Explicit dislikes remain excluded from automatic recommendations until undone, while skips and playback failures are not treated as dislikes. Direct song requests retain their existing behavior.

At Embeat revision `7617a505ec42f109685802d1a3319e1957ac0a99`, README claims MIT for code and model weights and CC BY-NC 4.0 for data, while the root LICENSE is CC BY-NC 4.0. This scope ambiguity is recorded without labeling the entire project MIT. Deterministic offline checks establish rule behavior, not proven user preference or satisfaction improvements.
