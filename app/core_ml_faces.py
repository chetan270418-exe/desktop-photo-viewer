"""
Memory Explorer — Face Detection and Clustering

Uses OpenCV's YuNet for face detection and SFace for face recognition embeddings.
Automatically downloads the required ONNX models.
"""

import logging
import os
from pathlib import Path
import numpy as np
import cv2
import requests
from sklearn.cluster import DBSCAN

from app.core_models import APP_DIR

logger = logging.getLogger(__name__)

MODELS_DIR = APP_DIR / "data" / "models"
YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
SFACE_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"

YUNET_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"


def _download_file(url: str, dest: Path) -> None:
    if dest.exists():
        return
    logger.info(f"Downloading ML model: {dest.name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    logger.info(f"Downloaded {dest.name} successfully.")


class FaceAnalyzer:
    def __init__(self):
        self._detector = None
        self._recognizer = None
        self._initialized = False

    def _initialize(self):
        if self._initialized:
            return
            
        try:
            _download_file(YUNET_URL, YUNET_PATH)
            _download_file(SFACE_URL, SFACE_PATH)
            
            # YuNet expects an input size, we'll set it dynamically during inference
            self._detector = cv2.FaceDetectorYN.create(
                str(YUNET_PATH),
                "",
                (320, 320),
                score_threshold=0.8,
                nms_threshold=0.3,
                top_k=5000
            )
            
            self._recognizer = cv2.FaceRecognizerSF.create(str(SFACE_PATH), "")
            self._initialized = True
            logger.info("FaceAnalyzer models initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize FaceAnalyzer: {e}")
            raise

    def extract_faces(self, image_path: str) -> list[dict]:
        """
        Reads an image and extracts bounding boxes and embeddings for all faces.
        Returns a list of dicts: {"box": [x, y, w, h], "embedding": list[float]}
        """
        self._initialize()
        
        # Read image properly handling unicode paths on Windows
        img_array = np.fromfile(image_path, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if img is None:
            logger.warning(f"Failed to decode image for face detection: {image_path}")
            return []
            
        height, width, _ = img.shape
        self._detector.setInputSize((width, height))
        
        # Detect faces
        _, faces = self._detector.detect(img)
        if faces is None:
            return []
            
        results = []
        for face in faces:
            # box is [x, y, w, h]
            box = face[0:4].astype(int)
            x, y, w, h = box
            
            # Ensure box is within image bounds
            if x < 0 or y < 0 or x + w > width or y + h > height:
                continue
                
            # Extract features (embedding)
            try:
                # SFace requires the face data as detected by YuNet
                # face is a 15-element array: [x,y,w,h, left_eye_x, left_eye_y, right_eye_x, right_eye_y, nose_x, nose_y, mouth_left_x, mouth_left_y, mouth_right_x, mouth_right_y, score]
                # alignCrop takes the image and the face array
                aligned_face = self._recognizer.alignCrop(img, face)
                feature = self._recognizer.feature(aligned_face)
                # Feature is a (1, 128) float32 array
                embedding = feature[0].tolist()
                
                results.append({
                    "box": [int(x), int(y), int(w), int(h)],
                    "embedding": embedding
                })
            except Exception as e:
                logger.warning(f"Failed to extract face embedding from {image_path}: {e}")
                
        return results

def cluster_embeddings(embeddings: list[list[float]], eps: float = 0.5, min_samples: int = 2) -> list[int]:
    """
    Takes a list of 128D embeddings and returns a list of cluster IDs (person IDs).
    Returns -1 for outliers (unrecognized/unique faces).
    """
    if not embeddings:
        return []
        
    X = np.array(embeddings)
    # Cosine distance is standard for face embeddings. 
    # For SFace, typical threshold is around 0.364 according to OpenCV docs.
    # We use eps=0.36 here.
    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine').fit(X)
    return clustering.labels_.tolist()
