Benchmark Script: scripts/benchmark_semantic_search.py

INITIAL CODE AFTER SWITCH FROM JINA:

============================================================
                 Semantic Search Benchmark
============================================================
Embedding Generation:    420.50s
Indexing Operations:       1.38s
Total Time:              421.88s
------------------------------------------------------------
Files Processed:            508
Total Chunks:               130
Skipped Chunks:               0
Batches:                     64
------------------------------------------------------------
Avg Chunks/File:           0.26
Throughput:                0.31 chunks/sec
============================================================


---

Optimizations:
from:
embeddings = self._embedding_func.generate_embeddings(texts)
to:
embeddings = list(self._embedding_func.generate_embeddings(texts))

============================================================
                 Semantic Search Benchmark
============================================================
Embedding Generation:    464.29s
Indexing Operations:       1.47s
Total Time:              465.76s
------------------------------------------------------------
Files Processed:            516
Total Chunks:               139
Skipped Chunks:               1
Batches:                     67
------------------------------------------------------------
Avg Chunks/File:           0.27
Throughput:                0.30 chunks/sec
============================================================