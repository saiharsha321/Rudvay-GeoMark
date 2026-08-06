import logging
import base64
from config import Config

logger = logging.getLogger(__name__)

# Try importing cloudinary SDK
try:
    import cloudinary
    import cloudinary.uploader
    HAS_CLOUDINARY_SDK = True
except ImportError:
    HAS_CLOUDINARY_SDK = False

def is_cloudinary_configured() -> bool:
    """
    Check if Cloudinary environment credentials are configured.
    """
    if not HAS_CLOUDINARY_SDK:
        return False
    name = (Config.CLOUDINARY_CLOUD_NAME or "").strip()
    key = (Config.CLOUDINARY_API_KEY or "").strip()
    secret = (Config.CLOUDINARY_API_SECRET or "").strip()
    
    placeholders = {'your_cloud_name_here', 'your_api_key_here', 'your_api_secret_here', ''}
    return bool(name and key and secret and name not in placeholders and key not in placeholders and secret not in placeholders)

def _init_cloudinary():
    if is_cloudinary_configured():
        try:
            cloudinary.config(
                cloud_name=(Config.CLOUDINARY_CLOUD_NAME or "").strip(),
                api_key=(Config.CLOUDINARY_API_KEY or "").strip(),
                api_secret=(Config.CLOUDINARY_API_SECRET or "").strip(),
                secure=True
            )
        except Exception as e:
            logger.warning(f"Error configuring Cloudinary SDK: {e}")

# Initialize configuration on import
_init_cloudinary()

def upload_to_cloudinary(photo_b64_or_bytes, folder: str = "punch_photos", public_id: str = None) -> str:
    """
    Upload image (base64 string or bytes) to Cloudinary.
    Returns secure HTTPS image URL or None if Cloudinary is unconfigured or upload fails.
    """
    if not is_cloudinary_configured():
        return None

    try:
        _init_cloudinary()
        
        # Prepare payload for Cloudinary uploader
        if isinstance(photo_b64_or_bytes, str):
            if not photo_b64_or_bytes.startswith("data:image"):
                photo_payload = f"data:image/jpeg;base64,{photo_b64_or_bytes}"
            else:
                photo_payload = photo_b64_or_bytes
        elif isinstance(photo_b64_or_bytes, bytes):
            photo_payload = photo_b64_or_bytes
        else:
            return None

        upload_options = {
            "folder": folder,
            "resource_type": "image"
        }
        if public_id:
            upload_options["public_id"] = public_id

        res = cloudinary.uploader.upload(photo_payload, **upload_options)
        secure_url = res.get("secure_url") or res.get("url")
        logger.info(f"Successfully uploaded image to Cloudinary: {secure_url}")
        return secure_url
    except Exception as e:
        logger.error(f"Cloudinary image upload failed: {e}")
        return None
