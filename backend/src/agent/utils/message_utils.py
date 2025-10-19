"""
Message manipulation utilities for the agent system.

This module provides helper functions for working with message lists,
particularly for appending content to messages in an intelligent way.
"""

from typing import List, Union, Dict, Any


def append_user_content(
    messages: List[Dict[str, Any]], 
    new_content: Union[str, List[Dict[str, Any]], Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Append content to the last user message or create a new one.
    
    This helps maintain cleaner message history by combining multiple
    system instructions into existing user messages when possible.
    Instead of creating multiple consecutive user messages, this function
    intelligently appends to the last user message if one exists.
    
    Args:
        messages: List of message dictionaries with 'role' and 'content' keys
        new_content: Content to append - can be:
            - str: Plain text content
            - dict: Single content dictionary (e.g., {"type": "text", "text": "..."})
            - list: List of content dictionaries
    
    Returns:
        New list of messages with content appended appropriately
    
    Example:
        >>> messages = [{"role": "user", "content": "Hello"}]
        >>> new_messages = append_user_content(messages, "How are you?")
        >>> # Results in combined content in the same user message
    """
    # Create a copy to avoid modifying the original
    messages_copy = messages.copy()
    
    if messages_copy and messages_copy[-1]["role"] == "user":
        # Append to existing user message
        last_message = messages_copy[-1]
        last_content = last_message["content"]
        
        # Normalise the new content to list format
        if isinstance(new_content, str):
            new_content_list = [{"type": "text", "text": new_content}]
        elif isinstance(new_content, dict):
            new_content_list = [new_content]
        else:  # already a list
            new_content_list = new_content
        
        # Handle different formats of existing content
        if isinstance(last_content, str):
            # Convert string to list format and append
            last_message["content"] = [
                {"type": "text", "text": last_content}
            ] + new_content_list
        elif isinstance(last_content, list):
            # Extend existing list
            last_content.extend(new_content_list)
        else:
            # Shouldn't happen, but handle gracefully
            last_message["content"] = new_content_list
    else:
        # Create new user message
        messages_copy.append({
            "role": "user",
            "content": new_content
        })
    
    return messages_copy


def format_tool_call_display(tool_call: Any) -> str:
    """
    Format tool call for display to user.

    Args:
        tool_call: OpenAI ResponseFunctionToolCall or Anthropic ToolUseBlock

    Returns:
        Formatted display string with double newlines for markdown
    """
    import json

    # Handle OpenAI format
    if hasattr(tool_call, 'name') and hasattr(tool_call, 'arguments'):
        tool_name = tool_call.name
        args = json.loads(tool_call.arguments) if isinstance(tool_call.arguments, str) else tool_call.arguments
    # Handle Anthropic format
    elif hasattr(tool_call, 'name') and hasattr(tool_call, 'input'):
        tool_name = tool_call.name
        args = tool_call.input
    else:
        return "Tool call (unknown format)"

    # Format parameters with double newlines for markdown display
    params = "\n".join([f"- {k}: {v}" for k, v in args.items()])

    return f"Calling tool: {tool_name}\n\nInput parameters:\n\n{params}"


def extract_text_from_response(response: Any, provider: str) -> str:
    """
    Extract displayable text from LLM response.

    Args:
        response: API response object
        provider: "openai" or "anthropic"

    Returns:
        Text content for display
    """
    if provider == "openai":
        # OpenAI Responses API
        if hasattr(response, 'output_text'):
            return response.output_text
        return ""

    elif provider == "anthropic":
        # Anthropic Messages API
        text_parts = []
        if hasattr(response, 'content'):
            for block in response.content:
                if hasattr(block, 'text'):
                    text_parts.append(block.text)
        return "\n".join(text_parts)

    return ""