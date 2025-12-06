

how can we create agent/claude functionality to follow this process with a single command?
prompts, hooks, slash commands? what tools should we use?
PROCESS: 3 steps? plan, implement, maybe test?
```
PLAN
- review TODO_ITEM.md
- create integration plan (TODO_ITEM_PLAN) from docs
- create/update .beads + clear context
- refine integration TODO_ITEM_PLAN based on architectural goals
- create/update .beads + clear context
- review refined TODO_ITEM_PLAN to ensure it achieves TODO_ITEM desired outcome
- create/update .beads + clear context
- review refined TODO_ITEM_PLAN to ensure new behavior is tested
- create/update .beads + clear context
- review refined TODO_ITEM_PLAN to ensure all steps are concrete
- create/update .beads + clear context
IMPLEMENT
- review TODO_ITEM, if it makes sense, begin
FOR EACH PHASE IN TODO_ITEM_PLAN:
- when phase is complete: 
  - does it align with CLAUDE.md design principles?
  - if not, fix it. if so, create/update .beads + clear context
- when all phases are complete: audit code state versus plan. 
  - if changes are needed to achieve desired state and match CLAUDE.md principles, implement them
  - create/update .beads + clear context, repeat audit until no changes needed
TEST
- use docker container? how to test integration, success?  
- ensure app loads, if not fix
  - if fix is required to load app, fix it
  - create/update .beads + clear context, repeat until app loads
- create report detailing implementation, update beads
```