"""
Détection faciale — InsightFace + OpenCV
Détecte visages, landmarks 68pts, bounding boxes, qualité
"""
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger

try:
    import insightface
    from insightface.app import FaceAnalysis
    INSIGHTFACE_OK = True
except ImportError:
    INSIGHTFACE_OK = False
    logger.warning("InsightFace non disponible — mode OpenCV dlib uniquement")


@dataclass
class DetectedFace:
    """Résultat d'une détection faciale"""
    bbox: list[int]              # [x, y, w, h]
    confidence: float
    landmarks: Optional[np.ndarray] = None   # (5, 2) ou (68, 2)
    embedding: Optional[np.ndarray] = None   # 512D si InsightFace
    quality_score: float = 0.0
    age: Optional[int] = None
    gender: Optional[str] = None
    face_img: Optional[np.ndarray] = None    # crop aligné
    track_id: Optional[int] = None


class FaceDetector:
    """
    Détecteur facial principal basé sur InsightFace.
    Détecte plusieurs visages simultanément, retourne
    bounding boxes + landmarks + score de confiance.
    """

    def __init__(self,
                 model_name: str = "buffalo_l",
                 gpu: bool = False,
                 max_faces: int = 10,
                 det_size: tuple = (640, 640)):

        self.gpu = gpu
        self.max_faces = max_faces
        self.det_size = det_size
        self.model_name = model_name
        self._app = None
        self._initialized = False

        # Cascade Haar en fallback
        self._haar = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

    def initialize(self) -> bool:
        if self._initialized:
            return True

        if INSIGHTFACE_OK:
            try:
                ctx = 0 if self.gpu else -1
                self._app = FaceAnalysis(
                    name=self.model_name,
                    providers=["CUDAExecutionProvider" if self.gpu
                               else "CPUExecutionProvider"]
                )
                self._app.prepare(ctx_id=ctx, det_size=self.det_size)
                self._initialized = True
                logger.success(f"FaceDetector initialisé — modèle: {self.model_name} | GPU: {self.gpu}")
                return True
            except Exception as e:
                logger.error(f"InsightFace init échoué: {e}")

        # Fallback Haar
        self._initialized = True
        logger.warning("Fallback: détection Haar Cascade (moins précis)")
        return True

    def detect(self, frame: np.ndarray) -> list[DetectedFace]:
        """
        Détecte tous les visages dans une frame.

        Args:
            frame: Image BGR numpy array

        Returns:
            Liste de DetectedFace triée par confiance décroissante
        """
        if not self._initialized:
            self.initialize()

        if frame is None or frame.size == 0:
            return []

        # ---- InsightFace (mode principal) ----
        if self._app is not None:
            return self._detect_insightface(frame)

        # ---- Fallback Haar ----
        return self._detect_haar(frame)

    def _detect_insightface(self, frame: np.ndarray) -> list[DetectedFace]:
        """Détection avec InsightFace — retourne bbox + landmarks + embedding"""
        faces_raw = self._app.get(frame)
        results = []

        for face in faces_raw[:self.max_faces]:
            x1, y1, x2, y2 = face.bbox.astype(int)
            bbox = [x1, y1, x2 - x1, y2 - y1]

            # Crop du visage aligné
            face_img = self._crop_face(frame, x1, y1, x2, y2)

            # Score de qualité basé sur taille + netteté
            quality = self._compute_quality(face_img, face.det_score)

            results.append(DetectedFace(
                bbox=bbox,
                confidence=float(face.det_score),
                landmarks=face.kps if hasattr(face, "kps") else None,
                embedding=face.embedding if hasattr(face, "embedding") else None,
                quality_score=quality,
                age=int(face.age) if hasattr(face, "age") and face.age else None,
                gender="M" if hasattr(face, "gender") and face.gender == 1 else "F",
                face_img=face_img,
            ))

        results.sort(key=lambda f: f.confidence, reverse=True)
        return results

    def _detect_haar(self, frame: np.ndarray) -> list[DetectedFace]:
        """Détection fallback avec Haar Cascade"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._haar.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
        )
        results = []
        for (x, y, w, h) in faces[:self.max_faces]:
            face_img = frame[y:y+h, x:x+w]
            results.append(DetectedFace(
                bbox=[x, y, w, h],
                confidence=0.75,
                quality_score=self._compute_quality(face_img, 0.75),
                face_img=face_img,
            ))
        return results

    @staticmethod
    def _crop_face(frame: np.ndarray,
                   x1: int, y1: int, x2: int, y2: int,
                   padding: float = 0.1) -> np.ndarray:
        """Crop avec padding autour du visage"""
        h, w = frame.shape[:2]
        pad_x = int((x2 - x1) * padding)
        pad_y = int((y2 - y1) * padding)
        x1c = max(0, x1 - pad_x)
        y1c = max(0, y1 - pad_y)
        x2c = min(w, x2 + pad_x)
        y2c = min(h, y2 + pad_y)
        return frame[y1c:y2c, x1c:x2c]

    @staticmethod
    def _compute_quality(face_img: np.ndarray, det_score: float) -> float:
        """
        Score qualité combiné : netteté (Laplacian) + taille + score détection.
        Retourne valeur entre 0.0 et 1.0.
        """
        if face_img is None or face_img.size == 0:
            return 0.0

        # Netteté via variance du Laplacien
        gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness_score = min(1.0, sharpness / 500.0)

        # Score taille (min 80px pour bonne qualité)
        size_score = min(1.0, min(face_img.shape[:2]) / 80.0)

        # Combinaison pondérée
        quality = 0.4 * float(det_score) + 0.4 * sharpness_score + 0.2 * size_score
        return round(min(1.0, quality), 3)

    def draw_detections(self,
                        frame: np.ndarray,
                        faces: list[DetectedFace],
                        show_quality: bool = True) -> np.ndarray:
        """
        Dessine les bounding boxes sur la frame (debug / preview).
        """
        out = frame.copy()
        for face in faces:
            x, y, w, h = face.bbox
            color = (0, 255, 0) if face.confidence > 0.7 else (0, 165, 255)

            cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)

            label = f"{face.confidence:.2f}"
            if show_quality:
                label += f" Q:{face.quality_score:.2f}"
            if face.age:
                label += f" {face.age}{face.gender}"

            cv2.putText(out, label, (x, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            # Landmarks
            if face.landmarks is not None:
                for pt in face.landmarks:
                    cv2.circle(out, (int(pt[0]), int(pt[1])), 2, (255, 0, 0), -1)

        return out


# Singleton global
_detector: Optional[FaceDetector] = None


def get_detector() -> FaceDetector:
    global _detector
    if _detector is None:
        from config import get_settings
        s = get_settings()
        _detector = FaceDetector(
            model_name=s.face_detection_model,
            gpu=s.gpu_enabled,
            max_faces=s.max_faces_per_frame,
        )
        _detector.initialize()
    return _detector
