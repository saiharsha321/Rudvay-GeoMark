import math

# Earth radius in meters
EARTH_RADIUS_METERS = 6371000.0

def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate the great-circle distance between two points on the Earth's surface
    using the Haversine formula. Returns distance in meters.
    """
    try:
        lat1, lng1, lat2, lng2 = map(float, [lat1, lng1, lat2, lng2])
    except (ValueError, TypeError):
        return float('inf')

    # Convert degrees to radians
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    # Haversine formula
    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    
    # Clamp 'a' between 0.0 and 1.0 to prevent floating point inaccuracy domain errors in asin
    a = max(0.0, min(1.0, a))
    
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    distance = EARTH_RADIUS_METERS * c

    return round(distance, 2)

def check_geofence_violation(emp_lat: float, emp_lng: float, fence_lat: float, fence_lng: float, radius_meters: float) -> dict:
    """
    Checks whether employee coordinates fall within the specified geofence radius.
    Returns dict with distance_meters, radius_meters, and is_outside (boolean).
    """
    dist = haversine_distance(emp_lat, emp_lng, fence_lat, fence_lng)
    is_outside = dist > radius_meters
    return {
        "distance_meters": dist,
        "radius_meters": radius_meters,
        "is_outside": is_outside
    }
