# Pattern Format Schema

Every pattern entry in `patterns.md` MUST follow this exact format.
Place the pattern under the correct category heading.

## Format

```
### [Pattern Name]
- **Discovered by**: [agent-name]
- **Date**: [YYYY-MM-DD]
- **Confidence**: [hypothesis | validated | established]
- **Last validated**: [YYYY-MM-DD]
- **Validation count**: [number]
- **Context**: [When does this pattern apply? Be specific about the scope.]
- **Pattern**: [What to do. Concrete, actionable, with code if relevant.]
- **Anti-pattern**: [What NOT to do. The mistake this pattern prevents.]
- **Evidence**: [Brief description of how this was discovered.]
```

## Confidence Levels

| Level | Meaning | Weight | Promotion criteria |
|-------|---------|--------|--------------------|
| `hypothesis` | First observation, might be wrong | Low — try it but verify | Initial discovery |
| `validated` | Confirmed across 2+ agents or sessions | Medium — follow unless you have reason not to | 2+ independent confirmations |
| `established` | Used successfully 5+ times | High — treat as project convention | 5+ successful uses, 0 contradictions |

## Rules

1. **One pattern per concept.** Don't combine "use Pydantic v2" with "always validate response schemas."
2. **Be specific.** "Handle errors" is not a pattern. "Wrap Snowflake queries in try/except and check for ProgrammingError to catch stale sessions" is.
3. **Include code when possible.** A 3-line code snippet is worth 30 words of description.
4. **Anti-patterns are mandatory.** If you can't articulate what NOT to do, the pattern isn't concrete enough.
5. **Context scoping.** Always specify WHEN the pattern applies. "When calling BC_ANALYTICS APIs" not "always."
