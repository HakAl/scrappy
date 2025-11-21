You are correct that `fastembed` is not currently a built-in key in the default LanceDB registry (unlike `openai` or `sentence-transformers`).

However, you **can** absolutely use FastEmbed with LanceDB. 
You need to define a custom embedding function and register it yourself. 
This allows you to use `fastembed` effectively as if it were built-in.

Here is the complete example code, we should use SOLID + scrappy best practices

```python
import lancedb
from lancedb.embeddings import register, TextEmbeddingFunction
from fastembed import TextEmbedding
from lancedb.pydantic import LanceModel, Vector

# 1. Register the Jina Code model
@register("fastembed-jina") # Custom key for your registry
class JinaEmbedFunction(TextEmbeddingFunction):
    # The exact string supported by FastEmbed
    name: str = "jinaai/jina-embeddings-v2-base-code"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._model = TextEmbedding(model_name=self.name)
        
    def generate_embeddings(self, texts):
        return list(self._model.embed(texts))

    def ndims(self):
        # Jina v2 base code is 768 dimensions
        return 768

# 2. Initialize the function
# We use the key "fastembed-jina" we defined above
registry = lancedb.embeddings.get_registry()
jina_embed = registry.get("fastembed-jina").create()

# 3. Define Schema with Correct Dimensions
class CodeSnippets(LanceModel):
    code: str = jina_embed.SourceField()
    # Note: We must use 768 dimensions for this model
    vector: Vector(768) = jina_embed.VectorField()

# 4. Create Table and Ingest
db = lancedb.connect("~/.lancedb")
table = db.create_table("code_base", schema=CodeSnippets, mode="overwrite")

table.add([
    {"code": "def quicksort(arr): ..."},
    {"code": "class Authentication: ..."}
])
```

### Step 1: Install dependencies

### Step 2: Define and Register the Custom Function
You need to create a class that inherits from `TextEmbeddingFunction` and register it.


import lancedb
from lancedb.embeddings import register, TextEmbeddingFunction
from fastembed import TextEmbedding
from lancedb.pydantic import LanceModel, Vector

# 1. Register the Jina Code model
@register("fastembed-jina") # Custom key for your registry
class JinaEmbedFunction(TextEmbeddingFunction):
    # The exact string supported by FastEmbed
    name: str = "jinaai/jina-embeddings-v2-base-code"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._model = TextEmbedding(model_name=self.name)
        
    def generate_embeddings(self, texts):
        return list(self._model.embed(texts))

    def ndims(self):
        # Jina v2 base code is 768 dimensions
        return 768

# 2. Initialize the function
# We use the key "fastembed-jina" we defined above
registry = lancedb.embeddings.get_registry()
jina_embed = registry.get("fastembed-jina").create()

# 3. Define Schema with Correct Dimensions
class CodeSnippets(LanceModel):
    code: str = jina_embed.SourceField()
    # Note: We must use 768 dimensions for this model
    vector: Vector(768) = jina_embed.VectorField()

# 4. Create Table and Ingest
db = lancedb.connect("~/.lancedb")
table = db.create_table("code_base", schema=CodeSnippets, mode="overwrite")

table.add([
    {"code": "def quicksort(arr): ..."},
    {"code": "class Authentication: ..."}
])
```python
from lancedb.embeddings import register, TextEmbeddingFunction
from fastembed import TextEmbedding
import numpy as np

@register("fastembed")
class FastEmbedFunction(TextEmbeddingFunction):
    name: str = "BAAI/bge-small-en-v1.5" # Default model, can be changed
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._model = TextEmbedding(model_name=self.name)
        
    def generate_embeddings(self, texts):
        # fastembed returns a generator, so we convert to list
        return list(self._model.embed(texts))

    def ndims(self):
        # fastembed doesn't expose ndims directly, so we run a dummy embed
        # BAAI/bge-small-en-v1.5 is 384 dimensions
        return len(list(self._model.embed(["test"]))[0])
```

### Step 3: Use it in your Schema
Now you can use the `"fastembed"` key in the registry just like you wanted.

```python
import lancedb
from lancedb.pydantic import LanceModel, Vector

# 1. Get the registry entry we just created
registry = lancedb.embeddings.get_registry()
fastembed = registry.get("fastembed").create(name="BAAI/bge-small-en-v1.5")

# 2. Define your schema using the function
class Documents(LanceModel):
    text: str = fastembed.SourceField()
    vector: Vector(fastembed.ndims()) = fastembed.VectorField()

# 3. Create Table and Add Data
db = lancedb.connect("~/.lancedb")
table = db.create_table("my_docs", schema=Documents, mode="overwrite")

# Embeddings are generated automatically!
table.add([
    {"text": "LanceDB is a vector database."},
    {"text": "FastEmbed is a lightweight embedding library."}
])

# 4. Search
results = table.search("What is a vector db?").limit(2).to_pandas()
print(results)
```

### Why do you have to do this?
The LanceDB registry is designed to be extensible. 
While they include popular APIs (OpenAI) and heavy-weights (Sentence Transformers) by default, 
lighter or newer libraries like FastEmbed often require this "glue code" until they are officially added to the core library. 
The method above is the official way to bridge that gap.