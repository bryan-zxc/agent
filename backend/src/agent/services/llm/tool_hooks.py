"""
Tool hook system for pre and post processing of MCP tool calls.

This module provides a registry for hooks that can modify tool arguments
before execution and tool results after execution. Hooks enable context
injection, response handling, and other cross-cutting concerns without
modifying individual tools.
"""

from typing import Dict, Any, Optional, Callable, Awaitable
from typing import TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from websockets import WebSocket

# Import for database access
from ...models.agent_database import AgentDatabase

logger = logging.getLogger(__name__)


class ToolHooks:
    """Registry for tool pre/post processing hooks.
    
    Pre-hooks can modify tool arguments before execution (e.g., inject context).
    Post-hooks can modify tool results after execution (e.g., send updates).
    """
    
    # Type aliases for hook signatures
    PreHook = Callable[
        [str, Dict[str, Any], Optional[Dict[str, Any]], Optional['WebSocket']], 
        Awaitable[Dict[str, Any]]
    ]
    PostHook = Callable[
        [str, Any, Optional[Dict[str, Any]], Optional['WebSocket']], 
        Awaitable[Any]
    ]
    
    def __init__(self):
        """Initialise hook registry with default hooks."""
        self._pre_hooks: Dict[str, ToolHooks.PreHook] = {}
        self._post_hooks: Dict[str, ToolHooks.PostHook] = {}
        self._register_default_hooks()
    
    def _register_default_hooks(self):
        """Register all default hooks for known tools."""
        # Register hooks for set_plan_and_answer tool
        self._pre_hooks["agent_tools__set_plan_and_answer"] = self._inject_router_id
        self._post_hooks["agent_tools__set_plan_and_answer"] = self._handle_plan_completion

        # Register hooks for execution tools
        self._pre_hooks["agent_tools__execute_python"] = self._inject_router_id
        self._pre_hooks["agent_tools__execute_sql"] = self._inject_router_id
    
    async def apply_pre_hook(
        self, 
        tool_name: str, 
        tool_args: Dict[str, Any], 
        payload: Optional[Dict[str, Any]] = None,
        websocket: Optional['WebSocket'] = None
    ) -> Dict[str, Any]:
        """
        Apply pre-processing hook if registered for the tool.
        
        Args:
            tool_name: Name of the tool being called
            tool_args: Original arguments for the tool
            payload: Optional context data (e.g., router_id)
            websocket: Optional WebSocket connection for updates
        
        Returns:
            Potentially modified tool arguments
        """
        if tool_name in self._pre_hooks:
            try:
                logger.debug(f"Applying pre-hook for {tool_name}")
                return await self._pre_hooks[tool_name](tool_name, tool_args, payload, websocket)
            except Exception as e:
                logger.error(f"Pre-hook failed for {tool_name}: {e}")
                # Return original args if hook fails
                return tool_args
        # Pass through if no hook registered
        return tool_args
    
    async def apply_post_hook(
        self,
        tool_name: str,
        result: Any,
        payload: Optional[Dict[str, Any]] = None,
        websocket: Optional['WebSocket'] = None
    ) -> Any:
        """
        Apply post-processing hook if registered for the tool.
        
        Args:
            tool_name: Name of the tool that was called
            result: Result from the tool execution
            payload: Optional context data
            websocket: Optional WebSocket connection for updates
        
        Returns:
            Potentially modified result
        """
        if tool_name in self._post_hooks:
            try:
                logger.debug(f"Applying post-hook for {tool_name}")
                return await self._post_hooks[tool_name](tool_name, result, payload, websocket)
            except Exception as e:
                logger.error(f"Post-hook failed for {tool_name}: {e}")
                # Return original result if hook fails
                return result
        # Pass through if no hook registered
        return result
    
    # ===== Default Pre-processing Hooks =====
    
    async def _inject_router_id(
        self, 
        tool_name: str, 
        tool_args: Dict[str, Any], 
        payload: Optional[Dict[str, Any]],
        websocket: Optional['WebSocket']
    ) -> Dict[str, Any]:
        """
        Pre-hook: Inject router_id from payload into tool arguments.
        
        This allows the tool to access router context without the LLM
        needing to generate or hallucinate the router_id.
        """
        if payload and "router_id" in payload:
            # Create a copy to avoid mutating original
            tool_args = tool_args.copy()
            tool_args["router_id"] = payload["router_id"]
            logger.info(f"Injected router_id {payload['router_id']} into {tool_name}")
        else:
            logger.warning(f"No router_id in payload for {tool_name}")
        
        return tool_args
    
    # ===== Default Post-processing Hooks =====
    
    async def _handle_plan_completion(
        self,
        tool_name: str,
        result: Any,
        payload: Optional[Dict[str, Any]],
        websocket: Optional['WebSocket']
    ) -> Any:
        """
        Post-hook: Handle plan storage completion and update status.
        
        When set_plan_and_answer completes, this hook updates the router
        status based on whether execution is needed or the answer is complete.
        """
        router_id = payload.get("router_id") if payload else None

        if isinstance(result, str):
            status = None
            mode = None
            agent_phase = None
            router_data = None  # Track router data for approval flow

            # Detect based on content structure, not status text
            if result.startswith("# Execution Plan"):
                # Has todos - needs approval for execution
                status = "awaiting_approval"
                # Keep current mode and phase (stay in agent mode)
                logger.info(f"Execution plan stored for router {router_id}, awaiting approval")
            elif result.startswith("# Answer"):
                # No todos - answer is complete, back to conversation
                # IMPORTANT: Update all three values together as per design
                status = "active"
                mode = "auto"
                agent_phase = None  # Null for auto mode
                logger.info(f"Answer complete for router {router_id}, transitioning to auto mode")

            # Update database and send updates if determined
            if status and router_id:
                # Create database connection for updates
                try:
                    agent_db = await AgentDatabase.create()

                    # Update database with all state values when transitioning to auto
                    if mode == "auto":
                        await agent_db.update_router(
                            router_id=router_id,
                            status=status,
                            mode=mode,
                            agent_phase=agent_phase
                        )
                        logger.info(f"Updated router {router_id} in database: status={status}, mode={mode}, agent_phase={agent_phase}")
                    else:
                        # Just update status for awaiting_approval case
                        logger.info(f"Entering awaiting_approval flow for router {router_id}")
                        await agent_db.update_router(
                            router_id=router_id,
                            status=status
                        )
                        logger.info(f"Updated router {router_id} status to 'awaiting_approval' in database")

                        # Fetch router data to get plan and template for approval_request
                        try:
                            router_data = await agent_db.get_router(router_id)
                            logger.info(f"Successfully fetched router data for {router_id}")
                            logger.debug(f"Router data keys: {list(router_data.keys()) if router_data else 'None'}")
                        except Exception as fetch_error:
                            logger.error(f"Failed to fetch router data for {router_id}: {fetch_error}")
                            router_data = None

                    # Send WebSocket updates
                    if websocket:
                        # Always send status update
                        await websocket.send_json({
                            "type": "status",
                            "router_id": router_id,
                            "status": status
                        })
                        logger.info(f"Sent status update '{status}' for router {router_id}")

                        # Send mode and phase updates when transitioning to auto
                        if mode == "auto":
                            await websocket.send_json({
                                "type": "mode_updated",
                                "mode": mode,
                                "router_id": router_id
                            })
                            logger.info(f"Sent mode update 'auto' for router {router_id}")

                            await websocket.send_json({
                                "type": "phase_updated",
                                "agent_phase": agent_phase,
                                "router_id": router_id
                            })
                            logger.info(f"Sent phase update 'null' for router {router_id}")

                        # Send approval_request when plan needs approval
                        elif status == "awaiting_approval":
                            if router_data:
                                try:
                                    await websocket.send_json({
                                        "type": "approval_request",
                                        "plan": router_data.get("execution_plan", ""),
                                        "template": router_data.get("answer_template", ""),
                                        "router_id": router_id
                                    })
                                    logger.info(f"✓ Sent approval_request for router {router_id}")
                                    logger.debug(f"Approval request - plan length: {len(router_data.get('execution_plan', ''))}, template length: {len(router_data.get('answer_template', ''))}")
                                except Exception as ws_error:
                                    logger.error(f"Failed to send approval_request WebSocket message: {ws_error}")
                            else:
                                logger.error(f"Cannot send approval_request - router_data is None for router {router_id}")
                    else:
                        logger.warning(f"WebSocket is None - cannot send updates for router {router_id}")

                except Exception as e:
                    logger.error(f"Failed to update router state: {e}", exc_info=True)
        
        return result
    
    # ===== Hook Registration Methods =====
    
    def register_pre_hook(self, tool_name: str, hook: PreHook):
        """
        Register a custom pre-processing hook for a tool.
        
        Args:
            tool_name: Name of the tool (e.g., "agent_tools__my_tool")
            hook: Async function matching PreHook signature
        """
        self._pre_hooks[tool_name] = hook
        logger.info(f"Registered pre-hook for {tool_name}")
    
    def register_post_hook(self, tool_name: str, hook: PostHook):
        """
        Register a custom post-processing hook for a tool.
        
        Args:
            tool_name: Name of the tool
            hook: Async function matching PostHook signature
        """
        self._post_hooks[tool_name] = hook
        logger.info(f"Registered post-hook for {tool_name}")
    
    def unregister_pre_hook(self, tool_name: str):
        """Remove a pre-processing hook."""
        if tool_name in self._pre_hooks:
            del self._pre_hooks[tool_name]
            logger.info(f"Unregistered pre-hook for {tool_name}")
    
    def unregister_post_hook(self, tool_name: str):
        """Remove a post-processing hook."""
        if tool_name in self._post_hooks:
            del self._post_hooks[tool_name]
            logger.info(f"Unregistered post-hook for {tool_name}")


# Global instance for use across the application
tool_hooks = ToolHooks()