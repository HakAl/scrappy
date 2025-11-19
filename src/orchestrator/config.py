"""
Single source of truth for provider configuration.

This module centralizes all provider-related configuration that was previously
scattered across provider_selector.py and rate_limiter.py.
"""

# Provider priority order for brain selection and fallback
# NOTE: GitHub Models excluded from default priority due to aggressive rate limiting
PROVIDER_PRIORITY = ['cerebras', 'groq', 'gemini', 'cohere', 'github_models']

# Detailed provider information
PROVIDER_INFO = {
    'cerebras': {
        'quota': '14,400 RPD',
        'description': 'highest daily quota',
    },
    'groq': {
        'quota': '7,000 RPD',
        'description': 'fast and reliable',
    },
    'gemini': {
        'quota': 'varies',
        'description': 'auto-fallback enabled',
    },
    'cohere': {
        'quota': '1,000/month',
        'description': 'limited quota - embeddings only',
    },
    'github_models': {
        'quota': '10K RPD',
        'description': 'aggressive rate limiting - not suitable for brain',
    },
}

# Task-specific provider preferences
# Order matters - first available provider in list is selected
TASK_PREFERENCES = {
    'planning': ['cerebras', 'groq', 'gemini'],
    'execution': ['cerebras', 'groq', 'gemini'],
    'quick': ['cerebras', 'groq'],
    'general': ['cerebras', 'groq', 'gemini'],
}

# Default priority for brain selection (excludes problematic providers)
BRAIN_PRIORITY = ['cerebras', 'groq', 'gemini']

# Fallback priority (same as brain for now)
FALLBACK_PRIORITY = ['cerebras', 'groq', 'gemini']


def get_provider_reason(provider_name: str) -> str:
    """
    Get human-readable reason for provider selection.

    Args:
        provider_name: Name of the provider

    Returns:
        Description string explaining why this provider was selected
    """
    if provider_name not in PROVIDER_INFO:
        return 'available'

    info = PROVIDER_INFO[provider_name]
    quota = info['quota']
    description = info['description']

    return f"{quota} - {description}"
