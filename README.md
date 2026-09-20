# sayelf-pet-story-agent — Build 0.1 / Sprint 01

Repository: `sayelf-pet-story-agent`
Internal Python package: `sayelf_pet_story_agent`

这是 Phase 21–26 冻结架构的第一段实际工程骨架。它采用本地优先的 Modular Monolith，只实现 Sprint 01 的最小可验收切片。

## 已交付

- `Event / Exhibitor / Product / Campaign / Entry / Session / Pet / Job / Shot / GenerationAttempt / Video / Share / HallPlay / LedgerEvent` 最小数据模型。
- Session 与 Job 状态机，非法迁移会被拒绝且不会改变当前状态。
- 本地 JSONL append-only Event Ledger；只提供追加和读取。
- 固定 `Pet Expo Pilot 01 / HappyPet / Smart Motion Ball / My Pet Movie` fixture，包含 8 个黄金故事镜头。
- 统一 `VideoProviderAdapter` contract、`MockVideoProvider` 和可重复故障注入的 `FaultVideoProvider`。
- 标准库 contract/integration tests 与普通用户可读的 golden path demo。

## 启动

需要 Python 3.11 或更高版本；运行时无第三方依赖。

在仓库根目录执行：

```text
python -m unittest discover -s tests -v
python -m sayelf_pet_story_agent
```

如果尚未安装 package，可使用项目根目录的 `PYTHONPATH` 方式运行：

```text
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m sayelf_pet_story_agent
```

普通用户只需看到测试通过或 `sayelf-pet-story-agent Pilot 01: READY`；JSON、Prompt、provider/API 细节留在内部 contract 和测试中。

## WebUI / HTML 演示

生成完成后，WebUI 会展开 Prompt Board：图片与视频分镜固定保持 8:8 对齐；每张图片 Prompt 有独立复制按钮，视频分镜 Prompt 提供汇总复制按钮。

本地 WebUI 还支持：

- 中英文一键切换，包含状态、分镜 Prompt、弹窗和提示语。
- 使用 webui/assets/sayelf-logo.png 作为 SAYELF Logo。
- 扫码入口与相机/相册图片入口；文件只在浏览器本地处理。
- 扫码后进入会话栏；会话栏只显示接入状态和下一步，不重复承载内容输入。
- `01 / PET INTAKE` 是唯一内容入口：可只填文字、只拍照片，或文字加照片作为同一份宠物输入。
- 未完成扫码验证前隐藏宠物录入步骤；接入成功后展开「拍摄宠物照片」和 `01 / PET INTAKE`。
- 会话接入契约规定短时一次性 join token、服务端验证、幂等消息回执和明确的失败状态。
- 模型 API 接入设置入口；当前只展示配置界面，不保存或发送 API Key，也不调用外部服务。
- 用户提交的文字、单张或最多两张图片会通过本地 WebUI 后端生成 3 秒本地演示 MP4，并回传到当前页面播放和下载；同一访客每天最多成功生成 1 次视频，图片输入累计最多 2 张。

已提供一个不依赖构建工具的单页界面：`webui/index.html`。它展示普通用户的输入、生成进度、8 镜头结果和展位播放授权。`webui/server.py` 提供本地生成接口与视频回传；视频由本地 ffmpeg 演示渲染器生成，不代表已接入真实 AI 视频 provider。

### QR → Agent 会话边界

当前 WebUI 的“模拟扫码接入”用于本地验收完整用户路径。真实扫码不能仅凭前端显示“已连接”：必须由会话网关验证二维码签名、过期时间、一次性 nonce、活动/展位绑定，并返回 `CONNECTED` 后再显示会话输入栏。真实 Agent 网关的请求/响应、统一消息格式和防重放规则见 [`SESSION_CONNECTION_CONTRACT.md`](SESSION_CONNECTION_CONTRACT.md)。

当前页面不会把访客图片或文字发送到外部服务，也不会直接接入当前 Codex 对话；接入真实 Agent 时只替换会话网关适配层，不改变普通用户的会话栏交互。

在仓库根目录执行（包含二维码生成与 PNG/PDF 下载）：

```text
pip install -r requirements-webui.txt
python webui/server.py
```

然后打开 `http://localhost:8080`。

后台二维码控制台为 `http://localhost:8080/admin.html`：可选择活动、参展商和展位，生成本地二维码并下载 PNG / PDF，同时查看二维码状态和历史。后台页不提供“扫码进入”按钮；游客体验页仍为 `http://localhost:8080/`，供手机访问二维码后的会话与宠物录入使用。已生成二维码的状态保存在本地 `webui/.local/`，不会进入公共发布内容。

## 生成回传与额度边界

- 后端只接受本机 WebUI 的生成请求，不把文字、图片或生成文件发送到外部服务。
- `visitor_id` 仅用于本地演示额度记录；换设备或清理本地存储后会产生新的访客标识，生产环境应替换为真实会话身份。
- 额度按本机日期计算：每天 1 次视频；图片输入累计最多 2 张。失败渲染会释放本次额度，成功结果可通过返回的播放地址和下载地址读取。
- 这是可验证的本地 Mock 生成闭环；真实大模型视频质量、云 provider、鉴权和跨设备回传仍未接入。

## 验收边界

本 Sprint 不包含真实视频服务、Prompt 编排、Shot QA、Final Assembly、并发队列、数据库、真实 Agent 网关、云存储、外部分享、hall 播放器和 analytics。这些属于后续冻结阶段，Sprint 01 完成后停止。当前新增的生成回传仍是本地 Mock 闭环，不扩展为真实 provider 或云端生产链路。

详细 Build Decision Record 见 [`BUILD_DECISION_RECORD.md`](BUILD_DECISION_RECORD.md)。
