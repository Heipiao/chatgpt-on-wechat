import os
import re
import logging
import uuid
from datetime import datetime
import oss2
from config import conf

logger = logging.getLogger(__name__)

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
