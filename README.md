# 熊出没奇遇

这是一个面向亲子共玩的 Ren'Py 互动故事项目。当前主线以“默认离线、选择可解释、失败可恢复”为原则：本地故事引擎无需网络即可完成开场、选择、属性变化、结局、评分和家庭共读记录。

## 开发入口

- 主工程：`game/`
- 原始/候选美术：`assets-source/`
- 技术与发布文档：`docs/`
- 可重复检查：`tools/`
- 历史包与风险样本：`archive/`，仅供取证，禁止再次分发
- 本机运行数据：`.local/`，不进入源码或发行包

使用 Ren'Py 8.5.2 打开本目录。提交前执行：

```sh
python3 tools/check_project.py
python3 tools/test_core_logic.py
tools/run_renpy_lint.sh
tools/run_visual_qa.sh
tools/run_build_verify.sh
```

## 故事模式

本地模式始终可用，也是默认值。云端模式仅用于受控开发或已配置代理的发行环境，玩家必须在每次冒险设置中主动开启。客户端不应携带服务商长期密钥。

可选环境变量：

```text
XCMQY_AI_ENDPOINT=https://your-controlled-proxy.example/v1/chat/completions
XCMQY_AI_KEY=short-lived-proxy-token
XCMQY_AI_MODEL=your-model-name
```

端点必须使用 HTTPS，只有本机开发的 `localhost`、`127.0.0.1` 和 `::1` 允许 HTTP。远端失败、响应为空或流式响应不完整时，游戏自动回退到本地剧情。

发布前请完整阅读 `docs/RELEASE_CHECKLIST.md` 与 `archive/SECURITY_NOTICE.md`。
