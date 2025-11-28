## Architecture Diagram

```
                      +-------------------+
                      |   User Config     |
                      | (.scrappy/config) |
                      +--------+----------+
                               |
                               v
  +------------------+   +-----+------+   +-------------------+
  | FilePrioritizer  |-->|  File      |-->| SemanticFile      |
  | Protocol         |   | Collector  |   | Collector         |
  +------------------+   +------------+   +-------------------+
                                                 |
                                                 v
  +------------------+   +------------+   +-----+-------------+
  | Composite        |-->|  LanceDB   |-->| cleanup_deleted   |
  | CodeChunker      |   | Provider   |   | _files()          |
  +--------+---------+   +-----+------+   +-------------------+
           |                   |
           v                   v
  +--------+---------+   +-----+-------------+
  | PythonASTChunker |   | ResultRanker      |
  | (+ future langs) |   | Protocol          |
  +------------------+   +-------------------+
                               |
                               v
                      +--------+----------+
                      | Ranked Search     |
                      | Results           |
                      +-------------------+
```
