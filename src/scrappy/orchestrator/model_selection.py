from enum import Enum


class ModelSelectionType(Enum):
    """Types of model selection strategies."""
    FAST = "fast"        # Quick responses, high throughput
    QUALITY = "quality"  # Best output quality
    INSTRUCT = "instruct"  # Instruction-tuned for JSON/structured output
    EMBED = "embed"      # Embeddings
