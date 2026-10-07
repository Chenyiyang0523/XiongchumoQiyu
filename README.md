# 熊出没奇遇

这是一个面向亲子共玩的 Ren'Py 互动故事项目。当前主线以“默认离线、选择可解释、失败可恢复”为原则：本地故事引擎无需网络即可完成开场、选择、属性变化、结局、评分和家庭共读记录。

既有发行包：**1.1.0-rc.1**，位于 `dist/1.1.0-rc.1/`。当前工作目录已接入 Linux 的故事核心改进；体验新版请用下方启动入口，旧发行包尚未重打。移植说明和验收证据见 `docs/integration/2026-10-07/`。

本地包含森林古地图、森林运动会、风雨后的家园、森林美食节四个篇章，每篇有三条开局路线。长篇补充中段关卡；儿童模式提供简单探索，青少年模式加入推理题。亲子模式有讨论环节；行动挑战支持空格、点击、轻松完成，超时也能继续。提示、三类心愿支线、三种指定结局均可离线使用。

自定义情景按关键词选择篇章，未匹配时进入寻宝篇；自定义行动按观察、行动、合作关键词进入预设路线。它是有限的本地故事库。云端生成保留接口，当前交付不包含服务端。

## 开发入口

本机接入 GLM 后，可双击项目根目录的 `启动游戏.command`。启动器依次读取 `XCMQY_API_KEY`、`~/.xcmqy/config.json`、`~/.claude/settings.json` 中已有的 BigModel 配置，启动仅监听本机的临时代理，再启动游戏；在冒险设置中选择「云端动态故事」。长期密钥只由代理读取，游戏使用临时令牌，退出游戏后代理一起关闭。使用智谱普通按量 API，故事使用 Linux 原版默认配置：`glm-4.7`、关闭思考、温度 0.9；点子解析和备用模型为 `glm-4.7-flashx`。代理原样转发各角色的模型参数，`XCMQY_GLM_MODEL` 只影响独立连通检查和旧版评价接口。运行 `python3 tools/run_glm_game.py --check-api` 可单独验证真实 API。此入口继续使用 `.local/player-saves` 作为 Ren’Py 存档目录，临时文件、缓存和存档签名数据均放在工作目录内，不改写用户目录里的配置。

启动器优先使用 `XCMQY_RENPY_SDK_ROOT` 或本工程 `.local/toolchains/renpy-8.5.2-sdk`；本机也兼容原项目目录中现有的 SDK。迁移到其他电脑时，请安装 SDK 并设置该变量。

- 主工程：`game/`
- 原始/候选美术：`assets-source/`
- 技术与发布文档：`docs/`
- 可重复检查：`tools/`
- 历史包与风险样本：`archive/`，仅供取证，禁止再次分发
- 本机运行数据：`.local/`，不进入源码或发行包

使用 Ren'Py 8.5.2 打开本目录；或用 `XCMQY_RENPY_SDK_ROOT` 指定 SDK。检查脚本在隔离副本中运行，不修改玩家存档。提交前执行：

```sh
python3 tools/check_project.py
python3 tools/test_core_logic.py
python3.12 tools/test_online_story.py
python3 tools/test_glm_relay.py
tools/run_renpy_lint.sh
tools/run_visual_qa.sh
tools/run_engine_qa.sh
tools/run_regression_qa.sh
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

端点必须使用 HTTPS，只有本机开发的 `localhost`、`127.0.0.1` 和 `::1` 允许 HTTP。云端故事失败时暂停当前世界线，点击「重试」会沿用同一个选择，不重置进度、不插入无关本地剧情。评价和报告失败时可根据真实游戏记录在本地整理。

云端现在直接运行 Linux `m3-r2@8514075` 的 `LeanWriter`。51 个上游源码/素材文件原样保留，校验清单见 `game/xcmengine/UPSTREAM.json`。提示词、章节安排、选择后的完整故事路径、自由点子解析、流式截断和修复均由原版负责；Ren’Py 适配层只处理输入、存档和显示，不再附加上一版的三页、属性、知识题或结尾提示。

5/10/15–20 分钟分别映射原版短/中/长篇：3/4/5 章，2/3/4 次选择，结尾一章四页。云端人物由情景决定，难度和神器设置不参与生成。账户和离线故事保留；旧云端存档可以查看已有内容，但续写需开始新冒险，新存档保存完整 Linux 故事对象。重启 `启动游戏.command`，选「云端动态故事」→「随机」→「开始冒险」。

本次接入与离线对照证据见 `docs/integration/2026-10-07/Linux原版路径接入.md`。先前 `真实试玩.md` 和 `live-stories.json` 对应已替换的适配版，不代表本次原版路径的联网测试。

真实联网验收会消耗 API 额度，需显式运行：`python3.12 tools/playtest_glm_story.py --live`（Python 3.10+；新结果写入 `linux-live-stories.json`）。

发布前请完整阅读 `docs/RELEASE_CHECKLIST.md` 与 `archive/SECURITY_NOTICE.md`。
