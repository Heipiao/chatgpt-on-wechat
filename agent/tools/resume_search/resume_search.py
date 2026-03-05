"""
Resume Search tool - Search and manage candidate resumes via the MCP Candidate Profile Service.
Calls POST /search (ES DSL), GET /candidate/{candidate_id}, POST /update, POST /delete.
Base URL: RESUME_SEARCH_BASE_URL or http://121.199.74.224:8000
"""

import os
from typing import Dict, Any, Optional

import requests

from agent.tools.base_tool import BaseTool, ToolResult
from common.log import logger
from config import conf


DEFAULT_BASE_URL = "http://121.199.74.224:8000"
DEFAULT_TIMEOUT = 30


class ResumeSearch(BaseTool):
    """Tool for searching, viewing, updating, or deleting candidate profiles."""

    name: str = "resume_search"
    description: str = (
        "Search candidate resumes via Elasticsearch DSL, get a resume by candidate_id, "
        "update resume fields, or delete a candidate.\n"
        "\n"
        "For action=search, provide a raw Elasticsearch DSL query body in the 'dsl' parameter. "
        "The tenant_id filter is injected automatically; you do NOT need to include it.\n"
        "Available index fields and types:\n"
        "  text (IK Chinese analyzer): name_full, current_title, current_company, "
        "experience_overview, education_overview, core_summary, doc_text_clean, "
        "projects_overview, achievements_highlights\n"
        "  keyword: candidate_id, gender, location_city, location_country, seniority_level, "
        "processing_status, skills_hard, skills_soft, tools_platforms, industries, functions, "
        "pref_roles, pref_locations, pref_industries, pref_salary\n"
        "  float: years_of_experience\n"
        "  long: created_at, updated_at\n"
        "\n"
        "Example DSL for searching '产品经理' in Beijing with >=5 years experience:\n"
        '{"query":{"bool":{"must":[{"multi_match":{"query":"产品经理",'
        '"fields":["name_full^3","current_title^3","core_summary^2","doc_text_clean"],'
        '"analyzer":"ik_smart"}}],'
        '"filter":[{"term":{"location_city":"北京"}},'
        '{"range":{"years_of_experience":{"gte":5}}}]}},'
        '"size":10,"from":0,'
        '"highlight":{"fields":{"core_summary":{},"current_title":{}}}}'
    )

    params: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "get", "update", "delete"],
                "description": (
                    "search: search resumes via ES DSL query; "
                    "get: get one resume by candidate_id; "
                    "update: update resume fields; "
                    "delete: soft/hard delete a candidate"
                )
            },
            "dsl": {
                "type": "object",
                "description": (
                    "Elasticsearch DSL query body (for action=search). "
                    "Must contain at least a 'query' key. "
                    "tenant_id filter is injected automatically. "
                    "Supports: query, from, size, sort, _source, highlight, aggs, etc."
                )
            },
            "candidate_id": {
                "type": "string",
                "description": "Candidate ID (required for action=get, update, delete)"
            },
            "fields": {
                "type": "object",
                "description": "Fields to update, e.g. {\"summary\": \"...\"} (for action=update)"
            },
            "hard_delete": {
                "type": "boolean",
                "description": "If true, physically delete instead of soft-delete (for action=delete, default false)"
            }
        },
        "required": ["action"]
    }

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._base_url = (
            os.environ.get("RESUME_SEARCH_BASE_URL")
            or self.config.get("base_url")
            or DEFAULT_BASE_URL
        ).rstrip("/")

    def _get_tenant_id(self) -> int:
        return int(conf().get("oss_tenant_id", 1))

    def _get_actor_user_id(self) -> int:
        return int(conf().get("mcp_actor_user_id", 0))

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self._base_url}{path}"
        return requests.request(method, url, timeout=DEFAULT_TIMEOUT, **kwargs)

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        action = (args.get("action") or "").strip().lower()
        if not action:
            return ToolResult.fail("Error: 'action' is required (search, get, update, or delete)")

        try:
            if action == "search":
                return self._do_search(args)
            if action == "get":
                return self._do_get(args)
            if action == "update":
                return self._do_update(args)
            if action == "delete":
                return self._do_delete(args)
            return ToolResult.fail(f"Error: unknown action '{action}'. Use search, get, update, or delete.")
        except requests.Timeout:
            return ToolResult.fail(f"Error: Request timed out after {DEFAULT_TIMEOUT}s")
        except requests.ConnectionError:
            return ToolResult.fail(f"Error: Cannot connect to resume service at {self._base_url}")
        except Exception as e:
            logger.error(f"[ResumeSearch] Unexpected error: {e}", exc_info=True)
            return ToolResult.fail(f"Error: {str(e)}")

    def _do_search(self, args: Dict[str, Any]) -> ToolResult:
        dsl = args.get("dsl")
        if not isinstance(dsl, dict):
            return ToolResult.fail("Error: 'dsl' must be an object containing an ES query body for action=search")

        payload: Dict[str, Any] = {
            "tenant_id": self._get_tenant_id(),
            "actor_user_id": self._get_actor_user_id(),
            "dsl": dsl,
        }

        resp = self._request("POST", "/search", json=payload)
        if resp.status_code != 200:
            return ToolResult.fail(f"Error: Resume search returned HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()

        hits = data.get("hits") or []
        if hits:
            top = hits[0]
            card = self._build_search_card(top)
            return ToolResult.success({
                "type": "feishu_card",
                "title": f"最佳匹配 - {top.get('name_full', '')}",
                "card": card,
                "search_result": data,
            })
        return ToolResult.success(data)

    def _do_get(self, args: Dict[str, Any]) -> ToolResult:
        candidate_id = (args.get("candidate_id") or "").strip()
        if not candidate_id:
            return ToolResult.fail("Error: 'candidate_id' is required for action=get")
        params = {
            "tenant_id": self._get_tenant_id(),
            "actor_user_id": self._get_actor_user_id(),
        }
        resp = self._request("GET", f"/candidate/{candidate_id}", params=params)
        if resp.status_code == 404:
            return ToolResult.fail(f"Error: Resume not found for candidate_id={candidate_id}")
        if resp.status_code != 200:
            return ToolResult.fail(f"Error: Get resume returned HTTP {resp.status_code}: {resp.text[:200]}")
        return ToolResult.success(resp.json())

    def _do_update(self, args: Dict[str, Any]) -> ToolResult:
        candidate_id = (args.get("candidate_id") or "").strip()
        if not candidate_id:
            return ToolResult.fail("Error: 'candidate_id' is required for action=update")
        fields = args.get("fields")
        if not isinstance(fields, dict):
            return ToolResult.fail("Error: 'fields' must be an object for action=update")
        payload = {
            "tenant_id": self._get_tenant_id(),
            "actor_user_id": self._get_actor_user_id(),
            "candidate_id": candidate_id,
            "fields": fields,
        }
        resp = self._request("POST", "/update", json=payload)
        if resp.status_code == 404:
            return ToolResult.fail(f"Error: Resume not found for candidate_id={candidate_id}")
        if resp.status_code != 200:
            return ToolResult.fail(f"Error: Update returned HTTP {resp.status_code}: {resp.text[:200]}")

        result = resp.json()
        name = fields.get("name_full") or candidate_id
        card = self._build_update_card(name, fields)
        return ToolResult.success({
            "type": "feishu_card",
            "title": f"简历已更新 - {name}",
            "card": card,
            "update_result": result,
        })

    def _do_delete(self, args: Dict[str, Any]) -> ToolResult:
        candidate_id = (args.get("candidate_id") or "").strip()
        if not candidate_id:
            return ToolResult.fail("Error: 'candidate_id' is required for action=delete")
        payload = {
            "tenant_id": self._get_tenant_id(),
            "actor_user_id": self._get_actor_user_id(),
            "candidate_id": candidate_id,
            "hard_delete": bool(args.get("hard_delete", False)),
        }
        resp = self._request("POST", "/delete", json=payload)
        if resp.status_code == 404:
            return ToolResult.fail(f"Error: Resume not found for candidate_id={candidate_id}")
        if resp.status_code != 200:
            return ToolResult.fail(f"Error: Delete returned HTTP {resp.status_code}: {resp.text[:200]}")

        result = resp.json()
        mode = result.get("mode", "soft")
        card = self._build_delete_card(candidate_id, mode)
        return ToolResult.success({
            "type": "feishu_card",
            "title": f"候选人已删除 - {candidate_id}",
            "card": card,
            "delete_result": result,
        })

    @staticmethod
    def _build_search_card(source: Dict[str, Any]) -> dict:
        name = source.get("name_full") or "未知"
        summary = source.get("core_summary") or "暂无摘要"
        tags = source.get("extracted_tags") or "暂无标签"
        url = source.get("url") or ""

        elements = [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**姓名**: {name}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**摘要**: {summary}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**标签**: {tags}"}},
        ]
        if url:
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看详情"},
                    "type": "primary",
                    "url": url,
                }],
            })
        return {
            "header": {
                "title": {"tag": "plain_text", "content": f"最佳匹配 - {name}"},
                "template": "green",
            },
            "elements": elements,
        }

    @staticmethod
    def _build_update_card(name: str, fields: Dict[str, Any]) -> dict:
        elements = []
        for key, value in fields.items():
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**{key}**: {value}"},
            })
        return {
            "header": {
                "title": {"tag": "plain_text", "content": f"简历已更新 - {name}"},
                "template": "blue",
            },
            "elements": elements,
        }

    @staticmethod
    def _build_delete_card(candidate_id: str, mode: str) -> dict:
        mode_label = "物理删除" if mode == "hard" else "软删除"
        elements = [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**候选人ID**: {candidate_id}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**删除方式**: {mode_label}"}},
        ]
        return {
            "header": {
                "title": {"tag": "plain_text", "content": f"候选人已删除 - {candidate_id}"},
                "template": "red",
            },
            "elements": elements,
        }
