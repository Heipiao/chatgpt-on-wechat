"""
Agent Initializer - Handles agent initialization logic
"""

import os
import asyncio
import datetime
import hashlib
import shutil
import time
from typing import Any, Dict, List, Optional

from agent.protocol import Agent
from agent.tools import ToolManager
from common.log import logger
from common.utils import expand_path


class AgentInitializer:
    """
    Handles agent initialization including:
    - Workspace setup
    - Memory system initialization  
    - Tool loading
    - System prompt building
    """
    
    def __init__(self, bridge, agent_bridge):
        """
        Initialize agent initializer
        
        Args:
            bridge: COW bridge instance
            agent_bridge: AgentBridge instance (for create_agent method)
        """
        self.bridge = bridge
        self.agent_bridge = agent_bridge
    
    def initialize_agent(
        self,
        session_id: Optional[str] = None,
        runtime_config: Optional[Dict[str, Any]] = None,
    ) -> Agent:
        """
        Initialize agent for a session
        
        Args:
            session_id: Session ID (None for default agent)
        
        Returns:
            Initialized agent instance
        """
        from config import conf
        
        # Get workspace from config
        workspace_root = expand_path(conf().get("agent_workspace", "~/cow"))
        
        # Migrate API keys
        self._migrate_config_to_env(workspace_root)
        
        # Load environment variables
        self._load_env_file()
        
        # Initialize workspace
        from agent.prompt import ensure_workspace, load_context_files, PromptBuilder
        workspace_files = ensure_workspace(workspace_root, create_templates=True)
        
        if session_id is None:
            logger.info(f"[AgentInitializer] Workspace initialized at: {workspace_root}")
        
        # Setup memory system
        memory_manager, memory_tools = self._setup_memory_system(workspace_root, session_id)
        
        # Load tools
        tools = self._load_tools(workspace_root, memory_manager, memory_tools, session_id)
        
        # Initialize scheduler if needed
        self._initialize_scheduler(tools, session_id)
        
        # Load context files
        context_files = load_context_files(workspace_root)
        context_files = self._merge_runtime_context_files(context_files, runtime_config)
        
        # Initialize skill manager
        skill_manager = self._initialize_skill_manager(workspace_root, session_id, runtime_config)
        
        # Check if first conversation
        from agent.prompt.workspace import is_first_conversation, mark_conversation_started
        is_first = is_first_conversation(workspace_root)
        
        # Build system prompt
        prompt_builder = PromptBuilder(workspace_dir=workspace_root, language="zh")
        runtime_info = self._get_runtime_info(workspace_root, runtime_config=runtime_config)
        
        system_prompt = prompt_builder.build(
            tools=tools,
            context_files=context_files,
            skill_manager=skill_manager,
            memory_manager=memory_manager,
            runtime_info=runtime_info,
            is_first_conversation=is_first
        )
        
        if is_first:
            mark_conversation_started(workspace_root)
        
        # Get cost control parameters
        from config import conf
        max_steps = conf().get("agent_max_steps", 20)
        max_context_tokens = conf().get("agent_max_context_tokens", 50000)
        
        # Create agent
        agent = self.agent_bridge.create_agent(
            system_prompt=system_prompt,
            tools=tools,
            max_steps=max_steps,
            output_mode="logger",
            workspace_dir=workspace_root,
            skill_manager=skill_manager,
            enable_skills=True,
            max_context_tokens=max_context_tokens,
            runtime_info=runtime_info,  # Pass runtime_info for dynamic time updates
            model_name=self._get_runtime_model_name(runtime_config),
        )
        
        # Attach memory manager
        if memory_manager:
            agent.memory_manager = memory_manager
        
        return agent
    
    def _load_env_file(self):
        """Load environment variables from .env file"""
        env_file = expand_path("~/.cow/.env")
        if os.path.exists(env_file):
            try:
                from dotenv import load_dotenv
                load_dotenv(env_file, override=True)
            except ImportError:
                logger.warning("[AgentInitializer] python-dotenv not installed")
            except Exception as e:
                logger.warning(f"[AgentInitializer] Failed to load .env file: {e}")
    
    def _setup_memory_system(self, workspace_root: str, session_id: Optional[str] = None):
        """
        Setup memory system
        
        Returns:
            (memory_manager, memory_tools) tuple
        """
        memory_manager = None
        memory_tools = []
        
        try:
            from agent.memory import MemoryManager, MemoryConfig, create_embedding_provider
            from agent.tools import MemorySearchTool, MemoryGetTool
            from config import conf
            
            # Get OpenAI config
            openai_api_key = conf().get("open_ai_api_key", "")
            openai_api_base = conf().get("open_ai_api_base", "")
            
            # Initialize embedding provider
            embedding_provider = None
            if openai_api_key and openai_api_key not in ["", "YOUR API KEY", "YOUR_API_KEY"]:
                try:
                    embedding_provider = create_embedding_provider(
                        provider="openai",
                        model="text-embedding-3-small",
                        api_key=openai_api_key,
                        api_base=openai_api_base or "https://api.openai.com/v1"
                    )
                    if session_id is None:
                        logger.info("[AgentInitializer] OpenAI embedding initialized")
                except Exception as e:
                    logger.warning(f"[AgentInitializer] OpenAI embedding failed: {e}")
            
            # Create memory manager
            memory_config = MemoryConfig(workspace_root=workspace_root)
            memory_manager = MemoryManager(memory_config, embedding_provider=embedding_provider)
            
            # Sync memory
            self._sync_memory(memory_manager, session_id)
            
            # Create memory tools
            memory_tools = [
                MemorySearchTool(memory_manager),
                MemoryGetTool(memory_manager)
            ]
            
            if session_id is None:
                logger.info("[AgentInitializer] Memory system initialized")
        
        except Exception as e:
            logger.warning(f"[AgentInitializer] Memory system not available: {e}")
        
        return memory_manager, memory_tools
    
    def _sync_memory(self, memory_manager, session_id: Optional[str] = None):
        """Sync memory database"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Event loop is closed")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            if loop.is_running():
                asyncio.create_task(memory_manager.sync())
            else:
                loop.run_until_complete(memory_manager.sync())
        except Exception as e:
            logger.warning(f"[AgentInitializer] Memory sync failed: {e}")
    
    def _load_tools(self, workspace_root: str, memory_manager, memory_tools: List, session_id: Optional[str] = None):
        """Load all tools"""
        tool_manager = ToolManager()
        tool_manager.load_tools()
        
        tools = []
        file_config = {
            "cwd": workspace_root,
            "memory_manager": memory_manager
        } if memory_manager else {"cwd": workspace_root}
        
        for tool_name in tool_manager.tool_classes.keys():
            try:
                # Skip web_search if no API key is available
                if tool_name == "web_search":
                    from agent.tools.web_search.web_search import WebSearch
                    if not WebSearch.is_available():
                        logger.debug("[AgentInitializer] WebSearch skipped - no BOCHA_API_KEY or LINKAI_API_KEY")
                        continue

                # Special handling for EnvConfig tool
                if tool_name == "env_config":
                    from agent.tools import EnvConfig
                    tool = EnvConfig({"agent_bridge": self.agent_bridge})
                else:
                    tool = tool_manager.create_tool(tool_name)

                if tool:
                    # Apply workspace config to file operation tools
                    if tool_name in ['read', 'write', 'edit', 'bash', 'grep', 'find', 'ls']:
                        tool.config = file_config
                        tool.cwd = file_config.get("cwd", getattr(tool, 'cwd', None))
                        if 'memory_manager' in file_config:
                            tool.memory_manager = file_config['memory_manager']
                    tools.append(tool)
            except Exception as e:
                logger.warning(f"[AgentInitializer] Failed to load tool {tool_name}: {e}")
        
        # Add memory tools
        if memory_tools:
            tools.extend(memory_tools)
            if session_id is None:
                logger.info(f"[AgentInitializer] Added {len(memory_tools)} memory tools")
        
        if session_id is None:
            logger.info(f"[AgentInitializer] Loaded {len(tools)} tools: {[t.name for t in tools]}")
        
        return tools
    
    def _initialize_scheduler(self, tools: List, session_id: Optional[str] = None):
        """Initialize scheduler service if needed"""
        if not self.agent_bridge.scheduler_initialized:
            try:
                from agent.tools.scheduler.integration import init_scheduler
                if init_scheduler(self.agent_bridge):
                    self.agent_bridge.scheduler_initialized = True
                    if session_id is None:
                        logger.info("[AgentInitializer] Scheduler service initialized")
            except Exception as e:
                logger.warning(f"[AgentInitializer] Failed to initialize scheduler: {e}")
        
        # Inject scheduler dependencies
        if self.agent_bridge.scheduler_initialized:
            try:
                from agent.tools.scheduler.integration import get_task_store, get_scheduler_service
                from agent.tools import SchedulerTool
                from config import conf
                
                task_store = get_task_store()
                scheduler_service = get_scheduler_service()
                
                for tool in tools:
                    if isinstance(tool, SchedulerTool):
                        tool.task_store = task_store
                        tool.scheduler_service = scheduler_service
                        if not tool.config:
                            tool.config = {}
                        tool.config["channel_type"] = conf().get("channel_type", "unknown")
            except Exception as e:
                logger.warning(f"[AgentInitializer] Failed to inject scheduler dependencies: {e}")
    
    def _initialize_skill_manager(
        self,
        workspace_root: str,
        session_id: Optional[str] = None,
        runtime_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize skill manager"""
        try:
            from agent.skills import SkillManager
            disable_local_skills = os.getenv("AIHRBP_DISABLE_LOCAL_SKILLS", "1").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            if runtime_config:
                builtin_dir, custom_dir = self._prepare_runtime_skill_dirs(
                    workspace_root,
                    session_id,
                    runtime_config,
                )
                skill_manager = SkillManager(
                    builtin_dir=builtin_dir,
                    custom_dir=custom_dir,
                )
            elif disable_local_skills:
                builtin_dir, custom_dir = self._prepare_runtime_skill_dirs(
                    workspace_root,
                    session_id,
                    {"name": "no-local-skills", "version": "disabled", "skills": []},
                )
                skill_manager = SkillManager(
                    builtin_dir=builtin_dir,
                    custom_dir=custom_dir,
                )
            else:
                skill_manager = SkillManager(custom_dir=os.path.join(workspace_root, "skills"))
            return skill_manager
        except Exception as e:
            logger.warning(f"[AgentInitializer] Failed to initialize SkillManager: {e}")
            return None
    
    def _get_runtime_info(
        self,
        workspace_root: str,
        runtime_config: Optional[Dict[str, Any]] = None,
    ):
        """Get runtime information with dynamic time support"""
        from config import conf
        
        def get_current_time():
            """Get current time dynamically - called each time system prompt is accessed"""
            now = datetime.datetime.now()
            
            # Get timezone info
            try:
                offset = -time.timezone if not time.daylight else -time.altzone
                hours = offset // 3600
                minutes = (offset % 3600) // 60
                timezone_name = f"UTC{hours:+03d}:{minutes:02d}" if minutes else f"UTC{hours:+03d}"
            except Exception:
                timezone_name = "UTC"
            
            # Chinese weekday mapping
            weekday_map = {
                'Monday': '星期一', 'Tuesday': '星期二', 'Wednesday': '星期三',
                'Thursday': '星期四', 'Friday': '星期五', 'Saturday': '星期六', 'Sunday': '星期日'
            }
            weekday_zh = weekday_map.get(now.strftime("%A"), now.strftime("%A"))
            
            return {
                'time': now.strftime("%Y-%m-%d %H:%M:%S"),
                'weekday': weekday_zh,
                'timezone': timezone_name
            }
        
        return {
            "model": self._get_runtime_model_name(runtime_config) or conf().get("model", "unknown"),
            "workspace": workspace_root,
            "channel": conf().get("channel_type", "unknown"),
            "_get_current_time": get_current_time  # Dynamic time function
        }

    def _merge_runtime_context_files(self, context_files, runtime_config: Optional[Dict[str, Any]] = None):
        if not runtime_config:
            return context_files

        from agent.prompt.builder import ContextFile

        merged_context_files = list(context_files or [])
        system_prompt = (runtime_config.get("system_prompt") or "").strip()
        agent_name = (runtime_config.get("name") or "").strip()
        version = runtime_config.get("version")
        agent_id = runtime_config.get("agent_id")
        tenant_id = runtime_config.get("tenant_id")

        runtime_lines = [
            "以下内容由上游业务系统为当前会话下发，是本次对话必须遵循的 Agent 设定。",
        ]

        if agent_name:
            runtime_lines.append(f"Agent 名称: {agent_name}")
        if agent_id is not None:
            runtime_lines.append(f"Agent ID: {agent_id}")
        if tenant_id is not None:
            runtime_lines.append(f"Tenant ID: {tenant_id}")
        if version:
            runtime_lines.append(f"Runtime 版本: {version}")
        if system_prompt:
            runtime_lines.extend(["", system_prompt])

        merged_context_files.append(
            ContextFile(
                path="AGENT_RUNTIME.md",
                content="\n".join(runtime_lines).strip(),
            )
        )
        return merged_context_files

    def _prepare_runtime_skill_dirs(
        self,
        workspace_root: str,
        session_id: Optional[str],
        runtime_config: Dict[str, Any],
    ):
        runtime_version = self._get_runtime_version(runtime_config)
        session_key = self._build_runtime_session_key(session_id, runtime_config)
        runtime_root = os.path.join(workspace_root, "runtime_agents", session_key, runtime_version)
        builtin_dir = os.path.join(runtime_root, "_builtin_empty")
        custom_dir = os.path.join(runtime_root, "skills")

        os.makedirs(builtin_dir, exist_ok=True)
        os.makedirs(custom_dir, exist_ok=True)
        self._reset_runtime_skill_dir(custom_dir)

        for skill in runtime_config.get("skills") or []:
            skill_name = self._sanitize_runtime_name(skill.get("name") or "skill")
            skill_dir = os.path.join(custom_dir, skill_name)
            os.makedirs(skill_dir, exist_ok=True)
            skill_path = os.path.join(skill_dir, "SKILL.md")
            with open(skill_path, "w", encoding="utf-8") as skill_file:
                skill_file.write(self._render_runtime_skill_markdown(skill))

        return builtin_dir, custom_dir

    def _reset_runtime_skill_dir(self, custom_dir: str):
        for entry in os.listdir(custom_dir):
            entry_path = os.path.join(custom_dir, entry)
            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path)
            else:
                os.remove(entry_path)

    def _render_runtime_skill_markdown(self, skill: Dict[str, Any]) -> str:
        name = (skill.get("name") or "runtime-skill").strip()
        description = (skill.get("description") or name).strip()
        content = (skill.get("content") or "").strip()

        if not content:
            return (
                f"---\nname: {name}\ndescription: {description}\n---\n\n"
                f"{description}\n"
            )

        if not content.startswith("---"):
            return (
                f"---\nname: {name}\ndescription: {description}\n---\n\n"
                f"{content}\n"
            )

        if "description:" not in content:
            parts = content.split("\n", 1)
            if len(parts) == 2:
                return f"{parts[0]}\ndescription: {description}\n{parts[1]}"

        return content

    def _build_runtime_session_key(
        self,
        session_id: Optional[str],
        runtime_config: Dict[str, Any],
    ) -> str:
        raw_key = str(
            session_id
            or runtime_config.get("agent_id")
            or runtime_config.get("name")
            or "default"
        )
        digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:12]
        safe_key = self._sanitize_runtime_name(raw_key)
        return f"{safe_key}-{digest}"

    @staticmethod
    def _sanitize_runtime_name(value: str) -> str:
        sanitized = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in value)
        sanitized = sanitized.strip("-_")
        return sanitized or "runtime"

    @staticmethod
    def _get_runtime_version(runtime_config: Optional[Dict[str, Any]] = None) -> str:
        if not runtime_config:
            return "default"
        version = runtime_config.get("version")
        return str(version) if version is not None else "default"

    @staticmethod
    def _get_runtime_model_name(runtime_config: Optional[Dict[str, Any]] = None) -> Optional[str]:
        if not runtime_config:
            return None
        model_config = runtime_config.get("llm_model_config") or {}
        model_name = model_config.get("model")
        if isinstance(model_name, str) and model_name.strip():
            return model_name.strip()
        return None
    
    def _migrate_config_to_env(self, workspace_root: str):
        """Migrate API keys from config.json to .env file"""
        from config import conf
        
        key_mapping = {
            "open_ai_api_key": "OPENAI_API_KEY",
            "open_ai_api_base": "OPENAI_API_BASE",
            "gemini_api_key": "GEMINI_API_KEY",
            "claude_api_key": "CLAUDE_API_KEY",
            "linkai_api_key": "LINKAI_API_KEY",
        }
        
        env_file = expand_path("~/.cow/.env")
        
        # Read existing env vars
        existing_env_vars = {}
        if os.path.exists(env_file):
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, _ = line.split('=', 1)
                            existing_env_vars[key.strip()] = True
            except Exception as e:
                logger.warning(f"[AgentInitializer] Failed to read .env file: {e}")
        
        # Check which keys need migration
        keys_to_migrate = {}
        for config_key, env_key in key_mapping.items():
            if env_key in existing_env_vars:
                continue
            value = conf().get(config_key, "")
            if value and value.strip():
                keys_to_migrate[env_key] = value.strip()
        
        # Write new keys
        if keys_to_migrate:
            try:
                env_dir = os.path.dirname(env_file)
                if not os.path.exists(env_dir):
                    os.makedirs(env_dir, exist_ok=True)
                if not os.path.exists(env_file):
                    open(env_file, 'a').close()
                
                with open(env_file, 'a', encoding='utf-8') as f:
                    f.write('\n# Auto-migrated from config.json\n')
                    for key, value in keys_to_migrate.items():
                        f.write(f'{key}={value}\n')
                        os.environ[key] = value
                
                logger.info(f"[AgentInitializer] Migrated {len(keys_to_migrate)} API keys to .env: {list(keys_to_migrate.keys())}")
            except Exception as e:
                logger.warning(f"[AgentInitializer] Failed to migrate API keys: {e}")
