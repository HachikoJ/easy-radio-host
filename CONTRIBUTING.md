# Contributing

感谢参与 `easy-radio-host`。请先通过 GitHub Issues 描述问题或建议，再提交 Pull Request。

## 本地检查

```bash
python3 -m py_compile backend/app.py musiclib/proxy_server.py musiclib/resolve_multi.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/static-server.test.mjs
git diff --check
```

提交前请确认没有提交 `radio.env`、API Key、Cookie、运行时音频或个人数据。Commit 使用简短的动词开头，例如 `docs:`、`fix:`、`feat:`。

接口测试需要安装项目已有的 `backend/requirements.txt`，使用本地替身验证实际 FastAPI 路由，不调用外部 AI、语音或音乐服务。静态服务测试使用 Node.js 22+ 内置测试工具，无额外 npm 依赖。

前端改动运行 `node scripts/serve-demo.mjs`，打开 `http://127.0.0.1:8131/?demo=1`，检查桌面与手机的主题选择、播放/暂停、进度/音量、点歌插播、收藏/历史、明暗/沉浸及错误恢复。不要用演示数据声称完成真实在线服务联调。

## Pull Request

请说明问题、行为变化、验证命令和已知限制。涉及播放链路、公共 API、配置格式或第三方服务的改动，需要附上兼容性影响和恢复方式。
