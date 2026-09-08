<a id="top"></a>

# 小蓝电台 · Xiaolan Radio

<p align="center">
  <img src="assets/brand/xiaolan-radio-logo.png" alt="小蓝电台 Logo：蓝色对话声波与珊瑚红播出信号" width="144">
</p>

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-009688)
![DeepSeek](https://img.shields.io/badge/DeepSeek-AI-1677E8)
[![GitHub stars](https://img.shields.io/github/stars/HachikoJ/easy-radio-host?style=flat)](https://github.com/HachikoJ/easy-radio-host)

[English](README.en.md) · [个人官网](https://www.deline.top) · [核心体验](#核心体验) · [产品预览](#产品预览) · [如何运行](#如何运行) · [项目资料](#项目资料) · [联系作者](#联系作者)

**选一个主题，把接下来的时间交给音乐。**

小蓝电台是一个面向喜欢主题听歌、愿意自行部署的听众的 AI 音乐电台。主持人选歌、串联话题并合成口播，浏览器连续播放「口播 → 歌曲 → 口播」。歌曲来自在线音乐 API，无需准备本地音乐文件。

**项目地址：** [HachikoJ/easy-radio-host](https://github.com/HachikoJ/easy-radio-host)

**使用入口：** 自行部署后访问服务器的 8100 端口；本仓库未提供托管播放服务。

## 核心体验

- **主题节目**：DeepSeek 根据主题和歌单编排节目，串联歌曲与话题。
- **主持人口播**：MiniMax 合成主持人声音，支持 edge-tts 降级。
- **连续播放**：网页依次播放口播与歌曲，支持暂停和切换片段。
- **点歌互动**：输入想听的内容，与主持人聊天或点歌。
- **在线曲库**：歌单保存歌名、歌手、音源和 ID，播放时动态获取歌曲直链。

## 产品预览

### 桌面端

<p>
  <img src="docs/radio-desktop.png" alt="小蓝电台桌面端待播放页面：生成节目、片段切换和点歌输入" width="100%">
</p>

### 移动端

<p>
  <img src="docs/radio-mobile.png" alt="小蓝电台移动端待播放页面：播放控制与点歌输入" width="375">
</p>

截图为当前页面的本地待播放状态，裁去了下方空白区域。生成节目和播放音乐需要配置相应服务。

## 工作原理

```text
浏览器
  → 主应用 :8100
      → DeepSeek 编排节目
      → MiniMax / edge-tts 合成口播
      → 在线曲库代理 :8001 读取歌单
  ← 口播与歌曲播放清单
  → 曲库代理调用音乐 API，跳转至歌曲直链
```

曲库代理读取 `musiclib/playlist.tsv`，通过 `/songs.txt` 提供标题与相对路径；通过 `/s/<source>/<id>.mp3` 获取歌曲地址并返回 302 跳转。歌曲音频不落盘，生成的口播文件保存在服务端 `data/voice/`。

## 如何运行

需要 Python 3.10+。完整的 Linux 部署步骤、systemd 配置和故障排查见 [部署手册](DEPLOY-HANDOFF.md)。

```bash
git clone https://github.com/HachikoJ/easy-radio-host.git
cd easy-radio-host
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt zhconv
```

1. 按部署手册创建 `radio.env`，配置 DeepSeek、MiniMax 和服务地址。
2. 启动主应用（8100）与在线曲库代理（8001）。
3. 确认浏览器可以访问两个端口，打开主应用页面并生成一期节目。

### 主要配置

| 变量 | 用途 |
| --- | --- |
| `DEEPSEEK_KEY` | 节目编排与对话的 API Key |
| `MINIMAX_KEY` | 主持人口播的 API Key |
| `NAS_LIST_URL` | 曲库列表地址，通常为 `http://127.0.0.1:8001/songs.txt` |
| `NAS_BASE_URL` | 浏览器可以访问的在线曲库代理地址 |
| `RADIO_BASE` | 浏览器可以访问的主应用地址 |
| `DATA_DIR` | 口播和运行数据目录 |

`NAS_*` 是保留的兼容变量名，指向在线曲库代理。远程浏览器无法访问服务器自身的 `127.0.0.1`，对外播放地址须使用服务器的可访问地址。

## API

| 服务 | 方法 | 路径 | 说明 |
| --- | --- | --- | --- |
| 主应用 :8100 | POST | `/api/show` | 生成节目播放清单 |
| 主应用 :8100 | POST | `/api/chat` | 对话与点歌 |
| 主应用 :8100 | GET | `/voice/*.mp3` | 主持人口播 |
| 曲库代理 :8001 | GET | `/songs.txt` | 在线歌单元数据 |
| 曲库代理 :8001 | GET | `/s/<source>/<id>.mp3` | 获取直链并跳转 |

## 歌单维护

在部署目录 `/opt/easy-radio-host` 编辑 `musiclib/playlist-source.tsv`，每行填写「歌名 + Tab + 歌手」。备份现有的 `musiclib/playlist.tsv` 后运行：

```bash
/opt/easy-radio-host/.venv/bin/python3 /opt/easy-radio-host/musiclib/resolve_multi.py
```

脚本会重写解析结果，搜索多音源、过滤版本并检查候选播放地址。匹配结果和可播性仍受第三方服务影响，请复核未命中或版本不符的歌曲。

## 隐私与限制

- API Key、Cookie 和 `radio.env` 不得提交到 GitHub。
- 节目主题、对话和曲目元数据会发送至相关 AI 或音乐服务；口播音频与运行数据保存在服务端。
- DeepSeek、MiniMax 等服务可能产生费用，价格与额度以各服务商为准。
- AI 生成的口播不保证事实准确；歌曲可用性、版本匹配和响应时间依赖第三方服务。
- 本项目用于个人学习与体验，歌曲版权归相应权利人，使用时须遵守平台规则。
- 项目处于实验阶段，目前未确认上游代码的完整授权条款，仓库尚未声明统一开源许可证。

## 项目资料

- [部署手册](DEPLOY-HANDOFF.md)：服务配置、歌单维护和排障。
- [贡献指南](CONTRIBUTING.md)：验证命令与 Pull Request 规范。
- [行为准则](CODE_OF_CONDUCT.md) · [安全政策](SECURITY.md)。
- [更新记录](CHANGELOG.md) · [协作约定](AGENTS.md)。
- [持续集成](https://github.com/HachikoJ/easy-radio-host/actions)：Python 语法检查。

## 致谢

- [easy-radio-host 原始项目](https://gitee.com/weak0001/easy-radio-host)，作者 `weak0001`；保留原作者署名与版权归属。
- [在线音乐 API](https://music-api.gdstudio.xyz/api.php)，提供多音源搜索与取链。
- DeepSeek、MiniMax、edge-tts 及其他第三方依赖；其权利和使用条款归各自权利人。

## GitHub 关注度

[![Star History Chart](https://api.star-history.com/svg?repos=HachikoJ/easy-radio-host&type=Date)](https://star-history.com/#HachikoJ/easy-radio-host&Date)

[查看独立 Star History](https://star-history.com/#HachikoJ/easy-radio-host&Date)

## 联系作者

交流 AI 音乐产品、反馈使用体验或支持项目，可以通过以下方式联系：

- 个人官网：[www.deline.top](https://www.deline.top)
- GitHub：[HachikoJ](https://github.com/HachikoJ) · [提交问题](https://github.com/HachikoJ/easy-radio-host/issues)
- 微信：`hostrow`，添加时请备注「小蓝电台」
- 邮箱：[946106011@qq.com](mailto:946106011@qq.com)

<table>
  <tr>
    <td align="center" valign="top" width="33%">
      <strong>微信联系</strong><br><br>
      <a href="assets/wechat-contact.png"><img src="assets/wechat-contact.png" alt="Wilson 微信联系二维码" width="180"></a>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>微信赞赏</strong><br><br>
      <a href="assets/donate-wechat.png"><img src="assets/donate-wechat.png" alt="微信赞赏二维码" width="180"></a>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>支付宝赞赏</strong><br><br>
      <a href="assets/donate-alipay.png"><img src="assets/donate-alipay.png" alt="支付宝赞赏二维码" width="180"></a>
    </td>
  </tr>
</table>

## 加入交流群

交流使用经验、分享想听的主题，也欢迎反馈问题。

<p align="center">
  <a href="assets/group-qr.jpg"><img src="assets/group-qr.jpg" alt="微信交流群二维码" width="240"></a>
</p>

<p align="right"><a href="#top">返回顶部</a></p>
