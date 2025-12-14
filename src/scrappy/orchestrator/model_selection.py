from enum import Enum


class ModelSelectionType(Enum):
    """Types of model selection strategies."""
    FAST = "fast"        # Quick responses, high throughput
    QUALITY = "quality"  # Best output quality
    INSTRUCT = "instruct"  # Instruction-tuned for JSON/structured output
    EMBED = "embed"      # Embeddings


# Canonical mapping from ModelSelectionType to LiteLLM model groups.
# Single source of truth - import this instead of defining your own.
SELECTION_TYPE_TO_GROUP: dict[ModelSelectionType, str] = {
    ModelSelectionType.FAST: "fast",
    ModelSelectionType.QUALITY: "quality",
    ModelSelectionType.INSTRUCT: "quality",  # Instruct maps to quality tier
    ModelSelectionType.EMBED: "fast",        # Embeddings use fast tier
}
