## Issues 

---
PROBLEM:
 Looking at the code:

  1. InteractiveMode._run_loop() in interactive.py - has its own input loop using
  input_handler.read_interactive_input()
  2. But TextualInteractiveMode creates an InteractiveMode and passes it to ScrappyApp
  3. ScrappyApp never calls _run_loop() - it handles input via Textual's TextArea and calls _process_input()
  directly

Confirmed. TextualInteractiveMode.run():
  1. Creates an InteractiveMode instance
  2. Passes it to ScrappyApp
  3. Calls app.run() (Textual's run)

  InteractiveMode.run() and _main_loop() are never called. The ScrappyApp only uses
  interactive_mode._process_input() directly.

  So the dead code is:
  - InteractiveMode.run()
  - InteractiveMode._main_loop()
  - InputHandler.read_interactive_input()
  - InputHandler._read_first_line()

  Want me to remove this dead code?
---

---
PROBLEM: (RESEARCH)
Does /clear clear all history files in .scrappy/ ? 
---

---
Problem: (RESEARCH)
semantic search no longer indexes --- .scrappy/lancedb remains empty
debug.log:
2025-11-27 11:17:54,131 - asyncio - DEBUG - Using proactor: IocpProactor
2025-11-27 11:17:54,802 - src.context.semantic_manager - DEBUG - Creating SemanticSearchInitializer with event queue
2025-11-27 11:17:54,803 - src.context.semantic_manager - DEBUG - Starting background semantic search initialization
2025-11-27 11:17:54,803 - src.infrastructure.threading.event_queue - DEBUG - Registered handler for source: semantic_search
2025-11-27 11:17:54,803 - src.context.semantic.initializer - DEBUG - Starting semantic search initialization in background
2025-11-27 11:17:54,803 - src.infrastructure.threading.managed_thread - DEBUG - Started managed thread: SemanticSearchInit
2025-11-27 11:17:54,803 - src.context.semantic.initializer - DEBUG - Started background semantic search initialization
2025-11-27 11:17:54,809 - src.context.semantic.provider - DEBUG - Initializing embedding function (may take 10-30s on first use)...
2025-11-27 11:17:54,809 - src.context.semantic.embeddings - DEBUG - Initializing FastEmbed with model: BAAI/bge-small-en-v1.5
2025-11-27 11:17:54,811 - urllib3.connectionpool - DEBUG - Starting new HTTPS connection (1): huggingface.co:443
2025-11-27 11:17:55,014 - src.orchestrator.output - INFO - [OK] GitHub Models provider registered (GPT-4o: 10K RPD, 10M TPD)
2025-11-27 11:17:55,229 - src.orchestrator.output - INFO - [OK] Cerebras provider registered (14,400 RPD)
2025-11-27 11:17:55,285 - urllib3.connectionpool - DEBUG - https://huggingface.co:443 "GET /api/models/qdrant/bge-small-en-v1.5-onnx-q HTTP/1.1" 307 78
2025-11-27 11:17:55,350 - urllib3.connectionpool - DEBUG - https://huggingface.co:443 "GET /api/models/Qdrant/bge-small-en-v1.5-onnx-Q HTTP/1.1" 200 1468
2025-11-27 11:17:55,401 - src.orchestrator.output - INFO - [OK] Groq provider registered (7,000 RPD)
2025-11-27 11:17:55,402 - src.orchestrator.output - INFO - [OK] Gemini provider registered (auto-fallback enabled)
2025-11-27 11:17:55,411 - urllib3.connectionpool - DEBUG - https://huggingface.co:443 "GET /api/models/qdrant/bge-small-en-v1.5-onnx-q/tree/52398278842ec682c6f32300af41344b1c0b0bb2?recursive=False&expand=False HTTP/1.1" 307 153
2025-11-27 11:17:55,465 - urllib3.connectionpool - DEBUG - https://huggingface.co:443 "GET /api/models/Qdrant/bge-small-en-v1.5-onnx-Q/tree/52398278842ec682c6f32300af41344b1c0b0bb2?recursive=False&expand=False HTTP/1.1" 200 1117
2025-11-27 11:17:55,523 - urllib3.connectionpool - DEBUG - https://huggingface.co:443 "GET /api/models/qdrant/bge-small-en-v1.5-onnx-q/revision/main HTTP/1.1" 307 92
2025-11-27 11:17:55,590 - urllib3.connectionpool - DEBUG - https://huggingface.co:443 "GET /api/models/Qdrant/bge-small-en-v1.5-onnx-Q/revision/main HTTP/1.1" 200 1468
2025-11-27 11:17:55,860 - src.orchestrator.output - INFO - [OK] Cohere provider registered (1,000/month - use sparingly)
2025-11-27 11:17:55,860 - src.orchestrator.output - INFO - [BRAIN] Using cerebras as orchestrator brain
2025-11-27 11:17:55,881 - src.context.semantic.embeddings - DEBUG - FastEmbed model initialized
2025-11-27 11:17:55,886 - src.context.semantic.provider - DEBUG - Embedding model is fully loaded
2025-11-27 11:17:55,887 - src.context.semantic.provider - DEBUG - Embedding function initialized
2025-11-27 11:17:55,890 - src.context.semantic.initializer - DEBUG - Embedding model is fully loaded
2025-11-27 11:17:55,890 - src.context.semantic.initializer - DEBUG - Semantic search initialized successfully in background
2025-11-27 11:17:55,890 - src.infrastructure.threading.event_queue - DEBUG - Event submitted: init_complete from semantic_search
2025-11-27 11:17:55,890 - src.context.semantic.initializer - DEBUG - Emitted INIT_COMPLETE event to queue
2025-11-27 11:17:55,906 - asyncio - DEBUG - Using proactor: IocpProactor

---

---
Problem: (RESEARCH)
.lancedb created outside .scrappy/ at root
---

---
Problem:
Remove save audit log agent prompt -- default to save. Doesn't seem to respect 'n' anyway.
---

---
Problem: /agent (other commands?) cannot take newline charactrs
Error output:
 Invalid command: Command cannot contain newline characters
 Type /help for available commands.
Solution:
Filter input? how to?
---


---
PROBLEM: Chat not added to log. User can't view Q+A, only A. Output is excessive.
 Output:
 ----------------------------------------
 I understand. How can I assist you?
 ----------------------------------------
SOLUTION:
Only show reply, not surrounding characters.
---

===

Unconfirmed / Mixed Behavior / Potential Non issue
===

---
textual dev console
---
---
textual command palette
---
---
what's auto route mode?

def render_welcome_banner(
    io: "UnifiedIOProtocol",
    auto_route_mode: bool = False
) -> None:
---