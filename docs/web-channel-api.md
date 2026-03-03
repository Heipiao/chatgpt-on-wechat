# Web Channel API 协议文档

> 版本: v2.0  
> 更新日期: 2026-03-04  
> 变更摘要: `/poll` 响应新增 `type` 字段；文件类型回复新增 `oss_url` 字段

---

## 1. 概述

Web Channel 通过 HTTP JSON 接口与前端通信，采用 **POST 请求 + 轮询** 模式：

1. 客户端通过 `POST /message` 发送消息，服务端立即返回 `request_id`
2. 客户端通过 `POST /poll` 轮询回复，服务端从 session 队列中取出回复返回

```
Client                          Server
  |  POST /message               |
  |  {session_id, message}       |
  |----------------------------->|
  |  {status, request_id}        |
  |<-----------------------------|
  |                               |  (后台异步处理)
  |  POST /poll                  |
  |  {session_id}                |
  |----------------------------->|
  |  {status, has_content,       |
  |   type, content, oss_url,    |
  |   request_id, timestamp}     |
  |<-----------------------------|
```

---

## 2. 接口定义

### 2.1 POST /message — 发送消息

#### 请求

```json
{
  "session_id": "string  // 会话唯一标识，前端生成",
  "message": "string     // 用户输入的消息文本",
  "timestamp": "string   // ISO 8601 时间戳（可选）"
}
```

#### 成功响应

```json
{
  "status": "success",
  "request_id": "string  // UUID，用于匹配后续的回复"
}
```

#### 错误响应

```json
{
  "status": "error",
  "message": "string  // 错误描述"
}
```

---

### 2.2 POST /poll — 轮询回复

#### 请求

```json
{
  "session_id": "string  // 会话唯一标识"
}
```

#### 成功响应 — 有回复

```json
{
  "status": "success",
  "has_content": true,
  "type": "string         // 回复类型，见下方枚举",
  "content": "string      // 回复内容（文本/URL/文件路径等）",
  "oss_url": "string|null // 文件类型时的 OSS 访问地址，非文件类型为 null",
  "request_id": "string   // 对应请求的 UUID",
  "timestamp": 1709560800.123
}
```

#### 成功响应 — 暂无回复

```json
{
  "status": "success",
  "has_content": false
}
```

#### 错误响应

```json
{
  "status": "error",
  "message": "string  // 错误描述"
}
```

---

### 2.3 GET /config — 获取前端配置

#### 成功响应

```json
{
  "status": "success",
  "use_agent": true,
  "title": "string   // 页面标题",
  "subtitle": "string // 页面副标题"
}
```

---

## 3. type 字段枚举

| type 值       | 说明             | content 内容            | oss_url        |
|---------------|-----------------|------------------------|----------------|
| `TEXT`        | 纯文本/Markdown  | 文本字符串              | `null`         |
| `TEXT_`       | 强制文本          | 文本字符串              | `null`         |
| `IMAGE`       | 图片文件          | 本地文件路径            | OSS 图片 URL   |
| `IMAGE_URL`   | 图片 URL         | 图片的公网 URL          | `null`         |
| `VIDEO`       | 视频文件          | 本地文件路径            | OSS 视频 URL   |
| `VIDEO_URL`   | 视频 URL         | 视频的公网 URL          | `null`         |
| `FILE`        | 通用文件          | 本地文件路径            | OSS 文件 URL   |
| `INFO`        | 提示信息          | 文本字符串              | `null`         |
| `ERROR`       | 错误信息          | 文本字符串              | `null`         |

> **规则**: 当 `type` 为 `IMAGE`、`VIDEO`、`FILE` 时（即本地文件类型），服务端会将文件上传至 OSS 并在 `oss_url` 字段返回可访问的 URL。  
> 其他类型的 `oss_url` 为 `null`。

### 不支持的类型

以下类型在 Web Channel 中不支持，收到后将被丢弃：

| type 值       | 说明                |
|---------------|---------------------|
| `VOICE`       | 音频文件             |
| `CARD`        | 微信名片（ntchat 专用）|
| `INVITE_ROOM` | 邀请进群             |
| `MINIAPP`     | 小程序               |
| `CARD_MSG`    | 互动卡片消息          |

---

## 4. 轮询策略

| 场景         | 轮询间隔   |
|-------------|-----------|
| 页面可见      | 2 秒      |
| 页面不可见    | 5 秒      |
| 请求出错后    | 3 秒      |

前端通过 `request_id` 匹配请求与回复，找到对应的 loading 占位符并替换为实际内容。

---

## 5. 前端渲染规则

| type                  | 渲染方式                                           |
|-----------------------|---------------------------------------------------|
| `TEXT` / `TEXT_`      | Markdown 渲染（markdown-it）                       |
| `IMAGE` / `IMAGE_URL`| `<img>` 标签；`IMAGE` 使用 `oss_url`，`IMAGE_URL` 使用 `content` |
| `VIDEO` / `VIDEO_URL`| `<video>` 标签；`VIDEO` 使用 `oss_url`，`VIDEO_URL` 使用 `content` |
| `FILE`               | 文件下载链接，使用 `oss_url`                         |
| `INFO`               | 信息提示样式                                        |
| `ERROR`              | 错误提示样式                                        |

---

## 6. CORS 配置

当 `config.json` 中配置了 `web_cors_allow_origin` 时，服务端自动添加 CORS 头：

```
Access-Control-Allow-Origin: <配置值>
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
```

---

## 7. OSS 配置

在 `config.json` 中新增以下配置项：

```json
{
  "oss_access_key_id": "",
  "oss_access_key_secret": "",
  "oss_endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
  "oss_bucket_name": "aihrbp-resumes",
  "oss_tenant_id": 1
}
```

| 配置项                  | 类型     | 必填 | 说明                                    |
|------------------------|---------|------|----------------------------------------|
| `oss_access_key_id`    | string  | 是   | 阿里云 Access Key ID                    |
| `oss_access_key_secret`| string  | 是   | 阿里云 Access Key Secret                |
| `oss_endpoint`         | string  | 是   | OSS Endpoint                           |
| `oss_bucket_name`      | string  | 是   | Bucket 名称，默认 `aihrbp-resumes`       |
| `oss_tenant_id`        | int     | 是   | 租户 ID，与 aihrbp-web 体系对齐           |

### OSS 文件路径规范

与 `aihrbp-web` 统一 Bucket（`aihrbp-resumes`），Web Channel 新增以下 category：

| 路径模式 | 说明 |
|----------|------|
| `{tenant_id}/chat_files/{YYYY-MM-DD}/{uuid}.{ext}` | 聊天产生的通用文件 |
| `{tenant_id}/chat_images/{YYYY-MM-DD}/{uuid}.{ext}` | 聊天产生的图片 |
| `{tenant_id}/chat_videos/{YYYY-MM-DD}/{uuid}.{ext}` | 聊天产生的视频 |

> OSSClient 实现位于 `common_utils/oss/oss_client.py`，参考 aihrbp-web 的 OSSClient 接口风格。
