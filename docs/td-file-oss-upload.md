# TD: Web Channel 文件类型 OSS 上传

> 作者: —  
> 日期: 2026-03-04  
> 状态: Draft

---

## 1. 背景

当前 Web Channel 的 `/poll` 接口在返回回复时不传递 `type` 字段，前端无法区分回复类型。对于文件类型（`FILE`、`IMAGE`、`VIDEO`），`reply.content` 是服务端本地文件路径，前端无法直接访问。

需要：
1. `/poll` 响应中新增 `type` 字段
2. 文件类型回复上传至 OSS，返回可公网访问的 `oss_url`

---

## 2. 目标

- `/poll` 接口返回 `type`，前端可根据类型差异化渲染
- `FILE`、`IMAGE`、`VIDEO` 三种本地文件类型自动上传至阿里云 OSS
- 上传异步执行，不阻塞主回复流程
- OSS 配置集中管理，通过 `config.json` 配置
- OSS 模块放置在 `common_utils/oss/` 下，与 `aihrbp-web` 的 OSSClient 保持一致的接口风格
- Bucket 及文件夹命名遵循 `aihrbp-web` 已有规范

---

## 3. 整体方案

### 3.1 架构图

```
                        send(reply, context)
                              │
                              ▼
                   ┌─────────────────────┐
                   │  reply.type 是否为   │
                   │  FILE/IMAGE/VIDEO?  │
                   └────┬───────────┬────┘
                        │ Yes       │ No
                        ▼           ▼
              ┌──────────────┐   直接入队
              │ OSSClient    │   (oss_url=null)
              │ upload_file  │
              └──────┬───────┘
                     │
                     ▼
              拿到 oss_url
              连同 type 一起入队
                     │
                     ▼
              ┌──────────────┐
              │ session 队列  │
              └──────┬───────┘
                     │
                     ▼  (poll)
              ┌──────────────────────┐
              │ 返回 JSON 含          │
              │ type, content,       │
              │ oss_url, request_id, │
              │ timestamp            │
              └──────────────────────┘
```

### 3.2 变更范围

| 模块/文件 | 变更内容 |
|----------|---------|
| `config.json` | 新增 OSS 配置项 |
| `config.py` | 新增 OSS 配置读取 |
| `common_utils/oss/__init__.py` | **新建** — 模块初始化 |
| `common_utils/oss/oss_client.py` | **新建** — OSSClient 封装，参考 aihrbp-web |
| `channel/web/web_channel.py` | `send()` 增加文件类型判断与 OSS 上传；`poll_response()` 返回 `type` 和 `oss_url` |
| `channel/web/chat.html` | 前端根据 `type` 差异化渲染 |
| `requirements.txt` | 新增 `oss2` 依赖 |

---

## 4. OSS Bucket 与文件夹命名规范

### 4.1 Bucket

与 `aihrbp-web` 复用同一 Bucket：**`aihrbp-resumes`**。

> 统一 Bucket 便于后续跨系统文件引用和权限管理。

### 4.2 文件路径规范

遵循 `aihrbp-web` 的分层结构，增加日期目录便于按天归档和清理：

```
{tenant_id}/{category}/{YYYY-MM-DD}/{uuid}.{ext}
```

Web Channel 场景下的路径映射：

| 路径模式 | 说明 |
|----------|------|
| `{tenant_id}/chat_files/{YYYY-MM-DD}/{uuid}.{ext}` | 聊天产生的通用文件 |
| `{tenant_id}/chat_images/{YYYY-MM-DD}/{uuid}.{ext}` | 聊天产生的图片 |
| `{tenant_id}/chat_videos/{YYYY-MM-DD}/{uuid}.{ext}` | 聊天产生的视频 |

**字段解释：**

| 字段 | 来源 | 说明 |
|------|------|------|
| `tenant_id` | `config.json` 中的 `oss_tenant_id` | 租户 ID，与 aihrbp-web 体系对齐 |
| `category` | 由 `ReplyType` 自动映射 | `FILE→chat_files`，`IMAGE→chat_images`，`VIDEO→chat_videos` |
| `YYYY-MM-DD` | `datetime.now().strftime("%Y-%m-%d")` | 上传日期，按天分目录 |
| `uuid` | `uuid.uuid4().hex[:8]` | 8 位唯一标识，避免文件名冲突 |
| `ext` | 从原始文件名提取 | 保留原始扩展名 |

**完整路径示例：**

```
aihrbp-resumes/                                        ← Bucket
  └── 1/                                               ← tenant_id
      ├── resumes/                                     ← aihrbp-web 已有
      │   └── a1b2c3d4.pdf
      ├── ocr_results/                                 ← aihrbp-web 已有
      │   └── task_001.json
      ├── llm_results/                                 ← aihrbp-web 已有
      │   └── task_001.json
      ├── chat_files/                                  ← 本次新增
      │   └── 2026-03-04/
      │       └── e5f6a7b8.xlsx
      ├── chat_images/                                 ← 本次新增
      │   └── 2026-03-04/
      │       └── c9d0e1f2.png
      └── chat_videos/                                 ← 本次新增
          └── 2026-03-04/
              └── 1a2b3c4d.mp4
```

---

## 5. 详细设计

### 5.1 OSS 配置 (config.json)

```json
{
  "oss_access_key_id": "",
  "oss_access_key_secret": "",
  "oss_endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
  "oss_bucket_name": "aihrbp-resumes",
  "oss_tenant_id": 1
}
```

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `oss_access_key_id` | string | 是 | 阿里云 Access Key ID |
| `oss_access_key_secret` | string | 是 | 阿里云 Access Key Secret |
| `oss_endpoint` | string | 是 | OSS Endpoint |
| `oss_bucket_name` | string | 是 | Bucket 名称，默认 `aihrbp-resumes` |
| `oss_tenant_id` | int | 是 | 租户 ID，与 aihrbp-web 体系对齐 |

### 5.2 OSSClient (common_utils/oss/oss_client.py)

参考 `aihrbp-web/backend/app/utils/oss/oss_client.py`，适配 chatgpt-on-wechat 的配置体系：

```python
import os
import re
import logging
import uuid
from datetime import datetime
import oss2
from config import conf

logger = logging.getLogger(__name__)

# ReplyType → OSS category 映射
REPLY_TYPE_CATEGORY_MAP = {
    "FILE": "chat_files",
    "IMAGE": "chat_images",
    "VIDEO": "chat_videos",
}


class OSSClient:
    """阿里云 OSS 封装（参考 aihrbp-web OSSClient）"""

    def __init__(self):
        self.auth = oss2.Auth(
            conf().get("oss_access_key_id", ""),
            conf().get("oss_access_key_secret", ""),
        )
        self.bucket = oss2.Bucket(
            self.auth,
            conf().get("oss_endpoint", ""),
            conf().get("oss_bucket_name", "aihrbp-resumes"),
        )

    @staticmethod
    def _sanitize_file_name(file_name: str) -> str:
        """清理文件名，仅保留安全字符"""
        base_name = os.path.basename((file_name or "").strip())
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", base_name)
        return safe_name or "file"

    def build_upload_key(self, reply_type: str, file_name: str) -> str:
        """
        构建 OSS 对象 Key。

        路径格式: {tenant_id}/{category}/{YYYY-MM-DD}/{uuid}.{ext}

        Args:
            reply_type: ReplyType 的 name，如 "FILE", "IMAGE", "VIDEO"
            file_name: 原始文件名

        Returns:
            OSS object key
        """
        tenant_id = conf().get("oss_tenant_id", 1)
        category = REPLY_TYPE_CATEGORY_MAP.get(reply_type, "chat_files")
        date_dir = datetime.now().strftime("%Y-%m-%d")

        ext = os.path.splitext(self._sanitize_file_name(file_name))[1]
        unique_name = f"{uuid.uuid4().hex[:8]}{ext}"

        return f"{tenant_id}/{category}/{date_dir}/{unique_name}"

    def upload_file(self, oss_key: str, local_path: str) -> str:
        """上传本地文件到 OSS"""
        self.bucket.put_object_from_file(oss_key, local_path)
        logger.info(f"[OSSClient] Uploaded local file: {local_path} -> {oss_key}")
        return oss_key

    def upload_bytes(self, oss_key: str, data: bytes, content_type: str = None) -> str:
        """上传二进制数据到 OSS"""
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        self.bucket.put_object(oss_key, data, headers=headers)
        logger.info(f"[OSSClient] Uploaded bytes -> {oss_key}")
        return oss_key

    def get_file_url(self, oss_key: str) -> str:
        """生成 OSS 文件的公网 URL"""
        endpoint = conf().get("oss_endpoint", "").replace("https://", "").replace("http://", "")
        bucket_name = conf().get("oss_bucket_name", "")
        return f"https://{bucket_name}.{endpoint}/{oss_key}"

    def get_signed_url(self, oss_key: str, expires: int = 3600) -> str:
        """生成带签名的临时访问 URL"""
        return self.bucket.sign_url("GET", oss_key, expires)

    def delete_file(self, oss_key: str):
        """删除 OSS 文件"""
        self.bucket.delete_object(oss_key)
        logger.info(f"[OSSClient] Deleted: {oss_key}")

    def file_exists(self, oss_key: str) -> bool:
        """检查文件是否存在"""
        return self.bucket.object_exists(oss_key)
```

### 5.3 模块初始化 (common_utils/oss/\_\_init\_\_.py)

```python
from .oss_client import OSSClient

__all__ = ["OSSClient"]
```

另需创建 `common_utils/__init__.py`（空文件）。

### 5.4 web_channel.py send() 改造

```python
from bridge.reply import ReplyType
from io import IOBase

FILE_REPLY_TYPES = {ReplyType.FILE, ReplyType.IMAGE, ReplyType.VIDEO}

def send(self, reply: Reply, context: Context):
    try:
        if reply.type in self.NOT_SUPPORT_REPLYTYPE:
            logger.warning(f"Web channel doesn't support {reply.type} yet")
            return

        if reply.type == ReplyType.IMAGE_URL:
            time.sleep(0.5)

        request_id = context.get("request_id", None)
        if not request_id:
            logger.error("No request_id found in context")
            return

        session_id = self.request_to_session.get(request_id)
        if not session_id:
            logger.error(f"No session_id found for request {request_id}")
            return

        # 文件类型：上传 OSS
        oss_url = None
        if reply.type in FILE_REPLY_TYPES:
            try:
                oss_url = self._upload_to_oss(reply)
            except Exception as e:
                logger.error(f"[WebChannel] OSS upload failed: {e}")

        if session_id in self.session_queues:
            response_data = {
                "type": str(reply.type),
                "content": reply.content if isinstance(reply.content, str) else "",
                "oss_url": oss_url,
                "timestamp": time.time(),
                "request_id": request_id,
            }
            self.session_queues[session_id].put(response_data)

    except Exception as e:
        logger.error(f"Error in send method: {e}")


def _upload_to_oss(self, reply: Reply) -> str:
    """将文件类型 reply 上传到 OSS，返回公网 URL"""
    from common_utils.oss import OSSClient

    client = OSSClient()
    content = reply.content
    reply_type_name = reply.type.name  # "FILE" / "IMAGE" / "VIDEO"

    # content 为本地文件路径
    if isinstance(content, str) and os.path.isfile(content):
        file_name = os.path.basename(content)
        oss_key = client.build_upload_key(reply_type_name, file_name)
        client.upload_file(oss_key, content)
        return client.get_file_url(oss_key)

    # content 为 file-like 对象
    if hasattr(content, "read"):
        file_name = getattr(content, "name", "file")
        oss_key = client.build_upload_key(reply_type_name, file_name)
        data = content.read()
        client.upload_bytes(oss_key, data)
        return client.get_file_url(oss_key)

    logger.warning(f"[WebChannel] Cannot upload: unrecognized content type {type(content)}")
    return None
```

### 5.5 poll_response() 改造

```python
def poll_response(self):
    # ... (省略请求解析)
    try:
        response = self.session_queues[session_id].get(block=False)
        return json.dumps({
            "status": "success",
            "has_content": True,
            "type": response["type"],               # 新增
            "content": response["content"],
            "oss_url": response.get("oss_url"),      # 新增
            "request_id": response["request_id"],
            "timestamp": response["timestamp"],
        })
    except Empty:
        return json.dumps({"status": "success", "has_content": False})
```

### 5.6 前端渲染适配 (chat.html)

根据 `type` 字段做差异化处理：

```javascript
function renderReply(data) {
    switch (data.type) {
        case 'TEXT':
        case 'TEXT_':
        case 'INFO':
            return formatMarkdown(data.content);

        case 'IMAGE':
            return `<img src="${data.oss_url}" alt="image" class="chat-image" />`;

        case 'IMAGE_URL':
            return `<img src="${data.content}" alt="image" class="chat-image" />`;

        case 'VIDEO':
            return `<video controls src="${data.oss_url}" class="chat-video"></video>`;

        case 'VIDEO_URL':
            return `<video controls src="${data.content}" class="chat-video"></video>`;

        case 'FILE':
            var fileName = data.content.split('/').pop() || 'download';
            return `<a href="${data.oss_url}" target="_blank" class="file-download">📎 ${fileName}</a>`;

        case 'ERROR':
            return `<div class="error-message">${data.content}</div>`;

        default:
            return formatMarkdown(data.content);
    }
}
```

---

## 6. 目录结构

改造后新增的文件：

```
chatgpt-on-wechat/
├── common_utils/                 ← 新建
│   ├── __init__.py
│   └── oss/
│       ├── __init__.py
│       └── oss_client.py         ← OSSClient 实现
├── common/                       ← 已有，不变
├── channel/
│   └── web/
│       └── web_channel.py        ← 改造
└── config.json                   ← 新增 OSS 配置
```

---

## 7. 依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| `oss2` | >=2.18.0 | 阿里云 OSS Python SDK |

安装：`pip install oss2`

---

## 8. 错误处理

| 场景 | 处理方式 |
|------|---------|
| OSS 配置缺失 | `OSSClient.__init__` 抛异常，`send()` 捕获并 log，`oss_url` 为 `null` |
| 本地文件不存在 | `upload_file` 抛 `oss2.exceptions.OssError`，`send()` 捕获，`oss_url` 为 `null` |
| OSS 网络超时 | `oss2` 抛异常，`send()` 捕获，`oss_url` 为 `null` |
| content 既非路径也非 file-like | `_upload_to_oss` 返回 `None`，log warning |

**核心原则**：OSS 上传失败不应阻断消息回复。失败时 `oss_url` 为 `null`，前端应做降级处理（如显示"文件暂不可用"）。

---

## 9. 测试计划

### 9.1 单元测试

| 测试项 | 输入 | 预期输出 |
|-------|------|---------|
| build_upload_key 路径格式 | `reply_type="FILE"`, `file_name="report.xlsx"` | `1/chat_files/2026-03-04/{uuid}.xlsx` |
| build_upload_key 图片 | `reply_type="IMAGE"`, `file_name="photo.png"` | `1/chat_images/2026-03-04/{uuid}.png` |
| build_upload_key 视频 | `reply_type="VIDEO"`, `file_name="demo.mp4"` | `1/chat_videos/2026-03-04/{uuid}.mp4` |
| _sanitize_file_name | `"我的 文件(1).pdf"` | `_______1_.pdf` |
| 文本类型回复 | `ReplyType.TEXT` | `type="TEXT"`, `oss_url=null` |
| 图片 URL 类型 | `ReplyType.IMAGE_URL` | `type="IMAGE_URL"`, `oss_url=null` |
| 本地文件上传 | `ReplyType.FILE`, content=有效路径 | `type="FILE"`, `oss_url` 为有效 URL |
| file-like 对象 | `ReplyType.IMAGE`, content=BytesIO | `type="IMAGE"`, `oss_url` 为有效 URL |
| OSS 配置缺失 | 未配置 OSS | `oss_url=null`，日志输出错误 |

### 9.2 集成测试

1. 配置有效 OSS 凭证，发送会触发文件回复的请求
2. 验证 `/poll` 返回中包含 `type` 和有效的 `oss_url`
3. 验证 `oss_url` 可通过浏览器直接访问/下载
4. 验证上传文件路径为 `{tenant_id}/chat_files|chat_images|chat_videos/{YYYY-MM-DD}/{uuid}.{ext}`
5. 验证前端正确渲染图片/视频/文件下载链接

### 9.3 异常测试

1. 断开 OSS 网络，验证回复不被阻断，`oss_url` 为 `null`
2. 发送超大文件（>100MB），验证上传超时处理
3. 并发多个文件回复，验证无竞态问题

---

## 10. 里程碑

| 阶段 | 内容 | 预计耗时 |
|------|------|---------|
| P1 | `common_utils/oss/oss_client.py` 实现 + 单元测试 | 0.5d |
| P2 | `web_channel.py` send/poll 改造 | 0.5d |
| P3 | 前端 `chat.html` 类型渲染适配 | 0.5d |
| P4 | 集成测试 + 异常测试 | 0.5d |

---

## 11. 后续扩展

- **Signed URL 模式**: 当前使用公网 URL，后续可切换为 `get_signed_url` 生成临时 URL，Bucket 设为私有读写
- **OSS 供应商扩展**: 通过配置扩展支持 AWS S3、MinIO 等
- **文件大小限制**: 可配置最大上传文件大小（参考 aihrbp-web 的 50MB 限制）
- **文件类型白名单**: 限制可上传的文件类型
- **文件过期清理**: 通过 OSS Lifecycle 规则自动清理历史文件（参考 aihrbp-web 7 天清理策略）
- **上传进度回调**: 大文件上传时向前端推送进度
