"""
Embedding model backends.

Each backend implements EmbeddingFunctionProtocol and registers
with the EmbeddingRegistry.

Available backends:
- bge_small: BGE-small-en-v1.5 via FastEmbed (always available)
- nomic: Nomic Embed via gpt4all (optional, install with scrappy[nomic])
- jina: Jina Code via sentence-transformers (optional, install with scrappy[jina])
"""

# Backends are lazily imported by the registry to avoid
# loading heavy dependencies until needed.
