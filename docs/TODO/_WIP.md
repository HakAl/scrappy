---
docs/TODO/PLAN_SEMANTIC_SEARCH_UX.md

semantic search backend is theoretically functional, but we haven't built a tool for it, or integrated with UX.
it's initialization is commented out here src/scrappy/orchestrator/factory.py
let's research and create a plan for semantic search UX
Current status: status bar shows some numbers, progress doesn't move, timer remains at 0, isn't hidden when task completes. 
Shown every time on load -- need a paradigm created so we show status bar on initial / large scans. not each app launch
Desired status: Semantic search is shown on initial index. Not shown for small updates -- need to define limits and ensure indexing occurs periodically as projects evolve. avoid blocking UX waiting to load in all scenarios.
---