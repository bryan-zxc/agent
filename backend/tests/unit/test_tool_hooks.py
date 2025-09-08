"""
Unit tests for the tool hook system.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.agent.services.llm.tool_hooks import ToolHooks


@pytest.mark.asyncio
async def test_pre_hook_without_registered_hook():
    """Test that pre-hook passes through args when no hook is registered."""
    hooks = ToolHooks()
    original_args = {"param1": "value1", "param2": "value2"}
    
    result = await hooks.apply_pre_hook(
        "unregistered_tool", 
        original_args, 
        None, 
        None
    )
    
    assert result == original_args
    assert result is original_args  # Should be the same object


@pytest.mark.asyncio
async def test_post_hook_without_registered_hook():
    """Test that post-hook passes through result when no hook is registered."""
    hooks = ToolHooks()
    original_result = {"status": "success", "data": "test"}
    
    result = await hooks.apply_post_hook(
        "unregistered_tool",
        original_result,
        None,
        None
    )
    
    assert result == original_result
    assert result is original_result  # Should be the same object


@pytest.mark.asyncio
async def test_inject_router_id_hook():
    """Test the default router_id injection pre-hook."""
    hooks = ToolHooks()
    original_args = {"objective": "test", "todos": ["task1"]}
    payload = {"router_id": "test_router_123"}
    
    result = await hooks.apply_pre_hook(
        "agent_tools__set_plan_and_answer",
        original_args,
        payload,
        None
    )
    
    # Should have router_id injected
    assert result["router_id"] == "test_router_123"
    assert result["objective"] == "test"
    assert result["todos"] == ["task1"]
    # Should be a copy, not the original
    assert result is not original_args


@pytest.mark.asyncio
async def test_inject_router_id_hook_without_payload():
    """Test router_id injection when payload is missing."""
    hooks = ToolHooks()
    original_args = {"objective": "test", "todos": ["task1"]}
    
    result = await hooks.apply_pre_hook(
        "agent_tools__set_plan_and_answer",
        original_args,
        None,  # No payload
        None
    )
    
    # Should return args unchanged
    assert "router_id" not in result
    assert result == original_args


@pytest.mark.asyncio
async def test_plan_completion_post_hook():
    """Test the plan completion post-hook with websocket."""
    hooks = ToolHooks()
    websocket = AsyncMock()
    payload = {"router_id": "test_router_123"}
    result = """# Execution Plan

## Plan
Test plan description

## Tasks to Execute
- [ ] Task 1
- [ ] Task 2

## Answer Template
Template with placeholders"""
    
    processed_result = await hooks.apply_post_hook(
        "agent_tools__set_plan_and_answer",
        result,
        payload,
        websocket
    )
    
    # Result should pass through unchanged
    assert processed_result == result
    
    # WebSocket should have been called
    websocket.send_json.assert_called_once()
    call_args = websocket.send_json.call_args[0][0]
    assert call_args["type"] == "status"
    assert call_args["router_id"] == "test_router_123"
    assert call_args["status"] == "plamarinating_awaiting_user"


@pytest.mark.asyncio
async def test_plan_completion_post_hook_no_todos():
    """Test the plan completion post-hook when answer is complete (no todos)."""
    hooks = ToolHooks()
    websocket = AsyncMock()
    payload = {"router_id": "test_router_456"}
    result = """# Answer

This is the complete answer with all information already filled in.
No execution needed."""
    
    processed_result = await hooks.apply_post_hook(
        "agent_tools__set_plan_and_answer",
        result,
        payload,
        websocket
    )
    
    # Result should pass through unchanged
    assert processed_result == result
    
    # WebSocket should have been called with 'active' status
    websocket.send_json.assert_called_once()
    call_args = websocket.send_json.call_args[0][0]
    assert call_args["type"] == "status"
    assert call_args["router_id"] == "test_router_456"
    assert call_args["status"] == "active"  # Back to conversation mode


@pytest.mark.asyncio
async def test_custom_hook_registration():
    """Test registering and using custom hooks."""
    hooks = ToolHooks()
    
    # Define custom hooks
    async def custom_pre_hook(tool_name, tool_args, payload, websocket):
        tool_args = tool_args.copy()
        tool_args["custom_field"] = "injected_value"
        return tool_args
    
    async def custom_post_hook(tool_name, result, payload, websocket):
        return {"modified": True, "original": result}
    
    # Register hooks
    hooks.register_pre_hook("custom_tool", custom_pre_hook)
    hooks.register_post_hook("custom_tool", custom_post_hook)
    
    # Test pre-hook
    args = {"param": "value"}
    modified_args = await hooks.apply_pre_hook("custom_tool", args, None, None)
    assert modified_args["custom_field"] == "injected_value"
    assert modified_args["param"] == "value"
    
    # Test post-hook
    result = "original_result"
    modified_result = await hooks.apply_post_hook("custom_tool", result, None, None)
    assert modified_result["modified"] is True
    assert modified_result["original"] == "original_result"


@pytest.mark.asyncio
async def test_hook_error_handling():
    """Test that hook errors don't break execution."""
    hooks = ToolHooks()
    
    # Register a failing hook
    async def failing_hook(tool_name, tool_args, payload, websocket):
        raise Exception("Hook failed!")
    
    hooks.register_pre_hook("failing_tool", failing_hook)
    
    # Should return original args despite hook failure
    original_args = {"param": "value"}
    result = await hooks.apply_pre_hook("failing_tool", original_args, None, None)
    assert result == original_args


@pytest.mark.asyncio
async def test_hook_unregistration():
    """Test unregistering hooks."""
    hooks = ToolHooks()
    
    # Register a custom hook
    async def test_hook(tool_name, tool_args, payload, websocket):
        tool_args = tool_args.copy()
        tool_args["modified"] = True
        return tool_args
    
    hooks.register_pre_hook("test_tool", test_hook)
    
    # Verify hook works
    result = await hooks.apply_pre_hook("test_tool", {"param": "value"}, None, None)
    assert result["modified"] is True
    
    # Unregister hook
    hooks.unregister_pre_hook("test_tool")
    
    # Should now pass through unchanged
    original = {"param": "value"}
    result = await hooks.apply_pre_hook("test_tool", original, None, None)
    assert result == original
    assert "modified" not in result