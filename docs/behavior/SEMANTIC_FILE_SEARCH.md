revisions:

### The Chunker Logic

*   **Refinement:** Your AST logic currently only handles Python (`if not file_path.endswith('.py')`).  This is fine for V1, but ensure your `_fixed_chunks` fallback is robust for many file types.

### Risks

There is one specific area in `src/context/file_embedder.py` that needs optimization to prevent crashing on large repos.

**The Issue: Memory Pressure**
In `embed_codebase`, you are collecting **every text chunk in the entire project** into a single list (`all_texts`) before sending it to the model.
```python
# Current Plan
for file_path, content in files.items():
    # ... collects 10,000+ strings ...
embeddings = self._embedder.embed_texts(all_texts) # <--- RAM spike
```

**The Fix: Batch Processing**
Embed in batches (e.g., 256 chunks at a time) to keep memory usage stable.

```python
# Recommended Change in FileEmbedder
def embed_codebase(self, files: dict[str, str], batch_size: int = 128):
    all_chunks = []
    batch_texts = []
    embeddings_list = []

    for file_path, content in files.items():
        file_chunks = self.chunk_file(file_path, content)
        for chunk in file_chunks:
            all_chunks.append(chunk)
            batch_texts.append(self.extract_chunk_text(content, chunk))
            
            # Process batch if full
            if len(batch_texts) >= batch_size:
                batch_emb = self.embed_texts(batch_texts)
                embeddings_list.append(batch_emb)
                batch_texts = [] # Clear memory

    # Process remaining
    if batch_texts:
        batch_emb = self.embed_texts(batch_texts)
        embeddings_list.append(batch_emb)

    if not embeddings_list:
        return [], np.array([])

    # Concatenate numpy arrays (efficient)
    return all_chunks, np.vstack(embeddings_list)
```

### UX Fix: The "First Run
`fastembed` downloads the model (approx 300MB-500MB depending on the model) on the very first run.
*   **Risk:** If the user runs `tool explore`, it might hang silently while downloading.
*   **Fix:** In `FileEmbedder._get_model`, add a printed notification if the model isn't cached yet, or ensure `fastembed`'s progress bar is visible.


FAISS Semantic File Search - Integration Plan (Revised)

  Overview

  Add semantic code search to enable intelligent prompt augmentation. When users ask "how to make the api more
  secure?", the system finds and includes relevant code chunks automatically.

  ---
  Dependencies

  # pyproject.toml
  dependencies = [
      "fastembed>=0.2.0",   # ~50MB (ONNX Runtime, no PyTorch)
      "faiss-cpu>=1.7.0",   # ~15MB
  ]

  Total installation: ~80MB (vs 600MB-2GB with sentence-transformers)

  ---
  Architecture

  src/context/
      __init__.py              # Add new exports
      codebase_context.py      # Orchestrator - uses FileContentProvider
      file_scanner.py          # Existing
      project_detector.py      # Existing
      git_history.py           # Existing
      cache.py                 # Existing
      platform.py              # Existing
      code_chunker.py          # NEW - Splits files into semantic chunks
      file_embedder.py         # NEW - Embeds chunks with fastembed
      semantic_index.py        # NEW - FAISS index with IndexIDMap
      file_content_provider.py # NEW - High-level API for retrieval

  ---
  Phase 1: Core Components

  1.1 Data Structures

  # src/context/semantic_index.py

  from dataclasses import dataclass

  @dataclass
  class ChunkInfo:
      """Metadata for a code chunk."""
      chunk_id: int
      file_path: str
      start_line: int
      end_line: int
      chunk_type: str  # 'function', 'class', 'module', 'window'
      name: str | None  # 'validate_token', 'UserAPI', None for windows

  1.2 CodeChunker

  # src/context/code_chunker.py

  import ast
  from pathlib import Path

  class CodeChunker:
      """Splits code files into semantic chunks for embedding."""

      def __init__(self,
                   strategy: str = 'hybrid',
                   chunk_size: int = 50,
                   overlap: int = 10,
                   max_chunk_lines: int = 100):
          self.strategy = strategy
          self.chunk_size = chunk_size
          self.overlap = overlap
          self.max_chunk_lines = max_chunk_lines

      def chunk(self, file_path: str, content: str) -> list[ChunkInfo]:
          """Chunk file based on strategy."""
          if self.strategy == 'fixed':
              return self._fixed_chunks(file_path, content)
          elif self.strategy == 'ast':
              return self._ast_chunks(file_path, content)
          else:  # hybrid
              return self._hybrid_chunks(file_path, content)

      def _fixed_chunks(self, file_path: str, content: str) -> list[ChunkInfo]:
          """Split into fixed-size overlapping windows."""
          lines = content.splitlines()
          chunks = []

          start = 0
          while start < len(lines):
              end = min(start + self.chunk_size, len(lines))
              chunks.append(ChunkInfo(
                  chunk_id=0,  # Assigned later by index
                  file_path=file_path,
                  start_line=start + 1,  # 1-indexed
                  end_line=end,
                  chunk_type='window',
                  name=None
              ))
              start += self.chunk_size - self.overlap
              if start >= len(lines):
                  break

          return chunks

      def _ast_chunks(self, file_path: str, content: str) -> list[ChunkInfo]:
          """Split by AST nodes (functions, classes)."""
          if not file_path.endswith('.py'):
              return self._fixed_chunks(file_path, content)

          try:
              tree = ast.parse(content)
          except SyntaxError:
              return self._fixed_chunks(file_path, content)

          chunks = []

          for node in ast.iter_child_nodes(tree):
              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                  chunks.append(ChunkInfo(
                      chunk_id=0,
                      file_path=file_path,
                      start_line=node.lineno,
                      end_line=node.end_lineno,
                      chunk_type='function',
                      name=node.name
                  ))
              elif isinstance(node, ast.ClassDef):
                  chunks.append(ChunkInfo(
                      chunk_id=0,
                      file_path=file_path,
                      start_line=node.lineno,
                      end_line=node.end_lineno,
                      chunk_type='class',
                      name=node.name
                  ))

          # If no AST nodes found, use fixed chunking
          if not chunks:
              return self._fixed_chunks(file_path, content)

          # Add module-level code (imports, constants) if not covered
          chunks = self._add_module_header(file_path, content, chunks)

          return sorted(chunks, key=lambda c: c.start_line)

      def _hybrid_chunks(self, file_path: str, content: str) -> list[ChunkInfo]:
          """AST-based with splitting for large chunks."""
          chunks = self._ast_chunks(file_path, content)

          # Split any chunks that are too large
          final_chunks = []
          lines = content.splitlines()

          for chunk in chunks:
              chunk_lines = chunk.end_line - chunk.start_line + 1
              if chunk_lines > self.max_chunk_lines:
                  # Re-chunk this section with fixed windows
                  sub_content = '\n'.join(lines[chunk.start_line - 1:chunk.end_line])
                  sub_chunks = self._fixed_chunks(chunk.file_path, sub_content)
                  # Adjust line numbers
                  for sc in sub_chunks:
                      sc.start_line += chunk.start_line - 1
                      sc.end_line += chunk.start_line - 1
                      sc.name = chunk.name  # Preserve parent name
                  final_chunks.extend(sub_chunks)
              else:
                  final_chunks.append(chunk)

          return final_chunks

      def _add_module_header(self, file_path: str, content: str,
                            chunks: list[ChunkInfo]) -> list[ChunkInfo]:
          """Add module header (imports, docstring) if not covered."""
          if not chunks:
              return chunks

          first_chunk_start = min(c.start_line for c in chunks)

          if first_chunk_start > 1:
              # There's code before the first function/class
              chunks.insert(0, ChunkInfo(
                  chunk_id=0,
                  file_path=file_path,
                  start_line=1,
                  end_line=first_chunk_start - 1,
                  chunk_type='module',
                  name=None
              ))

          return chunks

  1.3 FileEmbedder

  # src/context/file_embedder.py

  import numpy as np
  from fastembed import TextEmbedding
  from .code_chunker import CodeChunker, ChunkInfo

  class FileEmbedder:
      """Generates embeddings for code chunks using fastembed."""

      MODELS = {
          'default': 'BAAI/bge-small-en-v1.5',   # 33MB, dim=384
          'small': 'BAAI/bge-small-en-v1.5',
          'micro': 'BAAI/bge-micro-v2',           # 14MB, dim=384
          'base': 'BAAI/bge-base-en-v1.5',        # 110MB, dim=768
      }

      def __init__(self,
                   model_name: str = 'default',
                   chunk_strategy: str = 'hybrid',
                   chunk_size: int = 50,
                   chunk_overlap: int = 10,
                   max_chunk_lines: int = 100):
          self._model = None
          self._model_name = self.MODELS.get(model_name, model_name)
          self._chunker = CodeChunker(
              strategy=chunk_strategy,
              chunk_size=chunk_size,
              overlap=chunk_overlap,
              max_chunk_lines=max_chunk_lines
          )

      def _get_model(self) -> TextEmbedding:
          """Lazy load the embedding model."""
          if self._model is None:
              self._model = TextEmbedding(model_name=self._model_name)
          return self._model

      def embed_texts(self, texts: list[str]) -> np.ndarray:
          """Embed multiple texts."""
          model = self._get_model()
          embeddings = list(model.embed(texts))
          return np.array(embeddings, dtype=np.float32)

      def embed_query(self, query: str) -> np.ndarray:
          """Embed a search query."""
          model = self._get_model()
          embeddings = list(model.query_embed(query))
          return np.array(embeddings[0], dtype=np.float32)

      def chunk_file(self, file_path: str, content: str) -> list[ChunkInfo]:
          """Split file into semantic chunks."""
          return self._chunker.chunk(file_path, content)

      def embed_codebase(self, files: dict[str, str]) -> tuple[list[ChunkInfo], np.ndarray]:
          """Chunk and embed entire codebase.

          Args:
              files: {file_path: content}

          Returns:
              chunks: List of ChunkInfo
              embeddings: numpy array of shape (n_chunks, embedding_dim)
          """
          all_chunks = []
          all_texts = []

          for file_path, content in files.items():
              file_chunks = self.chunk_file(file_path, content)
              for chunk in file_chunks:
                  all_chunks.append(chunk)
                  chunk_text = self.extract_chunk_text(content, chunk)
                  all_texts.append(chunk_text)

          if not all_texts:
              return [], np.array([])

          embeddings = self.embed_texts(all_texts)
          return all_chunks, embeddings

      def extract_chunk_text(self, content: str, chunk: ChunkInfo) -> str:
          """Extract text for a chunk from file content."""
          lines = content.splitlines()
          chunk_lines = lines[chunk.start_line - 1:chunk.end_line]
          return '\n'.join(chunk_lines)

      def get_embedding_dimension(self) -> int:
          """Get the embedding dimension for the current model."""
          model = self._get_model()
          test_emb = list(model.embed(["test"]))[0]
          return len(test_emb)

  1.4 SemanticIndex

  # src/context/semantic_index.py

  import json
  import faiss
  import numpy as np
  from pathlib import Path
  from dataclasses import dataclass, asdict

  @dataclass
  class ChunkInfo:
      chunk_id: int
      file_path: str
      start_line: int
      end_line: int
      chunk_type: str
      name: str | None


  class SemanticIndex:
      """FAISS index with IndexIDMap for update/delete support."""

      def __init__(self, dimension: int = 384):
          self._dimension = dimension
          self._index = None
          self._chunks: dict[int, ChunkInfo] = {}
          self._file_to_chunks: dict[str, list[int]] = {}
          self._next_id = 0

      def _create_index(self):
          """Create FAISS index with ID mapping."""
          base_index = faiss.IndexFlatIP(self._dimension)
          self._index = faiss.IndexIDMap(base_index)

      def build(self, chunks: list[ChunkInfo], embeddings: np.ndarray):
          """Build index from chunk embeddings."""
          self._create_index()
          self._chunks = {}
          self._file_to_chunks = {}
          self._next_id = 0

          if len(chunks) == 0:
              return

          # Normalize for cosine similarity
          embeddings = embeddings.astype(np.float32)
          faiss.normalize_L2(embeddings)

          # Assign IDs
          ids = np.arange(len(chunks), dtype=np.int64)

          for i, chunk in enumerate(chunks):
              chunk_id = int(ids[i])
              chunk.chunk_id = chunk_id
              self._chunks[chunk_id] = chunk

              if chunk.file_path not in self._file_to_chunks:
                  self._file_to_chunks[chunk.file_path] = []
              self._file_to_chunks[chunk.file_path].append(chunk_id)

          self._next_id = len(chunks)
          self._index.add_with_ids(embeddings, ids)

      def search(self, query_embedding: np.ndarray, k: int = 5) -> list[tuple[ChunkInfo, float]]:
          """Search for similar chunks."""
          if self._index is None or self._index.ntotal == 0:
              return []

          query = query_embedding.reshape(1, -1).astype(np.float32)
          faiss.normalize_L2(query)

          scores, ids = self._index.search(query, k)

          results = []
          for idx, score in zip(ids[0], scores[0]):
              if idx >= 0 and idx in self._chunks:
                  results.append((self._chunks[idx], float(score)))

          return results

      def update_file(self, file_path: str, chunks: list[ChunkInfo], embeddings: np.ndarray):
          """Update all chunks for a file (remove old, add new)."""
          self.remove_file(file_path)
          self.add_file(file_path, chunks, embeddings)

      def remove_file(self, file_path: str):
          """Remove all chunks for a file."""
          if file_path not in self._file_to_chunks:
              return

          chunk_ids = self._file_to_chunks[file_path]

          if chunk_ids:
              ids_to_remove = np.array(chunk_ids, dtype=np.int64)
              self._index.remove_ids(ids_to_remove)

              for chunk_id in chunk_ids:
                  del self._chunks[chunk_id]

          del self._file_to_chunks[file_path]

      def add_file(self, file_path: str, chunks: list[ChunkInfo], embeddings: np.ndarray):
          """Add chunks for a file."""
          if self._index is None:
              self._create_index()

          if len(chunks) == 0:
              return

          embeddings = embeddings.astype(np.float32)
          faiss.normalize_L2(embeddings)

          new_ids = np.arange(self._next_id, self._next_id + len(chunks), dtype=np.int64)

          self._file_to_chunks[file_path] = []

          for i, chunk in enumerate(chunks):
              chunk_id = int(new_ids[i])
              chunk.chunk_id = chunk_id
              self._chunks[chunk_id] = chunk
              self._file_to_chunks[file_path].append(chunk_id)

          self._next_id += len(chunks)
          self._index.add_with_ids(embeddings, new_ids)

      def has_file(self, file_path: str) -> bool:
          """Check if file is indexed."""
          return file_path in self._file_to_chunks

      def get_file_chunks(self, file_path: str) -> list[ChunkInfo]:
          """Get all chunks for a file."""
          if file_path not in self._file_to_chunks:
              return []
          return [self._chunks[cid] for cid in self._file_to_chunks[file_path]]

      @property
      def total_chunks(self) -> int:
          return self._index.ntotal if self._index else 0

      @property
      def total_files(self) -> int:
          return len(self._file_to_chunks)

      def save(self, index_path: Path, mapping_path: Path):
          """Save index and mappings to disk."""
          if self._index is None:
              return

          faiss.write_index(self._index, str(index_path))

          mapping_data = {
              'dimension': self._dimension,
              'next_id': self._next_id,
              'chunks': {
                  str(k): asdict(v) for k, v in self._chunks.items()
              },
              'file_to_chunks': self._file_to_chunks
          }

          with open(mapping_path, 'w') as f:
              json.dump(mapping_data, f, indent=2)

      def load(self, index_path: Path, mapping_path: Path) -> bool:
          """Load index and mappings from disk."""
          if not index_path.exists() or not mapping_path.exists():
              return False

          try:
              self._index = faiss.read_index(str(index_path))

              with open(mapping_path, 'r') as f:
                  mapping_data = json.load(f)

              self._dimension = mapping_data.get('dimension', 384)
              self._next_id = mapping_data['next_id']
              self._file_to_chunks = mapping_data['file_to_chunks']

              self._chunks = {}
              for k, v in mapping_data['chunks'].items():
                  self._chunks[int(k)] = ChunkInfo(**v)

              return True

          except Exception:
              return False

  1.5 FileContentProvider

  # src/context/file_content_provider.py

  from pathlib import Path
  from .file_embedder import FileEmbedder
  from .semantic_index import SemanticIndex, ChunkInfo

  class FileContentProvider:
      """Provides relevant code chunks for prompt augmentation."""

      def __init__(self, project_path: Path, model_name: str = 'default'):
          self.project_path = project_path
          self._embedder = FileEmbedder(model_name=model_name)
          self._index = SemanticIndex()

          # Cache paths
          self._index_path = project_path / '.llm_team_embeddings.faiss'
          self._mapping_path = project_path / '.llm_team_embeddings.json'

      def build_index(self, files: dict[str, str]):
          """Build semantic index from file contents.

          Args:
              files: {relative_path: content}
          """
          chunks, embeddings = self._embedder.embed_codebase(files)
          self._index.build(chunks, embeddings)
          self._save_index()

      def is_indexed(self) -> bool:
          """Check if index exists."""
          return self._index_path.exists() and self._mapping_path.exists()

      def load_index(self) -> bool:
          """Load index from disk."""
          return self._index.load(self._index_path, self._mapping_path)

      def _save_index(self):
          """Save index to disk."""
          self._index.save(self._index_path, self._mapping_path)

      def find_relevant_chunks(self, query: str, k: int = 10) -> list[tuple[ChunkInfo, float]]:
          """Find chunks semantically relevant to query."""
          if self._index.total_chunks == 0:
              return []

          query_embedding = self._embedder.embed_query(query)
          return self._index.search(query_embedding, k=k)

      def get_context_for_query(self, query: str,
                                 max_chunks: int = 5,
                                 max_tokens: int = 4000) -> list[dict]:
          """Get relevant code chunks for prompt augmentation.

          Returns:
              List of {
                  'file_path': str,
                  'start_line': int,
                  'end_line': int,
                  'content': str,
                  'score': float,
                  'name': str | None,
                  'chunk_type': str
              }
          """
          results = self.find_relevant_chunks(query, k=max_chunks * 2)

          # Deduplicate overlapping chunks
          results = self._deduplicate_chunks(results)

          context = []
          tokens_used = 0

          for chunk_info, score in results[:max_chunks]:
              content = self._read_chunk(chunk_info)
              chunk_tokens = self._estimate_tokens(content)

              if tokens_used + chunk_tokens > max_tokens:
                  break

              context.append({
                  'file_path': chunk_info.file_path,
                  'start_line': chunk_info.start_line,
                  'end_line': chunk_info.end_line,
                  'content': content,
                  'score': score,
                  'name': chunk_info.name,
                  'chunk_type': chunk_info.chunk_type
              })
              tokens_used += chunk_tokens

          return context

      def _read_chunk(self, chunk: ChunkInfo) -> str:
          """Read chunk content from file."""
          file_path = self.project_path / chunk.file_path

          try:
              content = file_path.read_text(encoding='utf-8', errors='ignore')
              lines = content.splitlines()
              chunk_lines = lines[chunk.start_line - 1:chunk.end_line]
              return '\n'.join(chunk_lines)
          except Exception:
              return ""

      def _deduplicate_chunks(self, results: list[tuple[ChunkInfo, float]]) -> list[tuple[ChunkInfo, float]]:
          """Remove overlapping chunks from same file, keeping highest score."""
          seen_ranges = {}  # file_path -> list of (start, end) ranges
          deduplicated = []

          for chunk, score in results:
              file_path = chunk.file_path

              if file_path not in seen_ranges:
                  seen_ranges[file_path] = []

              # Check for overlap with existing ranges
              overlaps = False
              for start, end in seen_ranges[file_path]:
                  if not (chunk.end_line < start or chunk.start_line > end):
                      overlaps = True
                      break

              if not overlaps:
                  seen_ranges[file_path].append((chunk.start_line, chunk.end_line))
                  deduplicated.append((chunk, score))

          return deduplicated

      def _estimate_tokens(self, text: str) -> int:
          """Rough token estimate (4 chars per token)."""
          return len(text) // 4

      def update_changed_files(self, changed_files: dict[str, str]):
          """Incrementally update index for changed files."""
          for file_path, content in changed_files.items():
              chunks = self._embedder.chunk_file(file_path, content)
              texts = [self._embedder.extract_chunk_text(content, c) for c in chunks]

              if texts:
                  embeddings = self._embedder.embed_texts(texts)
                  self._index.update_file(file_path, chunks, embeddings)

          self._save_index()

      def remove_files(self, file_paths: list[str]):
          """Remove deleted files from index."""
          for file_path in file_paths:
              self._index.remove_file(file_path)

          self._save_index()

      def clear_index(self):
          """Clear the semantic index."""
          self._index = SemanticIndex()
          if self._index_path.exists():
              self._index_path.unlink()
          if self._mapping_path.exists():
              self._mapping_path.unlink()

  ---
  Phase 2: Integration with CodebaseContext

  2.1 Update CodebaseContext

  # In src/context/codebase_context.py

  from .file_content_provider import FileContentProvider

  class CodebaseContext:
      def __init__(self, project_path: Optional[str] = None):
          # ... existing initialization ...

          # Semantic search component
          self._content_provider = FileContentProvider(self.project_path)

      def explore(self, force: bool = False) -> dict:
          # ... existing exploration ...

          # Build semantic index after exploration
          if self._should_build_semantic_index():
              self._build_semantic_index()

          return result

      def _should_build_semantic_index(self) -> bool:
          """Check if semantic index needs to be built."""
          if not self._content_provider.is_indexed():
              return True
          # Could also check file modification times
          return False

      def _build_semantic_index(self):
          """Build FAISS index from source files."""
          source_files = {}

          # Read all source code files
          for category in ['python', 'javascript']:
              for file_path in self.file_index.get(category, []):
                  full_path = self.project_path / file_path
                  if full_path.exists():
                      try:
                          content = full_path.read_text(encoding='utf-8', errors='ignore')
                          source_files[file_path] = content
                      except Exception:
                          pass

          if source_files:
              self._content_provider.build_index(source_files)

      def get_relevant_code(self, query: str, max_chunks: int = 5) -> list[dict]:
          """Get code chunks relevant to a query.

          Args:
              query: Natural language query
              max_chunks: Maximum chunks to return

          Returns:
              List of chunk dicts with file_path, content, lines, etc.
          """
          if not self._content_provider.is_indexed():
              if not self._content_provider.load_index():
                  return []

          return self._content_provider.get_context_for_query(query, max_chunks=max_chunks)

      def augment_prompt_with_code(self, user_prompt: str,
                                    include_code: bool = True,
                                    max_chunks: int = 3) -> str:
          """Augment prompt with relevant code context.

          Args:
              user_prompt: Original user prompt
              include_code: Whether to include code chunks
              max_chunks: Maximum code chunks to include

          Returns:
              Augmented prompt with code context
          """
          # Get base augmentation
          augmented = self.augment_prompt(user_prompt)

          if not include_code:
              return augmented

          # Find relevant code
          chunks = self.get_relevant_code(user_prompt, max_chunks=max_chunks)

          if not chunks:
              return augmented

          # Format code context
          code_parts = []
          for chunk in chunks:
              header = f"# {chunk['file_path']}:{chunk['start_line']}-{chunk['end_line']}"
              if chunk.get('name'):
                  header += f" ({chunk['name']})"
              code_parts.append(f"{header}\n```\n{chunk['content']}\n```")

          code_context = "\n\n".join(code_parts)

          return f"""[Relevant Code]
  {code_context}

  {augmented}"""

  ---
  Phase 3: Cache Structure

  project/
  ├── .llm_team_context.json       # Existing context cache
  ├── .llm_team_embeddings.faiss   # FAISS index (binary)
  └── .llm_team_embeddings.json    # Chunk mappings

  Embeddings Mapping Schema

  {
    "dimension": 384,
    "next_id": 156,
    "chunks": {
      "0": {
        "chunk_id": 0,
        "file_path": "src/api.py",
        "start_line": 1,
        "end_line": 25,
        "chunk_type": "module",
        "name": null
      },
      "1": {
        "chunk_id": 1,
        "file_path": "src/api.py",
        "start_line": 27,
        "end_line": 89,
        "chunk_type": "class",
        "name": "UserAPI"
      }
    },
    "file_to_chunks": {
      "src/api.py": [0, 1, 2],
      "src/auth.py": [3, 4, 5, 6]
    }
  }

  ---
  Phase 4: Configuration

  # Could be added to CLI config or CodebaseContext init

  SEMANTIC_SEARCH_CONFIG = {
      'enabled': True,
      'model': 'default',  # 'micro', 'small', 'base'
      'chunk_strategy': 'hybrid',  # 'fixed', 'ast', 'hybrid'
      'chunk_size': 50,
      'chunk_overlap': 10,
      'max_chunk_lines': 100,
      'max_chunks_per_query': 5,
      'max_tokens_per_query': 4000,
  }

  ---
  Phase 5: Test Plan (TDD)

  Test Files

  tests/test_code_chunker.py
  tests/test_file_embedder.py
  tests/test_semantic_index.py
  tests/test_file_content_provider.py

  Key Test Cases

  CodeChunker Tests

  class TestCodeChunkerFixed:
      def test_chunks_small_file_into_single_chunk(self)
      def test_chunks_with_overlap(self)
      def test_handles_empty_file(self)

  class TestCodeChunkerAST:
      def test_extracts_functions(self)
      def test_extracts_classes(self)
      def test_includes_module_header(self)
      def test_falls_back_on_syntax_error(self)
      def test_falls_back_for_non_python(self)

  class TestCodeChunkerHybrid:
      def test_splits_large_functions(self)
      def test_preserves_small_functions(self)

  SemanticIndex Tests

  class TestSemanticIndexBasic:
      def test_build_and_search(self)
      def test_returns_scores_in_order(self)
      def test_handles_empty_index(self)

  class TestSemanticIndexUpdates:
      def test_update_file_removes_old_chunks(self)
      def test_update_file_adds_new_chunks(self)
      def test_remove_file_decreases_count(self)
      def test_old_ids_not_in_search_results(self)

  class TestSemanticIndexPersistence:
      def test_save_and_load(self)
      def test_load_preserves_search_results(self)

  FileContentProvider Tests

  class TestFileContentProvider:
      def test_find_relevant_chunks(self)
      def test_deduplicates_overlapping_chunks(self)
      def test_respects_token_budget(self)
      def test_incremental_update(self)

  ---
  Implementation Order

  Week 1: Core Components

  1. Write tests for CodeChunker
  2. Implement CodeChunker
  3. Write tests for FileEmbedder
  4. Implement FileEmbedder

  Week 2: Index & Search

  5. Write tests for SemanticIndex
  6. Implement SemanticIndex
  7. Write tests for FileContentProvider
  8. Implement FileContentProvider

  Week 3: Integration

  9. Update CodebaseContext
  10. Integration tests
  11. Update init.py exports

  Week 4: Polish

  12. Incremental update optimization
  13. Configuration options
  14. Documentation

  ---
  Performance Expectations

  | Codebase Size | Index Build | Query Time | Disk Usage |
  |---------------|-------------|------------|------------|
  | 100 files     | 3-5s        | <50ms      | ~2MB       |
  | 500 files     | 10-15s      | <50ms      | ~8MB       |
  | 1000 files    | 20-30s      | <50ms      | ~15MB      |
  | 5000 files    | 90-120s     | <100ms     | ~60MB      |

  ---
  Example Usage

  # After exploration
  context = CodebaseContext("/path/to/project")
  context.explore()

  # Query for relevant code
  query = "how to make the api more secure?"
  chunks = context.get_relevant_code(query, max_chunks=5)

  # Returns:
  [
      {
          'file_path': 'src/api.py',
          'start_line': 45,
          'end_line': 78,
          'content': 'def validate_request(request):\n    ...',
          'score': 0.82,
          'name': 'validate_request',
          'chunk_type': 'function'
      },
      {
          'file_path': 'src/auth.py',
          'start_line': 12,
          'end_line': 56,
          'content': 'class TokenValidator:\n    ...',
          'score': 0.79,
          'name': 'TokenValidator',
          'chunk_type': 'class'
      }
  ]

  # Or augment prompt directly
  augmented = context.augment_prompt_with_code(
      "how to make the api more secure?",
      max_chunks=3
  )

