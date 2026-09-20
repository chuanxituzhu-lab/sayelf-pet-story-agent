# sayelf-pet-story-agent Build 0.1 — Sprint 01 Build Decision Record

## Idea / real task

把已冻结的 Phase 21–26 架构落成可运行的 sayelf-pet-story-agent Build 0.1 最小工程骨架：领域模型、Session/Job 状态机、append-only Event Ledger、Pilot 01 fixture、统一视频 provider adapter、最小测试与启动说明。

## Closest existing projects or capabilities

- [pyeventsourcing/eventsourcing](https://github.com/pyeventsourcing/eventsourcing)：通用 Python 事件溯源能力。
- [Conductor OSS](https://github.com/conductor-oss/conductor)：通用持久化工作流与任务编排。
- [AI-Video-Factory](https://github.com/YangMingZhe34985/AI-Video-Factory)：带 provider adapter、故障隔离和结构化事件记录的视频工厂方向。
- 当前工作区：空目录，没有可复用实现。

## Step 0 decision

**Differentiate**

## Measurable improvement or differentiator

Sprint 01 的最小实现以 Python 标准库为核心，复用本地已有的 ReportLab/Pillow 生成固定 Pilot 01 的展位二维码 PNG/PDF；同时完成固定 Pilot 01 的创建、Session/Job 合法流转、非法迁移拒绝、账本追加、Mock 生成和 Fault 注入；不依赖通用工作流平台、第三方二维码网站或真实视频服务。验收以 `python -m unittest discover -s tests -v`、二维码接口检查和 demo golden path 结果为证据。

## Success measure and required evidence

1. 14 个最小领域对象可实例化并被 fixture 组合。
2. Session 与 Job 的合法迁移成功，非法迁移抛出明确异常且不写入错误状态。
3. Ledger 事件只追加、不提供更新/删除路径，重读后顺序和 payload 保持一致。
4. MockVideoProvider 与 FaultVideoProvider 通过同一 adapter contract；故障可重复注入。
5. 集成测试覆盖 Pilot 01 golden path；README 可让普通用户启动测试和 demo。

## Minimum Core

领域 dataclass、受限状态机、JSONL append-only ledger、provider protocol、Mock/Fault provider、Pilot fixture、一个最小 application service、展位 QR registry、标准库测试；QR PNG/PDF 只属于本地 WebUI 适配层。

## Plugin boundaries (if any)

`VideoProviderAdapter` 是唯一外部视频 provider 边界。Mock/Fault 是本地实现；真实 provider 留给后续 Sprint，不在本 Sprint 注册或调用。

## Local-first boundary

所有状态、fixture、ledger 和测试在本地内存/本地 JSONL 文件完成。Sprint 01 不上传图片、文本、Prompt、日志或用户数据，也不连接云模型或第三方 API。

## Data classification and local trust boundary

固定 fixture 与源代码可视为 `Internal`；未来宠物照片、会话内容、生成资产和运行日志至少是 `Sensitive`。本 Sprint 全部留在本地信任边界。没有任何公开发布或外部传输授权。

## GitHub/public release decision: Allowed | Blocked — review evidence

**Blocked**。没有 GitHub/public 发布请求；未做 staged diff 或 release artifact 公共泄漏审查，因此不推送、不创建 PR、不发布包。

## External transfer plan (if any; local and sensitive data excluded)

N/A。外部搜索只用于 Step 0 方案对比，不传输本地工作区数据。

## State, change signals, and next-check rule

Session/Job 状态变化由显式 command 触发并写入 Ledger。Sprint 01 没有后台轮询；demo 只执行一次 golden path。后续若引入异步 worker，应按状态变化、任务重要性和 provider 回调/错误事件驱动下一次检查。

## Observation / inference / hypothesis / fact boundary

- Observation：provider 返回成功/失败、状态迁移请求和 ledger 中已持久化的事件。
- Inference：由已持久化事件折叠得到的当前状态。
- Hypothesis：Fault provider 可代表真实 provider timeout/unavailable 的测试替身。
- Fact：仅以测试断言和 ledger 内容验证后，才把状态和生成结果视为事实。

## Evolution, validation, canary, version, and rollback plan

版本固定为 `0.1.0`。先跑标准库测试，再跑固定 demo；未来 provider 或状态规则变更必须新增版本化测试并在 Pilot fixture 上 canary。回滚边界是恢复到本次提交/目录版本；ledger 只追加，不通过删除历史事件回滚。

## WebUI decision: Required — reason

用户明确提出 WebUI 需求，因此保留普通用户体验页，同时增加职责单一的后台二维码控制台。游客页保持 Open → Input → Execute → Result；后台页保持 Open → Select → Generate → Download → Status。语言切换、Logo、二维码生成与下载、二维码状态均在本地浏览器完成。

## Default WebUI path (if required)

后台：Open `/admin.html` → choose event/exhibitor/booth → generate → download PNG/PDF → view status；游客：Open `/` → scan the distributed QR → verify session → enter text/image in one composer → execute local demo → view result and Prompt Board。

## Simplest reliable implementation

Python 3.11+ 标准库、`src/` package layout、`unittest`、JSONL ledger、dataclass/Enum/Protocol；不引入数据库、Web 框架、消息队列或真实 provider SDK。

## Explicitly not building

不做 Sprint 02；不做真实视频生成、Prompt 编排、Shot QA、Final Assembly、队列/并发、数据库、真实 Agent 网关、外部服务端文件上传、真实鉴权实现、支付、云存储、外部分享接口、真实大模型 API 调用、API Key 持久化、hall 播放器和 analytics dashboard。二维码接入只做到本地 mock handshake 与真实网关契约；品牌素材上传只属于本机后台，不声称已连接当前 Codex 对话。

## WebUI generation-return addendum

本次用户需求将 WebUI 的最小闭环从“浏览器模拟进度”改善为“本地提交 → 本地渲染 → 当前页面回传”。决策分类为 **Improve**：保留原有普通用户交互，不引入数据库、队列或云 provider，只增加一个本地 generation endpoint、受限的本地 MP4 renderer、幂等键和按访客/日期的额度保护。

- Success evidence：文字请求 `201` 并返回 `video_url` / `download_url`；视频端点返回 `video/mp4`；三张参考图请求返回 `400`；额度与积分规则由新增测试覆盖。
- Data boundary：文字、图片和生成资产留在本机 `.local/`；接口响应不回显原始输入；公开仓库不包含运行时生成文件、访客内容或 API Key。
- Explicit boundary：当前视频是本地 deterministic demo renderer，不声称是真实 AI 视频生成；真实 provider、生产身份、跨设备额度和云端回传继续不做。

## Free allowance, model pricing, and exhibitor branding addendum

本次需求继续分类为 **Improve**：复用本地生成、额度和 QR 控制台，只增加三条可替换规则——免费额度、模型计价与展位品牌层。

- Free grant：每个本地访客按本机日期获得 1 支视频和 2 张输出图片；额外输出从绑定展位的本地积分账户扣减。
- Model boundary：模型目录声明每支视频和每张图片的积分单价；当前两个模型仍调用本地 demo renderer，真实大模型只允许通过既有 provider adapter 接入。
- Brand boundary：QR 后台保存 Logo/展板到本机品牌资产目录；渲染层用 `ImageOps.contain` 和 alpha composite，保持原始宽高比，并在 PNG/MP4 两类输出中复用同一品牌帧。
- Success evidence：免费请求 `credits_charged=0` 且返回 1 个视频地址和 2 个图片地址；积分充值后额外请求按模型扣费；QR 返回 `brand_ready=true`；三张参考图仍被拒绝。
- Explicitly not building：真实支付、充值渠道、生产账户认证、跨设备钱包、云端大模型调用和品牌素材公开发布。
