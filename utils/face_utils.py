import math
import logging

logger = logging.getLogger(__name__)

FACE_SIMILARITY_THRESHOLD = 0.45  # LBP descriptor Euclidean distance threshold

def calculate_euclidean_distance(vec1, vec2) -> float:
    """
    Calculate Euclidean distance between two face embedding vectors.
    """
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return float('inf')
        
    try:
        sum_sq = sum((float(a) - float(b)) ** 2 for a, b in zip(vec1, vec2))
        return math.sqrt(sum_sq)
    except Exception as e:
        logger.error(f"Error calculating Euclidean distance: {e}")
        return float('inf')

def calculate_cosine_similarity(vec1, vec2) -> float:
    """
    Calculate Cosine similarity between two face embedding vectors.
    """
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    try:
        dot = sum(float(a) * float(b) for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(float(a) ** 2 for a in vec1))
        norm2 = math.sqrt(sum(float(b) ** 2 for b in vec2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)
    except Exception as e:
        logger.error(f"Error calculating Cosine similarity: {e}")
        return 0.0

def compare_face_descriptors(stored_descriptor, candidate_descriptor, threshold=FACE_SIMILARITY_THRESHOLD) -> dict:
    """
    Compare candidate face descriptor against stored face descriptor.
    Returns dict with is_match (bool), distance (float), confidence (float).
    """
    if not stored_descriptor or not candidate_descriptor:
        return {
            "is_match": False,
            "distance": float('inf'),
            "confidence": 0.0,
            "reason": "Missing face descriptor"
        }
        
    dist = calculate_euclidean_distance(stored_descriptor, candidate_descriptor)
    cosine_sim = calculate_cosine_similarity(stored_descriptor, candidate_descriptor)
    
    # Match condition: Euclidean distance <= threshold AND Cosine similarity >= 0.40
    is_match = (dist <= threshold) and (cosine_sim >= 0.40)
    
    if dist < float('inf'):
        confidence = max(0.0, min(100.0, (1.0 - (dist / (threshold * 1.5))) * 100.0))
    else:
        confidence = 0.0
        
    return {
        "is_match": is_match,
        "distance": round(dist, 4),
        "cosine_similarity": round(cosine_sim, 4),
        "confidence": round(confidence, 1),
        "threshold": threshold
    }
