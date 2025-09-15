"""LLM provider configurations and constants.

This module centralises all LLM provider-specific configurations including
model mappings, pricing, and provider requirements.
"""

from typing import Dict, Any

# Provider model mappings
# Maps friendly names to (provider, actual_model_name) tuples
PROVIDER_MODELS = {
    "gpt-5-mini": ("openai", "gpt-5-mini-2025-08-07"),
    "sonnet-4": ("anthropic", "claude-sonnet-4-20250514"),
    "gemini-2.5-pro": ("google", "gemini-2.5-pro"),
}

# Provider pricing configurations
# Costs are per 1M tokens in USD
PROVIDER_PRICING = {
    "openai": {
        "gpt-5-mini-2025-08-07": {
            "input": 0.25,
            "output": 2.0,
        }
    },
    "anthropic": {
        "claude-sonnet-4-20250514": {
            "input": 3.0,
            "output": 15.0,
        }
    },
    "google": {
        "gemini-2.5-pro": {
            "input_low": 1.25,   # ≤200k tokens
            "output_low": 10.0,  # ≤200k tokens
            "input_high": 2.50,  # >200k tokens
            "output_high": 15.0, # >200k tokens
            "threshold": 200000,  # 200k token threshold
        }
    }
}

# Provider requirements
# Maps providers to required environment variables
PROVIDER_REQUIREMENTS = {
    "openai": ["openai_api_key"],
    "anthropic": ["anthropic_api_key"],
    "google": ["gemini_api_key"],
}

# Default retry configuration
RETRY_CONFIG = {
    "max_retries": 3,
    "max_structured_retries": 2,
    "base_delay": 5,  # Base delay in seconds for exponential backoff
}

# Request limits
REQUEST_LIMITS = {
    "max_tool_rounds": 10,  # Maximum rounds of tool calling
    "max_tokens": 4096,     # Default max tokens for responses
}


def get_provider_for_model(model: str) -> str:
    """
    Get the provider name for a given model.
    
    Args:
        model: Friendly model name
        
    Returns:
        Provider name (openai, anthropic, google)
        
    Raises:
        ValueError: If model is not recognised
    """
    if model in PROVIDER_MODELS:
        return PROVIDER_MODELS[model][0]
    
    # Fallback to prefix matching
    if model.startswith("gpt"):
        return "openai"
    elif model.startswith("claude") or model.startswith("sonnet"):
        return "anthropic"
    elif model.startswith("gemini"):
        return "google"
    else:
        raise ValueError(f"Unknown model: {model}")


def get_actual_model_name(model: str) -> str:
    """
    Get the actual API model name for a friendly model name.
    
    Args:
        model: Friendly model name
        
    Returns:
        Actual model name for API calls
    """
    if model in PROVIDER_MODELS:
        return PROVIDER_MODELS[model][1]
    
    # If not in mapping, return as-is (assume it's already an actual name)
    return model


def validate_provider_config(provider: str, settings: Any) -> bool:
    """
    Validate that required settings exist for a provider.
    
    Args:
        provider: Provider name
        settings: Settings object with API keys
        
    Returns:
        True if all required settings are present
    """
    requirements = PROVIDER_REQUIREMENTS.get(provider, [])
    
    for req in requirements:
        if not getattr(settings, req, None):
            return False
    
    return True