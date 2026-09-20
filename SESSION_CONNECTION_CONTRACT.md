# Pet FDE Agent Session Connection Contract

## Purpose

二维码用于把现场访客带入一次 Pet FDE Agent 会话。二维码本身不是会话，也不携带宠物图片、输入文字或 API Key；它只携带一个短时、一次性的加入凭证。

当前 Sprint 01 的 WebUI 只实现本地 mock handshake，用于验证用户路径和状态变化。真实 Agent 接入需要由受信任的会话网关实现下面的接口。

## QR payload

推荐使用 HTTPS URL；本地演示也接受 `petfde://join`：

```text
https://agent.example/join?event=event-pilot-01&booth=A17&join_token=<opaque>&exp=<unix>&nonce=<opaque>&sig=<signature>
```

约束：

- `join_token`、`nonce` 和 `sig` 必须是服务端生成的 opaque 值；二维码不放原始 Prompt、图片地址、用户隐私或 API Key。
- `exp` 必须是短期过期时间；服务端还要记录 nonce/token 的一次性使用状态，防止截图转发和重放。
- 事件、展位和活动绑定在服务端签名内容中，客户端不能自行修改后继续使用。

## Join handshake

```text
POST /api/sessions/join
Content-Type: application/json
Idempotency-Key: <device-join-attempt>

{
  "join_token": "<opaque>",
  "device_nonce": "<new-client-value>",
  "client_version": "pet-fde-webui-0.1"
}
```

成功响应：

```json
{
  "session_id": "sess_...",
  "conversation_id": "conv_...",
  "status": "CONNECTED",
  "expires_at": 1770000000,
  "capabilities": {
    "text": true,
    "image": true,
    "multipart_message": true
  }
}
```

服务端必须在返回 `CONNECTED` 前校验：签名、过期时间、一次性 nonce、活动/展位绑定、设备速率限制和会话幂等键。失败时返回明确状态，例如 `TOKEN_EXPIRED`、`TOKEN_REPLAYED`、`TOKEN_INVALID` 或 `EVENT_MISMATCH`；前端只能进入失败态，不能展示“已连接”。

## Unified message

文字、图片、图片加文字都是同一个消息资源。推荐使用 multipart：

```text
POST /api/sessions/{session_id}/messages
Content-Type: multipart/form-data
Idempotency-Key: <message_id>

message_id: msg_...
text: optional
image: optional
content_type: image/jpeg | image/png | image/webp
```

至少有 `text` 或 `image` 一个字段；两个字段同时存在时仍只创建一条消息。服务端返回带 `message_id` 的明确 ack，客户端收到 ack 前保持 `SENDING`，超时只按同一个幂等键重试，避免重复消息。

## User-visible state machine

```text
QR_SCANNED
  -> VERIFYING
  -> CONNECTED
  -> READY_TO_SEND
  -> SENDING
  -> SENT
```

异常分支：

```text
VERIFYING -> EXPIRED / REJECTED / OFFLINE
SENDING   -> RETRYABLE_ERROR / REJECTED
```

普通用户只看到“正在验证、已接入、发送成功、二维码已过期”等结果；`session_id`、Prompt、provider 和 API 细节留在内部日志或开发面板。

## Current implementation boundary

当前页面使用本地 mock handshake；接入成功后由 `01 / PET INTAKE` 产生唯一的宠物输入，不上传文件、不调用外部 Agent、不声称已经接入当前 Codex 对话。要接入真实 Agent，需要把这份合并后的 intake payload 通过受 HTTPS 保护的会话网关提交，并让网关持有 Agent runtime 的 `conversation_id` 映射。
