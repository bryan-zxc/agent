# Agent System - AI Multi-Modal Processing

## GitHub Workflow Lifecycle

### 1. Planning → Create Ticket
- Plan the task first (identify steps)
- Create GitHub issue with full scope:
  - Implementation tasks
  - Descriptions in tickets must always contain full context with the expectation that the ticket will be called in a brand new conversation with no historical context
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
- Update ticket
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

## Git Operations Model

### Branch Strategy (Git Flow)
- **main**: Production-ready code only
- **develop**: Integration branch for features
- **feature/\***: Feature branches (merge to develop)
- **release/\***: Release preparation (merge to main and develop)
- **hotfix/\***: Emergency fixes (merge to main and develop)

### Feature Branch Development

#### 1. Create Feature Branch
```bash
git checkout develop
git pull origin develop
git checkout -b feature/descriptive-name
# First meaningful commit
git push -u origin feature/descriptive-name
```

#### 2. Create Draft PR Immediately
- Create Draft PR to **develop** branch after first commit for visibility
- Title format: `feat: Description [WIP]`
- Link all related tickets in PR description
- Convert to Ready only when all tickets complete

#### 3. Commit Message Standards
```bash
# Work in progress on ticket
git commit -m "feat: Add component X (addresses #123)"
git commit -m "fix: Resolve issue Y (part of #123)"

# Completing a ticket
git commit -m "feat: Complete feature Z (closes #123)"
git commit -m "fix: Final fix for bug (fixes #123)"
```

#### 4. PR Description Template
```markdown
## Overview
Brief description of the feature/change

## Related Issues
- [ ] #XXX - Ticket description
- [ ] #YYY - Another ticket

## Changes
- List of key changes
- Architecture modifications
- API updates

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing complete

## Notes
Any migration or deployment notes
```

#### 5. Development Workflow
```bash
# Keep feature branch updated
git checkout develop
git pull origin develop
git checkout feature/your-branch
git rebase develop  # Or merge if conflicts complex

# Make atomic commits
git add -p  # Selective staging
git commit -m "feat: Specific change (#123)"

# Push regularly (triggers CI)
git push origin feature/your-branch
```

#### 6. Review Milestones
- Request architecture review after core changes
- Request implementation review after functionality complete
- Final review when all tests pass

## Workflow
- **Always read READMEs first**: `/agent/README.md` → module README → code files
- **Backend testing**: Use Docker with uv
- **Documentation updates**: MANDATORY after code changes
- **Git operations**: Follow the model above for all feature development

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