# Agent System - AI Multi-Modal Processing

## GitHub Workflow Lifecycle

### 1. Planning → Create Ticket
- Plan the task first (identify steps)
- Create GitHub issue with full scope:
  - Implementation tasks
  - Testing requirements
  - Documentation updates
- **Always assign to bryan-zxc**: Use `assignees: ["bryan-zxc"]`
- Auto-add to project board: `gh project item-add` with status "ready"

### 2. Action → Update Status
- Mark ticket "in progress" when starting work
- Only ONE ticket "in progress" at a time
- Update ticket with progress comments as needed

### 3. Complete → Close & Commit
- Run tests and verify implementation
- Update documentation as required
- Close ticket: `gh issue close`
- Commit code changes with issue reference: `fixes #123`

## Status IDs
- "e18bf179" (Ready), "47fc9ee4" (In progress), "aba860b9" (In review), "98236657" (Done)

### Update Status (GraphQL)
```bash
# Get project item ID
gh api graphql -f query='
query {
  user(login: "bryan-zxc") {
    projectV2(number: 1) {
      items(first: 100) {
        nodes {
          id
          content {
            ... on Issue {
              number
            }
          }
        }
      }
    }
  }
}' | jq '.data.user.projectV2.items.nodes[] | select(.content.number == ISSUE_NUMBER) | .id'

# Update to "In progress" 
gh api graphql -f query='
mutation {
  updateProjectV2ItemFieldValue(
    input: {
      projectId: "PVT_kwHOCz6Fr84A-4Cm"
      itemId: "ITEM_ID_HERE"
      fieldId: "PVTSSF_lAHOCz6Fr84A-4CmzgyJdHo"
      value: {
        singleSelectOptionId: "47fc9ee4"
      }
    }
  ) {
    projectV2Item {
      id
    }
  }
}'
```

## Workflow
- **Always read READMEs first**: `/agent/README.md` → module README → code files
- **Backend testing**: Use Docker with uv
- **Documentation updates**: MANDATORY after code changes

## Commands
```bash
# Backend testing (Docker required)
docker-compose exec backend uv run python -m py_compile src/agent/tasks/worker_tasks.py
docker-compose exec backend uv run python  # For any Python execution
```

## Documentation Requirements
After code changes, update:
1. Module README (functions/classes/usage)
2. Main README (features/APIs/setup)
3. Database docs (schema changes)
4. Architecture docs (system design)

Use Australian English spelling throughout.