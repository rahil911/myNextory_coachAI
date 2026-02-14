# KG Agent Memory

## My Ownership
(Will be populated as the agent starts working)

Key infrastructure paths:
- .claude/kg/ (graph cache, builder scripts)
- .claude/kg/seeds/ (CSV seed data)
- .claude/mcp/ (MCP server implementations)
- .claude/scripts/ (spawn.sh, cleanup.sh)

## Key Decisions
(Will be populated as the agent makes choices)

## Schema Knowledge
The KG itself (not database tables):
- 40 nodes: 9 agents, 7 modules, 24 business concepts
- 190 edges: PARENT_OF, MANAGES, DEPENDS_ON, IMPLEMENTS, RELATES_TO
- Seed files: agents.csv, modules.csv, concepts.csv, edges.csv, table_concepts.csv
- Cache: agent_graph_cache.json (rebuilt from seeds + DB introspection)

## Infrastructure Status
- MCP servers: (status will be tracked here)
- CLI tools: ag (ownership graph), bd (beads)
- Cache: last rebuilt at (timestamp)

## Recent Changes
(Will be populated as the agent completes tasks)
