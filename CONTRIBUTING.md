# Contributing

感谢参与 `easy-radio-host`。请先通过 GitHub Issues 描述问题或建议，再提交 Pull Request。

## 本地检查

```bash
python3 -m py_compile backend/app.py musiclib/proxy_server.py musiclib/resolve_multi.py
git diff --check
```

提交前请确认没有提交 `radio.env`、API Key、Cookie、运行时音频或个人数据。Commit 使用简短的动词开头，例如 `docs:`、`fix:`、`feat:`。

## Pull Request

请说明问题、行为变化、验证命令和已知限制。涉及播放链路、公共 API、配置格式或第三方服务的改动，需要附上兼容性影响和恢复方式。

