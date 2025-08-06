# Agent Database Documentation

## Overview

This directory contains comprehensive documentation for the Agent State Database system, a unified SQLite database that persists conversation messages, agent states, and task management for the AI agent system.

## Architecture Summary

The database implements a hybrid Data Vault approach, combining:
- **Fixed columns** for stable, frequently-queried attributes
- **JSON metadata fields** for extensibility
- **Schema versioning** for evolution management
- **Relationship tracking** between routers, planners, and workers

## Quick Reference

### Core Tables
- **conversations** - Chat conversation metadata
- **routers** - Router agent state and configuration
- **planners** - Planner agent execution plans and status
- **workers** - Task/worker execution details and results
- **router_planner_links** - Router-planner relationships
- **router_messages**, **planner_messages**, **worker_messages** - Agent conversation history

### Key Relationships
```
conversation (1:1) router (1:n) planner (1:n) worker
                      ↘         ↗
                   router_planner_links
```

## Documentation Structure

### 📊 [Entity Relationship Diagram](erd.md)
Complete ERD with table relationships and cardinalities using Mermaid notation.

### 📝 [Data Dictionary](data_dictionary.md)
Comprehensive field definitions, data types, constraints, and business rules for all tables.

### 🔄 [Schema Evolution Guide](schema_evolution.md)
Schema versioning strategy, migration patterns, and evolution best practices.

### 🚀 [Migration Guide](migration_guide.md)
Step-by-step procedures for database migrations, rollbacks, and version transitions.

### ⚡ [Performance Guide](performance_guide.md)
Indexing strategy, query optimization, connection management, and performance monitoring.

## Implementation Files

### Database Layer
- `src/agent/models/agent_database.py` - Unified database service and SQLAlchemy models
- `src/agent/config/settings.py` - Database configuration and schema version

### Agent Integration
- `src/agent/core/base.py` - BaseAgent with database persistence
- `src/agent/core/router.py` - RouterAgent state management
- `src/agent/agents/planner.py` - PlannerAgent with TaskManager
- `src/agent/agents/worker.py` - WorkerAgent task execution

## Getting Started

1. **Understanding the Schema**: Start with [erd.md](erd.md) for visual overview
2. **Field Reference**: Use [data_dictionary.md](data_dictionary.md) for detailed field information
3. **Making Changes**: Follow [schema_evolution.md](schema_evolution.md) for safe modifications
4. **Performance**: Consult [performance_guide.md](performance_guide.md) for optimization

## Database Philosophy

### Data Vault Principles Applied
- **Hubs**: Stable business keys (router_id, planner_id, worker_id)
- **Satellites**: Descriptive attributes with temporal tracking
- **Links**: Explicit relationship tracking
- **Flexibility**: JSON metadata for schema evolution

### Design Goals
- **Restart Recovery**: Agents can resume from database state
- **State Consistency**: Real-time synchronisation through property setters
- **Future-Proof**: Schema versioning enables gradual evolution
- **Performance**: Hybrid column/JSON approach balances speed and flexibility

---

**Maintained by**: Agent Development Team  
**Last Updated**: 2025-08-06  
**Schema Version**: 1.0