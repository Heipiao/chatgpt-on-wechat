import json
import os
import threading
import time
from typing import Any, Optional

from common.log import logger
from config import conf

try:
    import pymysql
except Exception:  # pragma: no cover
    pymysql = None


class WebMessageStore:
    def __init__(self):
        self._table_ready = False
        self._lock = threading.Lock()

    def enabled(self) -> bool:
        if not conf().get("web_message_store_enabled", False):
            return False
        if pymysql is None:
            logger.warning("[WebMessageStore] PyMySQL not installed, store disabled")
            return False
        settings = self._db_settings()
        return all(settings.get(key) for key in ("host", "user", "database"))

    def append_event(
        self,
        *,
        session_id: str,
        request_id: Optional[str],
        tenant_id: Optional[int],
        agent_id: Optional[int],
        actor_user_id: Optional[int],
        role: str,
        sender_type: str,
        message_type: str,
        event_type: str,
        content: Optional[str] = None,
        reply_type: Optional[str] = None,
        oss_url: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        created_at_ms: Optional[int] = None,
    ) -> None:
        if not self.enabled():
            return
        try:
            self._ensure_table()
            conn = self._connect()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO cow_session_event (
                            session_id, request_id, tenant_id, agent_id, actor_user_id,
                            role, sender_type, message_type, event_type,
                            content, reply_type, oss_url, payload_json, created_at
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            session_id,
                            request_id,
                            tenant_id,
                            agent_id,
                            actor_user_id,
                            role,
                            sender_type,
                            message_type,
                            event_type,
                            content,
                            reply_type,
                            oss_url,
                            json.dumps(payload, ensure_ascii=False, default=str) if payload is not None else None,
                            created_at_ms or int(time.time() * 1000),
                        ),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"[WebMessageStore] Failed to append event: {e}")

    def _ensure_table(self) -> None:
        if self._table_ready:
            return
        with self._lock:
            if self._table_ready:
                return
            conn = self._connect()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS cow_session_event (
                            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                            session_id VARCHAR(128) NOT NULL,
                            request_id VARCHAR(128) NULL,
                            tenant_id BIGINT NULL,
                            agent_id BIGINT NULL,
                            actor_user_id BIGINT NULL,
                            role VARCHAR(16) NOT NULL,
                            sender_type VARCHAR(16) NOT NULL,
                            message_type VARCHAR(32) NOT NULL,
                            event_type VARCHAR(32) NOT NULL,
                            content LONGTEXT NULL,
                            reply_type VARCHAR(32) NULL,
                            oss_url VARCHAR(1024) NULL,
                            payload_json JSON NULL,
                            created_at BIGINT NOT NULL,
                            INDEX idx_cow_session_event_session (session_id, created_at),
                            INDEX idx_cow_session_event_request (request_id, created_at),
                            INDEX idx_cow_session_event_actor (tenant_id, actor_user_id, created_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                conn.commit()
                self._table_ready = True
            finally:
                conn.close()

    def _connect(self):
        settings = self._db_settings()
        return pymysql.connect(
            host=settings["host"],
            port=int(settings["port"]),
            user=settings["user"],
            password=settings["password"],
            database=settings["database"],
            charset=settings["charset"],
            autocommit=False,
        )

    @staticmethod
    def _db_settings() -> dict[str, Any]:
        return {
            "host": conf().get("web_message_store_db_host") or os.getenv("DB_HOST"),
            "port": conf().get("web_message_store_db_port", 3306) or int(os.getenv("DB_PORT", "3306")),
            "user": conf().get("web_message_store_db_user") or os.getenv("DB_USER"),
            "password": conf().get("web_message_store_db_password") or os.getenv("DB_PASSWORD", ""),
            "database": conf().get("web_message_store_db_name") or os.getenv("DB_NAME"),
            "charset": "utf8mb4",
        }
