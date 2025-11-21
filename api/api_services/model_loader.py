from sentence_transformers import SentenceTransformer


class ModelLoader:
    """Loads embedding models"""

    @staticmethod
    def load(model_name: str) -> SentenceTransformer:
        """Load embedding model"""
        print(f"Loading model: {model_name}")
        return SentenceTransformer(model_name)
