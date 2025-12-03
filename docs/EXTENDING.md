# Extending RAG-KB Pipeline

Add custom extractors, chunkers, embedders, or rerankers to RAG-KB.

> **Just want to change models?** Edit [`config/pipeline.yaml`](../config/pipeline.yaml) - no code needed.

---

## Quick Reference

| I want to... | Solution | Effort |
|--------------|----------|--------|
| Change embedding model | Edit `pipeline.yaml` | 1 min |
| Switch chunking strategy | Edit `pipeline.yaml` | 1 min |
| Support new file format | Implement `ExtractorInterface` | 30-60 min |
| Domain-specific chunking | Implement `ChunkerInterface` | 1-2 hours |
| Use OpenAI/Cohere embeddings | Implement `EmbedderInterface` | 2-3 hours |

---

## Architecture

RAG-KB uses a 4-stage pipeline. Each stage has an interface and is created by a factory.

| Stage | Interface | Config Key |
|-------|-----------|------------|
| Extraction | `ExtractorInterface` | `extraction.provider` |
| Chunking | `ChunkerInterface` | `chunking.strategy` |
| Embedding | `EmbedderInterface` | `embedding.provider` |
| Reranking | `RerankerInterface` | `reranking.enabled` |

### Workflow

1. Implement the interface
2. Register in factory
3. Configure via YAML
4. Write tests

---

## Adding a Custom Extractor

### 1. Implement the Interface

```python
# api/ingestion/extractors/my_extractor.py

from pathlib import Path
from typing import ClassVar, Set
from domain_models import ExtractionResult
from pipeline.interfaces.extractor import ExtractorInterface


class MyExtractor(ExtractorInterface):
    """Extract text from .xyz files."""

    SUPPORTED_EXTENSIONS: ClassVar[Set[str]] = {'.xyz', '.abc'}

    @property
    def name(self) -> str:
        return "my_extractor"

    def extract(self, path: Path) -> ExtractionResult:
        with open(path, 'r') as f:
            content = f.read()
        pages = [(content, None)]
        return ExtractionResult(pages=pages, method=self.name)
```

### 2. Register in Factory

Edit `api/pipeline/factory.py`:

```python
@classmethod
def _load_extractors(cls):
    from pipeline.extractors.my_extractor import MyExtractor
    extractors = [
        # ... existing ...
        MyExtractor,
    ]
```

### 3. Test

```python
def test_my_extractor(tmp_path):
    test_file = tmp_path / "test.xyz"
    test_file.write_text("Test content")

    extractor = MyExtractor()
    result = extractor.extract(test_file)

    assert result.method == 'my_extractor'
    assert 'Test content' in result.pages[0][0]
```

---

## Adding a Custom Chunker

### 1. Implement the Interface

```python
# api/pipeline/chunkers/my_chunker.py

from typing import List, Dict
from pipeline.interfaces.chunker import ChunkerInterface


class MyChunker(ChunkerInterface):
    """Custom chunking strategy."""

    def __init__(self, max_tokens: int = 512):
        self.max_tokens = max_tokens

    @property
    def name(self) -> str:
        return "my_strategy"

    def chunkify(self, source: str, **kwargs) -> List[Dict]:
        if not source.strip():
            return []
        return [{'content': source, 'metadata': {'chunker': self.name}}]
```

### 2. Register in Factory

```python
def create_chunker(self) -> ChunkerInterface:
    strategy = self.config.chunking.strategy.lower()
    if strategy == "my_strategy":
        from pipeline.chunkers.my_chunker import MyChunker
        return MyChunker(max_tokens=self.config.chunking.max_tokens)
```

### 3. Configure

```yaml
# config/pipeline.yaml
chunking:
  strategy: my_strategy
  max_tokens: 512
```

---

## Adding a Custom Embedder

### 1. Implement the Interface

```python
# api/pipeline/embedders/my_embedder.py

from typing import List, Optional, Callable
from pipeline.interfaces.embedder import EmbedderInterface


class MyEmbedder(EmbedderInterface):
    """Custom embedding model."""

    def __init__(self, model_name: str = "my-model"):
        self._model_name = model_name
        self._model = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return 768

    def embed(self, texts: List[str], on_progress: Optional[Callable] = None) -> List[List[float]]:
        if self._model is None:
            self._model = self._load_model()

        embeddings = []
        for i, text in enumerate(texts):
            embedding = self._model.encode(text)
            embeddings.append(embedding.tolist())
            if on_progress:
                on_progress(i + 1, len(texts))
        return embeddings

    def _load_model(self):
        # Load your model here
        pass
```

### 2. Register in Factory

```python
def create_embedder(self, model=None) -> EmbedderInterface:
    provider = self.config.embedding.provider.lower()
    if provider == "my-provider":
        from pipeline.embedders.my_embedder import MyEmbedder
        return MyEmbedder(model_name=self.config.embedding.model)
```

---

## Adding a Custom Reranker

### 1. Implement the Interface

```python
# api/pipeline/rerankers/my_reranker.py

from typing import List
from pipeline.interfaces.reranker import RerankerInterface


class MyReranker(RerankerInterface):
    """Custom reranking model."""

    def __init__(self, model_name: str = "my-reranker"):
        self._model_name = model_name
        self._model = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def is_enabled(self) -> bool:
        return True

    def rerank(self, query: str, candidates: List[dict], top_k: int) -> List[dict]:
        if self._model is None:
            self._model = self._load_model()

        scored = []
        for candidate in candidates:
            score = self._model.score(query, candidate['content'])
            scored.append((score, candidate))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:top_k]]

    def _load_model(self):
        pass
```

---

## Common Mistakes

### Missing SUPPORTED_EXTENSIONS

```python
# Wrong
class MyExtractor(ExtractorInterface):
    def extract(self, path): ...

# Right
class MyExtractor(ExtractorInterface):
    SUPPORTED_EXTENSIONS: ClassVar[Set[str]] = {'.xyz'}
```

### Wrong return type from chunkify

```python
# Wrong - returns List[str]
def chunkify(self, source):
    return ["chunk1", "chunk2"]

# Right - returns List[Dict]
def chunkify(self, source):
    return [{'content': "chunk1"}, {'content': "chunk2"}]
```

### Circular imports

```python
# Wrong - import at module level
from pipeline.extractors.my_extractor import MyExtractor

# Right - lazy import inside method
def _load_extractors(cls):
    from pipeline.extractors.my_extractor import MyExtractor
```

---

## Performance Tips

### Lazy Loading

Don't load models in `__init__`:

```python
def __init__(self):
    self._model = None  # Load later

def process(self, data):
    if self._model is None:
        self._model = load_heavy_model()
    return self._model.process(data)
```

### Batch Processing

```python
# Slow
def embed(self, texts):
    return [self._model.encode(text) for text in texts]

# Fast
def embed(self, texts):
    return self._model.encode(texts, batch_size=32)
```

---

## Testing

### Interface Compliance

```python
def test_implements_interface():
    impl = MyImplementation()
    assert isinstance(impl, TheInterface)

def test_returns_correct_type():
    result = impl.method(valid_input)
    assert isinstance(result, ExpectedType)
```

### Factory Integration

```python
def test_factory_creates_implementation(tmp_path):
    yaml_file = tmp_path / "pipeline.yaml"
    yaml_file.write_text("chunking:\n  strategy: my_strategy")

    factory = PipelineFactory.from_yaml(yaml_file)
    impl = factory.create_chunker()

    assert isinstance(impl, MyChunker)
```

---

## File Locations

| Component | Location |
|-----------|----------|
| Interfaces | `api/pipeline/interfaces/` |
| Extractors | `api/ingestion/extractors/` |
| Chunkers | `api/pipeline/chunkers/` |
| Embedders | `api/pipeline/embedders/` |
| Rerankers | `api/pipeline/rerankers/` |
| Factory | `api/pipeline/factory.py` |
| Config | `config/pipeline.yaml` |

---

## See Also

- [PIPELINE.md](PIPELINE.md) - Configuration options
- [CONFIGURATION.md](CONFIGURATION.md) - Infrastructure settings
