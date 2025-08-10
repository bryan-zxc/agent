# Agent System - AI Multi-Modal Processing

**Architecture**: Planning-worker system with multi-modal file processing capabilities.

## Code Workflow

**ALWAYS read README files first** before examining code:

1. Start with `/agent/README.md` for system overview
2. Read module README in the directory you're working with
3. Only read specific code files when README doesn't cover implementation details

**Backend Modules**:
- `agents/` - PlannerAgent and WorkerAgents  
- `core/` - Base classes and routing
- `models/` - Data schemas and database
- `services/` - LLM integration and processing
- `utils/` - Utility functions and tools

**Frontend Modules**:
- `components/` - React components and UI architecture
- `app/` - Next.js App Router and theme system
- `lib/` - Utilities (cn function) and services (file upload)
- `ui/` - shadcn/ui components and theming
- `hooks/` - React hooks and state management
- `stores/` - Zustand state management

## Architecture Summary

- **Multi-Agent**: Planner breaks down tasks → Workers execute them
- **Multi-Modal**: Text, images, charts, tables, data files
- **Unified LLM**: Single interface for OpenAI/Anthropic/Google
- **Safe Execution**: Sandboxed Python with security guardrails
- **Type Safety**: Pydantic models throughout

## CRITICAL: Documentation Update Requirements

**MANDATORY: After making ANY code changes, you MUST update the relevant documentation:**

### Required Documentation Updates After Code Changes:

1. **Module README Files**: Update the README.md in the affected module directory
   - Add new functions/classes to the function listings
   - Update usage examples if behaviour has changed
   - Document new features or capabilities
   - Revise integration points if modified

2. **Main Project README** (`/agent/README.md`): Update when:
   - Adding new major features (add to Features section)
   - Modifying API endpoints (update API Endpoints section)
   - Changing core architecture or tech stack
   - Adding new environment variables or setup steps

3. **Database Documentation** (`/agent/docs/database/`): Update when:
   - Adding new database tables or columns
   - Modifying existing schema structures
   - Changing relationships or indexes
   - Adding new database operations

4. **Architecture Documentation** (`/agent/ARCHITECTURE.md`): Update when:
   - Adding new components or services
   - Modifying system architecture or data flow
   - Changing core design patterns or principles
   - Adding new integration points

### Documentation Update Checklist:

- [ ] Updated relevant module README with new functions/classes
- [ ] Added usage examples for new functionality  
- [ ] Updated main README if features/APIs changed
- [ ] Updated database documentation if schema changed
- [ ] Updated architecture docs if system design changed
- [ ] Used Australian English spelling throughout
- [ ] Verified all code references include file_path:line_number format

**NEVER SKIP DOCUMENTATION UPDATES - they are as important as the code changes themselves.**

This approach ensures efficient code understanding while maintaining comprehensive project knowledge.