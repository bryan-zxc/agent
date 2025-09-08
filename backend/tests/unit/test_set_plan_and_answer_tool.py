"""
Unit tests for the set_plan_and_answer MCP tool.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.utils.tools import set_plan_and_answer


@pytest.mark.asyncio
async def test_set_plan_and_answer_with_todos():
    """Test tool with todos - normal execution path."""
    # Mock database
    mock_db = AsyncMock()
    mock_db.get_router.return_value = {"router_id": "test_router_123"}
    mock_db.update_router.return_value = True
    
    with patch('agent.utils.tools.AgentDatabase.create', return_value=mock_db):
        # Use .fn to access the actual function inside the MCP wrapper
        result = await set_plan_and_answer.fn(
            plan_description="Test plan description",
            objective="Test objective",
            answer_template="Answer with [placeholder]",
            todos=["Task 1", "Task 2"],
            router_id="test_router_123"
        )
    
    # Should return execution plan format
    assert "# Execution Plan" in result
    assert "## Plan" in result
    assert "Test plan description" in result
    assert "## Tasks to Execute" in result
    assert "- [ ] Task 1" in result
    assert "- [ ] Task 2" in result
    assert "## Answer Template" in result
    assert "Answer with [placeholder]" in result
    
    # Verify database calls
    mock_db.get_router.assert_called_once_with("test_router_123")
    mock_db.update_router.assert_called_once()
    
    # Check metadata structure
    call_args = mock_db.update_router.call_args
    metadata = call_args[1]['agent_metadata']
    assert 'execution_plan_model' in metadata
    assert 'answer_template' in metadata
    assert 'plan_description' in metadata


@pytest.mark.asyncio
async def test_set_plan_and_answer_without_todos():
    """Test tool without todos - answer complete path."""
    # Mock database
    mock_db = AsyncMock()
    mock_db.get_router.return_value = {"router_id": "test_router_456"}
    mock_db.update_router.return_value = True
    
    with patch('agent.utils.tools.AgentDatabase.create', return_value=mock_db):
        # Use .fn to access the actual function inside the MCP wrapper
        result = await set_plan_and_answer.fn(
            plan_description="Plan is complete",
            objective="Answer the question",
            answer_template="This is the complete answer",
            todos=None,  # No todos
            router_id="test_router_456"
        )
    
    # Should return just the answer
    assert "# Answer" in result
    assert "This is the complete answer" in result
    
    # Should NOT have execution plan sections
    assert "# Execution Plan" not in result
    assert "## Tasks to Execute" not in result
    
    # Verify database calls
    mock_db.get_router.assert_called_once_with("test_router_456")
    mock_db.update_router.assert_called_once()


@pytest.mark.asyncio
async def test_set_plan_and_answer_empty_todos_list():
    """Test tool with empty list of todos."""
    # Mock database
    mock_db = AsyncMock()
    mock_db.get_router.return_value = {"router_id": "test_router_789"}
    mock_db.update_router.return_value = True
    
    with patch('agent.utils.tools.AgentDatabase.create', return_value=mock_db):
        # Use .fn to access the actual function inside the MCP wrapper
        result = await set_plan_and_answer.fn(
            plan_description="Plan complete",
            objective="Provide answer",
            answer_template="Final answer here",
            todos=[],  # Empty list
            router_id="test_router_789"
        )
    
    # Should return just the answer (same as None)
    assert "# Answer" in result
    assert "Final answer here" in result
    assert "# Execution Plan" not in result


@pytest.mark.asyncio
async def test_set_plan_and_answer_missing_router_id():
    """Test tool without router_id - should error."""
    # Use .fn to access the actual function inside the MCP wrapper
    result = await set_plan_and_answer.fn(
        plan_description="Test plan",
        objective="Test objective",
        answer_template="Test template",
        todos=["Task 1"],
        router_id=None  # Missing
    )
    
    assert "Error: router_id not provided" in result


@pytest.mark.asyncio
async def test_set_plan_and_answer_router_not_found():
    """Test tool when router doesn't exist."""
    # Mock database
    mock_db = AsyncMock()
    mock_db.get_router.return_value = None  # Router not found
    
    with patch('agent.utils.tools.AgentDatabase.create', return_value=mock_db):
        # Use .fn to access the actual function inside the MCP wrapper
        result = await set_plan_and_answer.fn(
            plan_description="Test plan",
            objective="Test objective",
            answer_template="Test template",
            todos=["Task 1"],
            router_id="nonexistent_router"
        )
    
    assert "Error: Router nonexistent_router not found" in result


@pytest.mark.asyncio
async def test_set_plan_and_answer_database_update_failure():
    """Test tool when database update fails."""
    # Mock database
    mock_db = AsyncMock()
    mock_db.get_router.return_value = {"router_id": "test_router"}
    mock_db.update_router.return_value = False  # Update fails
    
    with patch('agent.utils.tools.AgentDatabase.create', return_value=mock_db):
        # Use .fn to access the actual function inside the MCP wrapper
        result = await set_plan_and_answer.fn(
            plan_description="Test plan",
            objective="Test objective",
            answer_template="Test template",
            todos=["Task 1"],
            router_id="test_router"
        )
    
    assert "Error: Failed to update router test_router" in result