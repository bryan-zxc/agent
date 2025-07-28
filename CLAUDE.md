# Claude Code Project Context

## Project Overview
This is an AI agent system for processing various file types and executing complex tasks using large language models. The system uses a planning-worker architecture with multi-modal processing capabilities.

## Code Understanding Instructions

### Primary Documentation Sources
When working with this codebase, **ALWAYS start by reading the README files** in the relevant directories before examining individual code files:

1. **Main Overview**: Read `/agent/README.md` first for architecture understanding
2. **Module-Specific**: Read the README.md in the specific folder you're working with:
   - `/agent/agents/README.md` - For planner and worker agents
   - `/agent/config/README.md` - For configuration and constants
   - `/agent/core/README.md` - For base classes and routing
   - `/agent/models/README.md` - For data models and schemas
   - `/agent/security/README.md` - For security guardrails
   - `/agent/services/README.md` - For LLM and processing services
   - `/agent/utils/README.md` - For utility functions and tools

### Workflow for Code Tasks

1. **Start with READMEs**: Always read the relevant README file(s) first to understand:
   - Module purpose and architecture
   - Available classes and functions
   - Usage patterns and examples
   - Integration points

2. **Targeted Code Reading**: Only read specific code files when you need to:
   - Understand implementation details not covered in README
   - Debug specific issues
   - Make targeted modifications

3. **Avoid Full Code Scanning**: Do not read all code files in a directory unless absolutely necessary. The READMEs provide comprehensive overviews.

## Key Architecture Points

- **Multi-Agent System**: PlannerAgent breaks down tasks, WorkerAgents execute them
- **Multi-Modal Processing**: Handles text, images, charts, tables, and data files
- **Unified LLM Interface**: Single service supports OpenAI, Anthropic, and Google models
- **Safe Execution**: Sandboxed Python environment with security guardrails
- **Structured Data**: Pydantic models ensure type safety throughout

## Common Tasks and Starting Points

### Understanding the System
- Start with `/agent/README.md`
- Review `/agent/core/README.md` for base architecture

### Working with Agents
- Read `/agent/agents/README.md` for PlannerAgent and WorkerAgent details
- Check `/agent/models/README.md` for task-related data models

### Adding New Features
- Check `/agent/services/README.md` for service integrations
- Review `/agent/utils/README.md` for available utilities

### Configuration Changes
- Read `/agent/config/README.md` for settings and constants

### Security Considerations
- Always review `/agent/security/README.md` for guardrails

## Development Guidelines

1. **Documentation First**: READMEs are the authoritative source for module understanding
2. **Incremental Understanding**: Build knowledge progressively from READMEs to specific code
3. **Context Efficiency**: Use READMEs to avoid unnecessary code exploration
4. **Maintain Documentation**: Update READMEs when making significant changes

This approach ensures efficient code understanding while maintaining comprehensive project knowledge.