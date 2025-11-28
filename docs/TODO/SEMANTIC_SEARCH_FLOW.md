# Semantic Search Initialization Flow

## Current Architecture

```
Factory
  -> creates CodebaseContext
  -> creates SemanticSearchInitializer (WITHOUT event_queue)
  -> assigns to context._semantic_initializer (UNUSED - manager already created)
  -> calls context.start_background_initialization()

CodebaseContext.__init__
  -> creates SemanticSearchManager(initializer=semantic_initializer)
     (semantic_initializer is None at this point since factory sets it AFTER construction)

SemanticSearchManager.start_background_init()
  -> if no initializer, calls _create_default_initializer()
  -> _create_default_initializer() creates SemanticSearchInitializer WITH event_queue
  -> registers event handler with event_queue
  -> calls initializer.start()

SemanticSearchInitializer._initialize_worker()
  -> loads model in background thread
  -> on completion, calls _emit_completion_event()
  -> _emit_completion_event() puts INIT_COMPLETE event on event_queue

SemanticSearchManager._handle_event()
  -> receives INIT_COMPLETE event
  -> triggers auto-indexing via file_collector_callback
```

## The Problem

The factory creates an initializer WITHOUT the event_queue:
```python
initializer = SemanticSearchInitializer(context.project_path)  # No event_queue!
```

Then assigns it to `context._semantic_initializer` AFTER the context is constructed.
But SemanticSearchManager was already created with `initializer=None`.

So SemanticSearchManager._create_default_initializer() creates its OWN initializer WITH the event_queue.
This SHOULD work... but something is broken.

## Key Question

Is `process_events()` being called anywhere? The event queue needs to be polled.

Looking at the code:
- `SemanticSearchManager.process_events()` calls `self._event_queue.process_pending()`
- `CodebaseContext.process_background_events()` delegates to manager
- BUT: Is anyone calling this from the TUI?

## Investigation Needed

1. Is `process_events()` called periodically from TUI?
2. Is the initializer actually starting (check logs)?
3. Is the INIT_COMPLETE event being emitted?
4. Is the event handler being registered correctly?

## Likely Fix

The TUI needs to periodically call `codebase_context.process_background_events()`
to process the event queue and trigger the auto-indexing when model loading completes.

Without this, events sit in the queue forever.
