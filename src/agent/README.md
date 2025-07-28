# Agent Library

A comprehensive AI agent system for processing various file types and executing complex tasks using large language models.

## Architecture Overview

This library implements a multi-agent system that can process documents, images, and data files to answer user questions and execute tasks. The system uses a planning-worker architecture where a planner breaks down complex requests into smaller tasks that are executed by specialized worker agents.

## Directory Structure

```
agent/
├── agents/          # Core agent implementations
├── config/          # Configuration and settings
├── core/            # Base classes and routing logic
├── models/          # Pydantic models and schemas
├── security/        # Security and safety guardrails
├── services/        # External service integrations
└── utils/           # Utility functions and tools
```

## Key Components

### Agents (`agents/`)
- **PlannerAgent**: Breaks down user requests into executable tasks
- **WorkerAgent**: Executes individual tasks with code generation
- **WorkerAgentSQL**: Specialized worker for database queries

### Core (`core/`)
- **BaseAgent**: Foundation class for all agents
- **RouterAgent**: Routes requests to appropriate processing pipelines

### Services (`services/`)
- **LLM Service**: Unified interface for multiple language models (OpenAI, Anthropic, Google)
- **Document Service**: PDF processing and content extraction
- **Image Service**: Image analysis and content recognition

### Models (`models/`)
- **Task Models**: Define task structure and execution flow
- **Response Models**: Structure API responses and validations
- **Schema Models**: Data models for files, images, and documents

## Getting Started

```python
from agent.core.router import RouterAgent
from agent.models.schemas import File

# Create a request with files
files = [File(filepath="data.csv", file_type="data", data_context="csv")]
router = RouterAgent(user_request=request)
await router.invoke()
response = await router.get_response_to_user()
```

## Features

- **Multi-modal Processing**: Handles text, images, charts, tables, and data files
- **Task Planning**: Automatically breaks down complex requests
- **Code Execution**: Safe sandboxed Python code execution
- **SQL Queries**: DuckDB integration for data analysis
- **Image Analysis**: Chart reading, table extraction, and visual content analysis
- **Document Processing**: PDF parsing with text and image extraction
- **Safety**: Built-in security guardrails and code validation

## Dependencies

- **LLM Providers**: OpenAI, Anthropic Claude, Google Gemini
- **Data Processing**: pandas, DuckDB, pypdf
- **Image Processing**: PIL, base64 encoding
- **Validation**: Pydantic models
- **Execution**: Sandboxed Python environment