"""
Execution Plan Converter Utility

Converts between Pydantic ExecutionPlanModel and markdown format,
with quality control validation rules.
"""

import logging
from typing import List, Tuple
from ..models.tasks import ExecutionPlanModel, TodoItem, InitialExecutionPlan

logger = logging.getLogger(__name__)


def initial_plan_to_execution_plan_model(initial_plan: InitialExecutionPlan) -> ExecutionPlanModel:
    """Convert InitialExecutionPlan to ExecutionPlanModel with proper TodoItem objects."""
    todos = [
        TodoItem(description=description, next_action=(i == 0))
        for i, description in enumerate(initial_plan.todos)
    ]
    return ExecutionPlanModel(objective=initial_plan.objective, todos=todos)


def execution_plan_model_to_markdown(model: ExecutionPlanModel) -> str:
    """Convert ExecutionPlanModel to markdown format with icons."""
    markdown_lines = [
        "# Objective",
        model.objective,
        "",
        "# Todos"
    ]
    
    for todo in model.todos:
        # Use updated_description if available, otherwise use original description
        description = todo.updated_description if todo.updated_description else todo.description
        
        if todo.completed:
            markdown_lines.append(f"- [x] ~~{description}~~")
        elif todo.obsolete:
            markdown_lines.append(f"- [❌] ~~{description}~~")
        else:
            markdown_lines.append(f"- [ ] {description}")
    
    return "\n".join(markdown_lines)


def validate_execution_plan_model(model: ExecutionPlanModel, previous_model: ExecutionPlanModel = None) -> Tuple[bool, List[str]]:
    """
    Validate ExecutionPlanModel with quality control rules.
    
    Args:
        model: The ExecutionPlanModel to validate
        previous_model: Previous model for comparison (optional)
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Note: next_action validation removed - handled by overriding logic in planner
    # Rule 1: Every existing task must remain (list only gets larger, never smaller)
    if previous_model:
        if len(model.todos) < len(previous_model.todos):
            errors.append(f"Task list shrunk from {len(previous_model.todos)} to {len(model.todos)} - tasks cannot be removed")
        
        # Check all previous tasks still exist (by description) - allowing for completed/obsolete status changes
        previous_descriptions = [todo.description for todo in previous_model.todos]
        current_descriptions = [todo.description for todo in model.todos]
        
        for prev_desc in previous_descriptions:
            if prev_desc not in current_descriptions:
                errors.append(f"Missing task from previous model: {prev_desc}")
    
    # Rule 2: Use old objective if new one is empty
    if previous_model and not model.objective.strip():
        model.objective = previous_model.objective
        logger.info("Auto-fixed: Used previous objective as current one was empty")
    
    # Rule 3: Validate no empty task descriptions
    for i, todo in enumerate(model.todos):
        if not todo.description.strip():
            errors.append(f"Task {i} has empty description")
    
    # Rule 4: Check for conflicting states (excluding next_action checks)
    for i, todo in enumerate(model.todos):
        if todo.completed and todo.obsolete:
            errors.append(f"Task {i} cannot be both completed and obsolete")
    
    is_valid = len(errors) == 0
    
    if not is_valid:
        logger.warning(f"ExecutionPlanModel validation failed: {errors}")
    
    return is_valid, errors


def get_next_action_task(model: ExecutionPlanModel) -> TodoItem:
    """Get the task marked as next_action, or None if no task is marked."""
    for todo in model.todos:
        if todo.next_action:
            return todo
    return None


def mark_task_completed(model: ExecutionPlanModel) -> ExecutionPlanModel:
    """
    Mark the current next_action task as completed and set the next task as next_action.
    
    Args:
        model: ExecutionPlanModel to update
        
    Returns:
        Updated ExecutionPlanModel
    """
    # Find and mark the next_action task as completed
    for todo in model.todos:
        if todo.next_action:
            todo.completed = True
            todo.next_action = False
            break
    
    # Find the next uncompleted, non-obsolete task and mark as next_action
    for todo in model.todos:
        if not todo.completed and not todo.obsolete:
            todo.next_action = True
            break
    
    return model


def has_pending_tasks(model: ExecutionPlanModel) -> bool:
    """Check if there are any pending (uncompleted, non-obsolete) tasks."""
    return any(not todo.completed and not todo.obsolete for todo in model.todos)