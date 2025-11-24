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

---

Optimization (don't manage embeddings):
from:

to:

============================================================
                 Semantic Search Benchmark
============================================================
Embedding Generation:    127.57s
Indexing Operations:     382.59s
Total Time:              510.16s
------------------------------------------------------------
Files Processed:            518
Total Chunks:               160
Skipped Chunks:               0
Batches:                     66
------------------------------------------------------------
Avg Chunks/File:           0.31
Throughput:                0.31 chunks/sec
============================================================


09:41:21,753
09:50:13,793

09:55:59,890
10:05:07,354

10:10:03,671
10:19:40,759


10:37:32,088
10:45:12,066

10:59:48,714
11:03:15,054