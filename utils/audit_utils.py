import uuid
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

def log_audit_action(tenant_id: str, actor_email: str, action: str, target: str, details: dict = None):
    """
    Creates an immutable audit log record for administrative actions.
    """
    if not tenant_id:
        return
        
    try:
        from firebase_config import db
        now_iso = datetime.now(timezone.utc).isoformat()
        log_id = f"audit_{uuid.uuid4().hex[:10]}"
        
        log_data = {
            "log_id": log_id,
            "tenant_id": tenant_id,
            "actor_email": actor_email or "System/Admin",
            "action": action,
            "target": target,
            "details": details or {},
            "timestamp": now_iso
        }
        
        db.collection(f"tenants/{tenant_id}/audit_logs").document(log_id).set(log_data)
        logger.info(f"Audit Log Recorded [{action}] by {actor_email} on target '{target}'")
    except Exception as e:
        logger.error(f"Failed to record audit log: {e}")
