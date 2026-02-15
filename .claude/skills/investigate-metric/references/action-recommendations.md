# Action Recommendations

Templates and patterns for recommending actions after a metric investigation.

## Recommendation Categories

### 1. Immediate (within hours)

For critical/high severity breaches:
- **Data fix**: Direct SQL correction (requires explicit authorization bead)
- **Rollback**: Revert recent deployment causing the issue
- **Notify**: Alert affected users/coaches via notification system
- **Workaround**: Temporary alternative while root fix is developed

### 2. Short-term (within days)

For medium severity or complex fixes:
- **Code fix**: Patch the application logic causing the breach
- **Configuration**: Adjust thresholds, rate limits, or feature flags
- **Content**: Add/update missing content blocking user progress
- **Process**: Adjust coaching schedules or admin workflows

### 3. Long-term (within weeks)

For prevention and systemic improvement:
- **Monitoring**: Add alerts for this metric to prevent recurrence
- **Testing**: Add regression tests covering this failure mode
- **Architecture**: Refactor the system to prevent this class of issue
- **Documentation**: Update runbooks with this investigation's findings

## Bead Creation

Create follow-up beads for each recommendation:

```bash
# Immediate action
bd create --title="[URGENT] Fix: [root cause summary]" \
  --type=task --priority=0 \
  --description="Root cause: [details]. Fix: [specific action]."

# Short-term fix
bd create --title="Fix: [issue summary]" \
  --type=task --priority=1 \
  --description="Investigation found: [details]. Recommended fix: [action]."

# Long-term prevention
bd create --title="Prevent: [issue class]" \
  --type=task --priority=2 \
  --description="Add monitoring/testing for [metric]. See investigation: [bead-id]."
```

## Output Template

```markdown
## Recommendations

### Immediate Actions
1. **[Action]** — [Why this is urgent]
   - Owner: [agent-name]
   - Bead: [created bead ID]

### Short-term Fixes
1. **[Action]** — [What this fixes]
   - Owner: [agent-name]
   - Bead: [created bead ID]
   - Estimated effort: [hours/days]

### Long-term Prevention
1. **[Action]** — [What this prevents]
   - Owner: [agent-name]
   - Bead: [created bead ID]

### Monitoring
- Add alert: [metric] < [threshold] for [duration]
- Add dashboard: [what to track]
- Review frequency: [daily/weekly]
```

## Notification Routing

For critical findings, use the notification router:

```python
from src.notifications.router import NotificationRouter

router = NotificationRouter.from_config("config/notifications.yaml")
await router.route(
    title="Investigation Complete: [metric] breach",
    body="Root cause: [summary]. Severity: [level]. Actions: [count] beads created.",
    priority=3,  # Routes to Telegram + Slack
    event_type="investigation_complete",
)
```
