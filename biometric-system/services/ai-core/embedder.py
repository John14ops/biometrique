"""
Génération d'embeddings faciaux — ArcFace 512D via ONNX Runtime
Normalise les vecteurs pour comparaison cosinus.
"""
import numpy as np
import cv2
from pathlib import Path
from typing import Optional
from loguru import logger

try:
    import onnxruntime as ort
    ONNX_OK = True
except ImportError:
    ONNX_OK = False
    logger.warning("ONNX Runtime non disponible")

try:
    import insightface
    INSIGHTFACE_OK = True
except ImportError:
    INSIGHTFACE_OK = False


EMBEDDING_DIM = 512
INPUT_SIZE = (112, 112)   # ArcFace standard


class FaceEmbedder:
    """
    Génère des embeddings 512D à partir d'une image de visage aligné.
    Utilise ArcFace (InsightFace) ou ONNX Runtime directement.
    """

    def __init__(self,
                 model_path: Optional[str] = None,
                 gpu: bool = False):
        self.model_path = model_path
        self.gpu = gpu
        self._session = None
        self._initialized = False

    def initialize(self) -> bool:
        if self._initialized:
            return True

        providers = (["CUDAExecutionProvider", "CPUExecutionProvider"]
                     if self.gpu else ["CPUExecutionProvider"])

        # Chercher le modèle ONNX local
        if self.model_path and Path(self.model_path).exists() and ONNX_OK:
            try:
                self._session = ort.InferenceSession(
                    self.model_path, providers=providers
                )
                self._initialized = True
                logger.success(f"Embedder ONNX chargé: {self.model_path}")
                return True
            except Exception as e:
                logger.error(f"ONNX load échoué: {e}")

        # InsightFace gère directement l'embedding (via detector)
        # Dans ce cas l'embedding est déjà dans DetectedFace.embedding
        self._initialized = True
        logger.info("Embedder: utilise InsightFace natif (via FaceAnalysis)")
        return True

    def embed(self, face_img: np.ndarray) -> Optional[np.ndarray]:
        """
        Génère un vecteur 512D normalisé à partir d'un crop de visage.

        Args:
            face_img: Image BGR du visage (n'importe quelle taille)

        Returns:
            np.ndarray shape (512,) normalisé L2, ou None si erreur
        """
        if not self._initialized:
            self.initialize()

        if face_img is None or face_img.size == 0:
            return None

        try:
            if self._session is not None:
                return self._embed_onnx(face_img)
            # Fallback: retourne embedding aléatoire normalisé (dev only)
            logger.warning("Pas de modèle ONNX — embedding simulé (dev mode)")
            return self._mock_embedding()
        except Exception as e:
            logger.error(f"Erreur embedding: {e}")
            return None

    def _embed_onnx(self, face_img: np.ndarray) -> np.ndarray:
        """Inférence ONNX directe"""
        # Preprocessing ArcFace standard
        img = cv2.resize(face_img, INPUT_SIZE)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32)
        img = (img - 127.5) / 128.0
        img = img.transpose(2, 0, 1)          # HWC → CHW
        img = np.expand_dims(img, axis=0)      # → (1, 3, 112, 112)

        input_name = self._session.get_inputs()[0].name
        output = self._session.run(None, {input_name: img})[0]
        embedding = output[0]

        return self.normalize(embedding)

    @staticmethod
    def normalize(embedding: np.ndarray) -> np.ndarray:
        """Normalisation L2 pour comparaison cosinus"""
        norm = np.linalg.norm(embedding)
        if norm == 0:
            return embedding
        return embedding / norm

    @staticmethod
    def _mock_embedding() -> np.ndarray:
        """Embedding aléatoire normalisé — dev/test uniquement"""
        emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        return emb / np.linalg.norm(emb)

    @staticmethod
    def cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Similarité cosinus entre deux embeddings normalisés"""
        return float(np.dot(emb1, emb2))

    @staticmethod
    def euclidean_distance(emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Distance euclidienne entre deux embeddings"""
        return float(np.linalg.norm(emb1 - emb2))


# Singleton
_embedder: Optional[FaceEmbedder] = None


def get_embedder() -> FaceEmbedder:
    global _embedder
    if _embedder is None:
        from config import get_settings
        s = get_settings()
        model_path = f"{s.model_dir}/arcface_r100.onnx"
        _embedder = FaceEmbedder(model_path=model_path, gpu=s.gpu_enabled)
        _embedder.initialize()
    return _embedder
