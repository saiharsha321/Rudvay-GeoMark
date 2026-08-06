import os
import json
import uuid
import logging
from datetime import datetime, timezone
from config import Config

logger = logging.getLogger(__name__)

# Global variables for DB, Bucket, and Auth
db = None
bucket = None
auth = None
IS_FIREBASE_REAL = False

def init_firebase():
    global db, bucket, auth, IS_FIREBASE_REAL
    cred_path = Config.FIREBASE_CREDENTIALS_PATH
    
    if os.environ.get('FORCE_LOCAL_DB', '').lower() not in ['1', 'true'] and os.path.exists(cred_path):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore, storage, auth as fb_auth
            
            if not firebase_admin._apps:
                cred = credentials.Certificate(cred_path)
                b_name = (Config.FIREBASE_STORAGE_BUCKET or "").strip()
                if b_name.endswith('.firebasestorage.app'):
                    b_name = b_name.replace('.firebasestorage.app', '.appspot.com')
                firebase_admin.initialize_app(cred, {
                    'storageBucket': b_name
                })
            
            db = firestore.client()
            auth = fb_auth
            try:
                bucket = storage.bucket()
            except Exception as b_err:
                logger.warning(f"Cloud Storage bucket binding warning: {b_err}. Falling back to LocalStorageEngine.")
                bucket = LocalStorageEngine()
                
            # Verify active Firestore API access
            try:
                list(db.collection('_health_check').limit(1).stream())
                IS_FIREBASE_REAL = True
                logger.info("Successfully connected to real Firebase Firestore, Auth & Storage.")
                return
            except Exception as conn_err:
                logger.warning(f"Firebase credentials loaded, but Firestore API access failed: {conn_err}. Falling back to local engine.")
        except Exception as e:
            logger.warning(f"Error loading Firebase credentials from {cred_path}: {e}. Initializing local fallback driver.")
            
    logger.info("Initializing high-performance local Firestore & Storage database fallback engine.")
    db = LocalFirestoreEngine()
    bucket = LocalStorageEngine()
    auth = LocalAuthEngine()
    IS_FIREBASE_REAL = False

def create_firebase_user(email: str, password: str = None, display_name: str = None) -> dict:
    """
    Create user in Firebase Auth or local auth emulator.
    Returns dict with uid, email, display_name.
    """
    if IS_FIREBASE_REAL and auth:
        try:
            user = auth.create_user(
                email=email,
                password=password or "DefaultPass123!",
                display_name=display_name or email.split('@')[0]
            )
            return {
                "uid": user.uid,
                "email": user.email,
                "display_name": user.display_name
            }
        except Exception as e:
            logger.warning(f"Firebase Auth user creation warning/fallback: {e}")
            # If user already exists or auth fails, return existing metadata
            try:
                existing = auth.get_user_by_email(email)
                return {"uid": existing.uid, "email": existing.email, "display_name": existing.display_name}
            except Exception:
                pass

    # Fallback/Local uid generation
    mock_uid = f"uid_{uuid.uuid4().hex[:10]}"
    return {"uid": mock_uid, "email": email, "display_name": display_name or email.split('@')[0]}

def verify_firebase_token(id_token: str) -> dict:
    """
    Verify Firebase Auth ID Token.
    Returns decoded token dictionary or None.
    """
    if IS_FIREBASE_REAL and auth:
        try:
            return auth.verify_id_token(id_token)
        except Exception as e:
            logger.error(f"Error verifying Firebase ID token: {e}")
            return None
    return {"uid": "mock_uid", "email": "mock@local.domain"}

class LocalAuthEngine:
    def create_user(self, email, password=None, display_name=None):
        class UserRecord:
            def __init__(self, email, display_name):
                self.uid = f"user_{uuid.uuid4().hex[:8]}"
                self.email = email
                self.display_name = display_name or email
        return UserRecord(email, display_name)

    def get_user_by_email(self, email):
        class UserRecord:
            def __init__(self, email):
                self.uid = f"user_{uuid.uuid4().hex[:8]}"
                self.email = email
                self.display_name = email
        return UserRecord(email)


class DocumentSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data or {}
        self.exists = bool(data)

    def to_dict(self):
        return dict(self._data)

    def get(self, field):
        return self._data.get(field)

class DocumentReference:
    def __init__(self, collection_ref, doc_id):
        self.collection_ref = collection_ref
        self.id = doc_id

    def get(self):
        data = self.collection_ref.storage_engine.get_doc(self.collection_ref.path, self.id)
        return DocumentSnapshot(self.id, data)

    def set(self, data, merge=False):
        self.collection_ref.storage_engine.set_doc(self.collection_ref.path, self.id, data, merge=merge)

    def update(self, data):
        self.collection_ref.storage_engine.update_doc(self.collection_ref.path, self.id, data)

    def delete(self):
        self.collection_ref.storage_engine.delete_doc(self.collection_ref.path, self.id)

    def collection(self, sub_name):
        sub_path = f"{self.collection_ref.path}/{self.id}/{sub_name}"
        return CollectionReference(self.collection_ref.storage_engine, sub_path)

class CollectionReference:
    def __init__(self, storage_engine, path):
        self.storage_engine = storage_engine
        self.path = path

    def document(self, doc_id=None):
        if not doc_id:
            doc_id = str(uuid.uuid4())
        return DocumentReference(self, doc_id)

    def add(self, data):
        doc_id = str(uuid.uuid4())
        doc_ref = self.document(doc_id)
        doc_ref.set(data)
        return None, doc_ref

    def get(self):
        docs_data = self.storage_engine.get_all_docs(self.path)
        return [DocumentSnapshot(doc_id, data) for doc_id, data in docs_data.items()]

    def stream(self):
        return self.get()

    def where(self, field, op, value):
        docs_data = self.storage_engine.query_docs(self.path, field, op, value)
        return QueryReference(self.storage_engine, self.path, docs_data)

class QueryReference:
    def __init__(self, storage_engine, path, docs_data):
        self.storage_engine = storage_engine
        self.path = path
        self.docs_data = docs_data

    def get(self):
        return [DocumentSnapshot(doc_id, data) for doc_id, data in self.docs_data.items()]

    def stream(self):
        return self.get()

    def where(self, field, op, value):
        filtered = {}
        for doc_id, data in self.docs_data.items():
            val = data.get(field)
            match = False
            if op == '==' and val == value:
                match = True
            elif op == '!=' and val != value:
                match = True
            elif op == '>' and val is not None and val > value:
                match = True
            elif op == '>=' and val is not None and val >= value:
                match = True
            elif op == '<' and val is not None and val < value:
                match = True
            elif op == '<=' and val is not None and val <= value:
                match = True
            elif op == 'in' and val in value:
                match = True
            if match:
                filtered[doc_id] = data
        return QueryReference(self.storage_engine, self.path, filtered)

class LocalFirestoreEngine:
    def __init__(self):
        self.db_file = os.path.join(Config.BASE_DIR, 'local_db.json')
        self._data = {}
        self.load()
        self._seed_default_data()

    def load(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            except Exception as e:
                logger.error(f"Error loading local_db.json: {e}")
                self._data = {}

    def save(self):
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving local_db.json: {e}")

    def collection(self, name):
        return CollectionReference(self, name)

    def get_doc(self, path, doc_id):
        return self._data.get(path, {}).get(doc_id)

    def set_doc(self, path, doc_id, data, merge=False):
        if path not in self._data:
            self._data[path] = {}
        if merge and doc_id in self._data[path]:
            self._data[path][doc_id].update(data)
        else:
            self._data[path][doc_id] = data
        self.save()

    def update_doc(self, path, doc_id, data):
        if path in self._data and doc_id in self._data[path]:
            self._data[path][doc_id].update(data)
            self.save()

    def delete_doc(self, path, doc_id):
        if path in self._data and doc_id in self._data[path]:
            del self._data[path][doc_id]
            self.save()

    def get_all_docs(self, path):
        return self._data.get(path, {})

    def query_docs(self, path, field, op, value):
        all_docs = self.get_all_docs(path)
        filtered = {}
        for doc_id, data in all_docs.items():
            val = data.get(field)
            match = False
            if op == '==' and val == value:
                match = True
            elif op == '!=' and val != value:
                match = True
            elif op == '>' and val is not None and val > value:
                match = True
            elif op == '>=' and val is not None and val >= value:
                match = True
            elif op == '<' and val is not None and val < value:
                match = True
            elif op == '<=' and val is not None and val <= value:
                match = True
            elif op == 'in' and isinstance(value, (list, tuple, set)) and val in value:
                match = True
            if match:
                filtered[doc_id] = data
        return filtered

    def _seed_default_data(self):
        # Default Super Admin
        admin_id = "admin_super"
        if not self.get_doc("super_admins", admin_id):
            self.set_doc("super_admins", admin_id, {
                "admin_id": admin_id,
                "email": Config.ADMIN_USERNAME,
                "password": Config.ADMIN_PASSWORD,
                "role": "SUPER_ADMIN",
                "created_at": datetime.now(timezone.utc).isoformat()
            })

        # Default Plans
        plans_data = [
            {
                "plan_id": "plan_starter",
                "name": "Starter Business",
                "price": 999.0,
                "max_employees": 15,
                "billing_cycle": "monthly",
                "features": ["Geo-Fencing", "Live Camera Verification", "Basic Shifts", "Real-Time Alerts"],
                "status": "active",
                "razorpay_plan_id": "plan_m_99900"
            },
            {
                "plan_id": "plan_pro",
                "name": "Professional Enterprise",
                "price": 2499.0,
                "max_employees": 50,
                "billing_cycle": "monthly",
                "features": ["Geo-Fencing", "WebRTC Camera", "Unlimited Shifts", "Manual Overrides", "CSV Exports", "Razorpay Billing"],
                "status": "active",
                "razorpay_plan_id": "plan_m_249900"
            },
            {
                "plan_id": "plan_unlimited",
                "name": "Unlimited Corporate",
                "price": 4999.0,
                "max_employees": 500,
                "billing_cycle": "monthly",
                "features": ["Dedicated Account Manager", "Unlimited Employees", "Custom Geofence Radius", "Webhook Automation"],
                "status": "active",
                "razorpay_plan_id": "plan_m_499900"
            }
        ]
        for plan in plans_data:
            if not self.get_doc("plans", plan["plan_id"]):
                self.set_doc("plans", plan["plan_id"], plan)

class LocalStorageEngine:
    def blob(self, blob_path):
        return LocalBlob(blob_path)

class LocalBlob:
    def __init__(self, blob_path):
        self.blob_path = blob_path
        self.public_url = f"/static/uploads/{os.path.basename(blob_path)}"
        
    def upload_from_string(self, content_bytes, content_type='image/jpeg'):
        uploads_dir = os.path.join(Config.BASE_DIR, 'static', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        file_path = os.path.join(uploads_dir, os.path.basename(self.blob_path))
        with open(file_path, 'wb') as f:
            f.write(content_bytes)

    def upload_from_filename(self, filename):
        uploads_dir = os.path.join(Config.BASE_DIR, 'static', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        file_path = os.path.join(uploads_dir, os.path.basename(self.blob_path))
        with open(filename, 'rb') as src, open(file_path, 'wb') as dst:
            dst.write(src.read())

    def make_public(self):
        pass

# Initialize Firebase on import
init_firebase()
