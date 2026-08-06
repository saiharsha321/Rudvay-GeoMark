import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Firebase Settings
    FIREBASE_CREDENTIALS_PATH = os.environ.get('FIREBASE_CREDENTIALS', os.path.join(BASE_DIR, 'firebase_key.json'))
    FIREBASE_STORAGE_BUCKET = os.environ.get('FIREBASE_STORAGE_BUCKET', 'your-app-id.appspot.com')
    FIREBASE_API_KEY = os.environ.get('FIREBASE_API_KEY', 'YOUR_FIREBASE_API_KEY')
    FIREBASE_AUTH_DOMAIN = os.environ.get('FIREBASE_AUTH_DOMAIN', 'your-app-id.firebaseapp.com')
    FIREBASE_PROJECT_ID = os.environ.get('FIREBASE_PROJECT_ID', 'your-app-id')
    FIREBASE_MESSAGING_SENDER_ID = os.environ.get('FIREBASE_MESSAGING_SENDER_ID', '1234567890')
    FIREBASE_APP_ID = os.environ.get('FIREBASE_APP_ID', '1:1234567890:web:abcdef123456')
    FIREBASE_MEASUREMENT_ID = os.environ.get('FIREBASE_MEASUREMENT_ID', 'G-XXXXXXXXXX')
    
    # Local fallback uploads folder (when Firebase credentials are not provided)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    
    # Razorpay Settings
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', 'rzp_test_geofence12345').strip()
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', 'secret_geofence_rzp_67890').strip()
    RAZORPAY_WEBHOOK_SECRET = os.environ.get('RAZORPAY_WEBHOOK_SECRET', 'whsec_geofence_webhook_key').strip()
    
    # Cloudinary Settings
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', '').strip()
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', '').strip()
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', '').strip()
    
    # Super Admin credentials
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin@system.local')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'SuperAdminPassword123!')

    # Session Cookie Security & Protection
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get('USE_HTTPS', '').lower() in ['1', 'true'] or bool(os.environ.get('VERCEL'))
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400  # 24 Hours


