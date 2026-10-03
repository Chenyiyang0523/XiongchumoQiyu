# 熊出没奇遇 2.0

2.0 将四个既有主题和自定义主题接入同一个互动绘本引擎：在线服务规划故事，Ren’Py 客户端呈现页面、收集行动并保存已确认内容。年龄分为 6–8 岁、9–12 岁，支持亲子共玩及 8 / 12 / 16 / 20 页。

当前开发版本为 **2.0.0-alpha.2**。已经接入本机 Claude Code 配置中的 GLM，真实模型技术评测持续进行；Mac、Windows、Linux 实际安装包的自动化试玩均已通过。按用户决定，60 本逐本人工检查和 20 组同主题盲评保持待完成，正式发布门禁保持关闭。具体证据见 [验收报告](docs/v2/ACCEPTANCE.md)。

## 开始使用

Mac 解压后运行 `XiongchumoQiyu.app`；Windows 运行包内 `.exe`；Linux 运行 `XiongchumoQiyu.sh`。首版包未签名、公证。三平台测试在各自原生系统中运行实际打包后的应用，测试记录和包散列见 [平台证据](docs/v2/platforms.json)。

本机使用 GLM 时，双击 `tools/run_glm_service.command`，再在游戏中填写终端显示的 `http://127.0.0.1:8001` 和监护人连接码。模型凭据从现有 Claude Code 设置读取，只保留在服务端。完整说明见 [本地 GLM 接入](docs/v2/LOCAL_GLM.md)。

先部署故事服务，再在游戏中选择角色、主题、年龄与长度，输入服务地址及监护人连接码，确认本次联网。凭据过期可以重新连接；断网可以从「我的绘本」继续阅读已有页面。生成失败不会把未经校验的草稿写入故事，保存后可重新连接并重试原行动。

书架保存进行中及完成作品。完成作品可导出单文件 HTML，包含实际页面、选择、亲子理由、结局、字体和图片，支持脱网翻页与方向键回看。重玩创建新故事。

## 部署服务

Python 3.12；单实例、单工作进程、SQLite WAL。长期模型凭据仅在服务端配置。

```sh
cp .env.example .env
# 编辑 .env：实际 chat/completions 地址、模型、密钥、监护人连接码及费率
# .env 不进入 Git、镜像或客户端
docker compose up --build -d
```

默认仅开放 `127.0.0.1:8000`。外网部署须用自己的 HTTPS 入口接入；客户端仅对 localhost / 127.0.0.1 / ::1 放行开发 HTTP。连接码至少八个字符；访问令牌有效一小时，按本地账户授权。SQLite 使用持久卷。模型失败不会切换成模拟故事。

不用 Docker 时：

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r service/requirements.txt
# 将 .env 配置设置为当前进程环境变量，再运行：
.venv/bin/uvicorn service.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

配置说明及完整请求协议见 [实现说明](docs/v2/IMPLEMENTATION.md) 和 [OpenAPI](docs/v2/openapi.json)。默认每本上限 120 次调用 / 700000 token；费用上限可设。正费用上限需要实际输入及输出费率。GLM Coding 套餐实际收费金额未知，不能当成零费用。

开发演示须显式设置 `XCMQY_DEVELOPMENT_MOCK=1`，与实际 LLM 使用分开。例如：

```sh
XCMQY_DEVELOPMENT_MOCK=1 XCMQY_GUARDIAN_CODE=local-dev-guardian .venv/bin/uvicorn service.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

演示时在游戏中填写 `http://127.0.0.1:8000` 与连接码 `local-dev-guardian`。页面明确标注开发模拟。演示连接码应另外配置，不要沿用生产连接码。

现成 ARM64 服务镜像随交付提供；其他服务器架构使用部署源码构建。可 `docker load -i dist/2.0.0-alpha.1-final/StoryService-image.tar.gz` 后以 `.env` 配置运行；该镜像没有内置模型密钥或连接码。默认 Python 基础镜像在本机拉取曾因 registry 网络超时失败，本次成功构建使用官方 `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`，也可通过 Dockerfile 的 `PYTHON_IMAGE` 构建参数指定。

## 开发与验收

```sh
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
python3 tools/test_core_logic.py
python3 tools/check_project.py
tools/run_renpy_lint.sh
tools/run_book_qa.sh
# 后两项需要 Ren’Py 8.5.2；绘本 QA 需要 localhost:8000 的显式模拟服务
# QA 使用独立账户和临时存档
```

真实模型配置可用后，执行标准长度评测并填写逐本人工表；中断后用同一输出目录恢复，不覆盖已有人工评分：

```sh
XCMQY_LLM_BACKEND=glm-local XCMQY_LLM_MODEL=glm-5.3 \
.venv/bin/python tools/evaluate_books.py --mode live --pages 12 --output docs/v2/acceptance-evaluation --workers 4
# 60 本：六种结构 × 两档年龄 × 每组五个主题，其中36本采用新主题
.venv/bin/python tools/technical_gate_v2.py
# 下项还要求人工逐本检查、20组评分和费用证据，当前应保持不通过
.venv/bin/python tools/release_gate_v2.py
```

20 组对照必须准备两版实际同主题作品，组织者保管版本映射。审阅者独立填写 40 份匿名作品评分，然后解盲：

```sh
python3 tools/prepare_blind_review.py prepare pairs.json .local/blind-review
python3 tools/prepare_blind_review.py decode .local/blind-review docs/v2/comparison-review.csv
```

[发布门禁](docs/v2/release-gate.json) 不满足全部要求会退出失败；生成源码与安装包成功不等于故事质量通过。

## 工程与素材

- `game/book_v2.rpy`：页式客户端、五类互动、自由表达、恢复与书架。
- `game/storybook/`：客户端和服务共享的状态规则、画面布局、HTML 导出及结局回顾。
- `service/`：类型协议、模型适配、规划 / 提案 / 审校管线、持久任务队列与 API。
- `game/images/v2/`：运行素材；`asset_manifest.json` 按稳定 ID 登记。
- `assets-source/v2/`：风格规范、生成提示、参考图记录、编码验证；原始 PNG 在本地 `raw/`，独立交付。
- `docs/v2/`：测试证据、评测集、部署与候选版验收说明。

素材覆盖 18 场景、9 角色各 6 姿态 / 表情、36 道具、12 情境插图。运行时选择预制素材；不生成图片。WebP 为无损编码，经逐像素 RGBA 比较；角色和道具保留真实透明背景。

旧账户、成就与完成图鉴保留并做 schema 迁移。旧进行中存档保留原件，经旧剧情入口继续；2.0 原生存档使用独立页码，绘本 JSON 按账户隔离。保留 `dist/1.1.0-rc.1/` 可退回旧版；不要把新蓝图从残缺的旧对话历史中编造出来。
