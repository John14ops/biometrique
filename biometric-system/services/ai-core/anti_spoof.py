"""
Anti-spoofing / Liveness Detection
Détecte photos imprimées, vidéos rejouées, deepfakes basiques.
Techniques : analyse texture, détection clignement, micro-mouvements.
"""
import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Deque
from collections import deque
from loguru import logger


@dataclass
class LivenessResult:
    is_live: bool
    score: float            # 0.0 (fake) → 1.0 (vivant)
    reason: str             # description du résultat
    blink_detected: bool = False
    texture_score: float = 0.0
    motion_score: float = 0.0


class LivenessDetector:
    """
    Détecteur de vivacité multi-couche :
    1. Analyse de texture (LBP — Local Binary Patterns)
    2. Détection de clignement (Eye Aspect Ratio)
    3. Micro-mouvements (optical flow entre frames)
    """

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self._eye_ar_history: Deque[float] = deque(maxlen=30)
        self._prev_frame: Optional[np.ndarray] = None
        self._blink_counter = 0
        self._blink_threshold_ar = 0.25    # EAR < seuil = clignement

        # Points faciaux pour les yeux (landmarks MediaPipe/InsightFace 5pts)
        # Indices dans les 5-landmarks InsightFace: 0=oeil_g, 1=oeil_d
        self._left_eye_idx  = [0]
        self._right_eye_idx = [1]

    def analyze(self,
                face_img: np.ndarray,
                landmarks: Optional[np.ndarray] = None,
                history_frames: Optional[list] = None) -> LivenessResult:
        """
        Analyse la vivacité d'un visage détecté.

        Args:
            face_img:  crop du visage BGR
            landmarks: points faciaux (5 ou 68 pts)
            history_frames: frames précédentes pour le mouvement

        Returns:
            LivenessResult avec score et diagnostics
        """
        scores = []
        details = []

        # --- 1. Analyse de texture LBP ---
        texture_score = self._texture_lbp(face_img)
        scores.append(texture_score)
        details.append(f"texture={texture_score:.2f}")

        # --- 2. Clignement (si landmarks 5pts disponibles) ---
        blink = False
        if landmarks is not None and len(landmarks) >= 2:
            blink = self._detect_blink(landmarks)
            blink_score = 1.0 if blink else 0.5   # bonus si clignement détecté
            scores.append(blink_score)
            details.append(f"blink={blink}")

        # --- 3. Micro-mouvements optiques ---
        motion_score = 0.5
        if self._prev_frame is not None and face_img is not None:
            motion_score = self._optical_flow_score(face_img)
            scores.append(motion_score)
            details.append(f"motion={motion_score:.2f}")

        self._prev_frame = face_img.copy() if face_img is not None else None

        # Score final pondéré
        if scores:
            final_score = float(np.mean(scores))
        else:
            final_score = 0.5

        is_live = final_score >= self.threshold

        return LivenessResult(
            is_live=is_live,
            score=round(final_score, 3),
            reason=" | ".join(details),
            blink_detected=blink,
            texture_score=texture_score,
            motion_score=motion_score,
        )

    def _texture_lbp(self, face_img: np.ndarray) -> float:
        """
        Local Binary Patterns — une vraie peau a plus de variance
        de texture qu'une photo imprimée ou un écran.
        Score élevé = probable peau réelle.
        """
        if face_img is None or face_img.size == 0:
            return 0.5

        gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (128, 128))

        # LBP simplifié via gradient magnitude
        grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        magnitude = np.sqrt(grad_x**2 + grad_y**2)

        # La variance de gradient est plus élevée pour vraie peau
        variance = np.var(magnitude)

        # Normalisation empirique (0→1)
        # Valeurs typiques: peau réelle ~800-2000, photo ~200-600
        score = min(1.0, variance / 1500.0)

        # Analyse fréquentielle (FFT) — photo a des patterns réguliers
        f = np.fft.fft2(gray)
        fshift = np.fft.fftshift(f)
        magnitude_spectrum = np.log(np.abs(fshift) + 1)
        freq_variance = np.var(magnitude_spectrum)
        freq_score = min(1.0, freq_variance / 15.0)

        return round(0.6 * score + 0.4 * freq_score, 3)

    def _detect_blink(self, landmarks: np.ndarray) -> bool:
        """
        Eye Aspect Ratio pour détecter le clignement.
        Avec landmarks 5pts InsightFace: [oeil_g, oeil_d, nez, coin_g, coin_d]
        """
        try:
            if len(landmarks) < 2:
                return False

            # Distance inter-oculaire approximative
            left_eye  = landmarks[0]
            right_eye = landmarks[1]
            inter_dist = np.linalg.norm(right_eye - left_eye)

            # EAR approximé (ratio hauteur/largeur oeil)
            # Avec 5pts on fait une estimation simplifiée
            ear = inter_dist / (np.linalg.norm(landmarks[3] - landmarks[4]) + 1e-6)
            self._eye_ar_history.append(ear)

            # Clignement = EAR chute sous le seuil
            if ear < self._blink_threshold_ar:
                self._blink_counter += 1
            elif self._blink_counter >= 2:
                self._blink_counter = 0
                return True  # Clignement complet détecté

            return False
        except Exception:
            return False

    def _optical_flow_score(self, current_frame: np.ndarray) -> float:
        """
        Micro-mouvements entre frames consécutives.
        Un visage vivant a des micro-mouvements (respiration, clignements).
        Une photo est statique → flow ≈ 0.
        """
        try:
            if self._prev_frame is None:
                return 0.5

            # Resize pour performance
            curr = cv2.resize(current_frame, (64, 64))
            prev = cv2.resize(self._prev_frame, (64, 64))

            curr_gray = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)
            prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)

            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, curr_gray, None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0
            )

            magnitude = np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)
            mean_motion = np.mean(magnitude)

            # Trop de mouvement (vidéo rejouée) ou pas assez (photo)
            # Zone idéale: 0.3 à 3.0 pixels/frame
            if mean_motion < 0.1:      # photo statique
                return 0.2
            elif mean_motion > 8.0:    # vidéo rejouée (trop de mouvement)
                return 0.3
            else:
                # Score maximal dans la zone "naturelle"
                return min(1.0, 0.3 + mean_motion / 4.0)

        except Exception as e:
            logger.debug(f"Optical flow error: {e}")
            return 0.5


# Singleton
_liveness: Optional[LivenessDetector] = None


def get_liveness_detector() -> LivenessDetector:
    global _liveness
    if _liveness is None:
        from config import get_settings
        s = get_settings()
        _liveness = LivenessDetector(threshold=s.liveness_threshold)
    return _liveness
