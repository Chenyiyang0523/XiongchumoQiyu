# 本地 Claude Code 的 GLM 接入

Mac 双击 `tools/run_glm_service.command`。脚本使用项目 Python 环境，读取当前用户 `~/.claude/settings.json` 中的 GLM 配置，默认模型 `glm-5.3`，数据库 `.local/glm/player.sqlite`。终端显示服务地址 `http://127.0.0.1:8001` 和监护人连接码；在游戏 2.0 连接页面填写这两项即可。短期令牌由服务签发。

也可在仓库根目录运行：

```sh
XCMQY_LLM_BACKEND=glm-local XCMQY_LLM_MODEL=glm-5.3 \
XCMQY_GUARDIAN_CODE='你的私有连接码' XCMQY_MODEL_TIMEOUT=240 \
XCMQY_BOOK_TOKEN_LIMIT=700000 \
.venv/bin/python -m uvicorn service.app:create_app --factory --host 127.0.0.1 --port 8001
```

`glm-local` 从 Claude Code 的设置读取凭据和服务商地址，仅支持经过验证的 `open.bigmodel.cn`。模型推理使用同一服务商的 GLM Coding 原生 JSON 接口，避免 Anthropic 工具兼容层将对象错误转为字符串。凭据只存在服务进程内存，不复制到客户端、命令行参数或 Git。没有读取或修改全局 hooks、MCP 或 Claude 会话。

`claude-cli` 适配器也已提供并真实连接成功，适合使用 CLI 输出的环境；它禁用工具、MCP、斜杠命令、Chrome、hooks 和会话持久化，单次仅执行一个模型回合。长故事规划在当前 CLI 上出现过超时，完整技术评测使用 `glm-local`，不能将两种传输混称为全程 CLI 运行。

服务端可通过 `XCMQY_CLAUDE_SETTINGS` 指定另一份配置。Docker 使用此模式时需要将配置文件以只读方式挂载到服务容器，并指定容器中的绝对路径；不要把凭据加入镜像。生产也可使用原有 `openai` 模式，通过服务端环境变量指定准确的兼容接口、模型和密钥。

每次真实调用记录输入 / 输出 token、等待时间、修订次数与计费依据。GLM Coding 套餐接口未返回实际账单金额，金额明确为未知；CLI 的估算费用不能当作 GLM 账单。若部署者提供实际费率，可设置两项 `XCMQY_*_USD_PER_MILLION` 作 token 估算，仍需与服务商账单区分。未知费率时启用正金额预算会暂停，调用和 token 上限始终生效。

使用服务商支持的开启推理模式：普通规划、提案与审校默认low，遇到明确错误的有限修订默认high。可以分别配置 XCMQY_GLM_REASONING_EFFORT 和 XCMQY_GLM_REPAIR_EFFORT，值为low/high/max。不使用该模型已不支持的关闭推理参数。推理内容不展示、不进入作品，评测仅保存用量及最终结构化响应。单次请求超时240秒，每本默认120次调用 / 700000 token，达到预算会保留已确认进度。

真实评测可断点恢复，失败原行动保持不变：

```sh
XCMQY_LLM_BACKEND=glm-local XCMQY_LLM_MODEL=glm-5.3 \
.venv/bin/python tools/evaluate_books.py --mode live \
  --output docs/v2/acceptance-evaluation --workers 2
```

修复后显式添加 `--retry-failed` 重试未提交请求；已完成作品不会重复生成。单次生成 / 修订仍最多四次调用，失败重试的历史用量保留。`--cases case.03,case.08` 可选择小规模试验，完整验收仍要求全部 60 本。人工检查表保留空白，等待实际审阅者填写。

同一主机的 GLM 服务和评测进程默认共用两个请求槽，进程退出后操作系统释放锁。可用 `XCMQY_GLM_CONCURRENCY` 配置 1–4，但所有进程应保持一致；容器与宿主是不同锁域，额外并发仍需控制。HTTP 429、服务端错误或传输中断直接保存为可恢复失败，不执行内容修订；用户重试仍携带原请求。评测应一次运行一组工作进程，避免多个恢复组争用套餐额度。

已保存为待续或达到预算的故事不会改写状态。基准需要重测时，显式使用 `--story-attempt 2` 新建同设定故事，原作品与失败记录仍保留；汇总记录每次故事尝试的用量，不能用新结果隐藏旧失败。
