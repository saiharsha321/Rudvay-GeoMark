import hmac
import hashlib
import json
import logging

try:
    import razorpay
except ImportError:
    razorpay = None

from config import Config

logger = logging.getLogger(__name__)

def get_razorpay_client():
    if razorpay and Config.RAZORPAY_KEY_ID and Config.RAZORPAY_KEY_SECRET:
        try:
            return razorpay.Client(auth=(Config.RAZORPAY_KEY_ID, Config.RAZORPAY_KEY_SECRET))
        except Exception as e:
            logger.warning(f"Failed to initialize Razorpay SDK client: {e}")
    return None

def verify_webhook_signature(raw_body: bytes, signature: str, secret: str = None) -> bool:
    """
    Cryptographically verifies Razorpay webhook signature using HMAC SHA256.
    """
    secret = secret or Config.RAZORPAY_WEBHOOK_SECRET
    if not secret or not signature:
        return False
        
    try:
        expected_signature = hmac.new(
            key=secret.encode('utf-8'),
            msg=raw_body,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {e}")
        return False

def verify_payment_signature(payment_id: str, subscription_id: str, signature: str, secret: str = None) -> bool:
    """
    Verifies Razorpay subscription checkout payment signature.
    msg = payment_id + '|' + subscription_id
    """
    secret = secret or Config.RAZORPAY_KEY_SECRET
    if not secret or not signature:
        return False
        
    try:
        msg = f"{payment_id}|{subscription_id}".encode('utf-8')
        expected_signature = hmac.new(
            key=secret.encode('utf-8'),
            msg=msg,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
    except Exception as e:
        logger.error(f"Error verifying payment signature: {e}")
        return False

def create_razorpay_plan_api(name: str, amount_in_rupees: float, period: str = "monthly", max_employees: int = 50) -> dict:
    """
    Sync plan creation with Razorpay Plan API if client available, or return local plan metadata.
    """
    client = get_razorpay_client()
    amount_in_paise = int(amount_in_rupees * 100)
    
    period_str = "monthly" if period.lower() in ["monthly", "month"] else "yearly"
    interval = 1
    
    plan_data = {
        "period": period_str,
        "interval": interval,
        "item": {
            "name": name,
            "amount": amount_in_paise,
            "currency": "INR",
            "description": f"GeoFence Attendance Plan ({max_employees} employees)"
        }
    }
    
    if client:
        try:
            rzp_plan = client.plan.create(data=plan_data)
            return {
                "success": True,
                "razorpay_plan_id": rzp_plan.get("id"),
                "plan_data": rzp_plan
            }
        except Exception as e:
            logger.warning(f"Razorpay API call failed: {e}. Falling back to generated plan ID.")
            
    # Mock/Fallback ID generation
    mock_plan_id = f"plan_{period_str[:1]}_{amount_in_paise}"
    return {
        "success": True,
        "razorpay_plan_id": mock_plan_id,
        "plan_data": plan_data
    }

def create_subscription_api(plan_id: str, total_count: int = 12) -> dict:
    """
    Create a subscription for a tenant using Razorpay API.
    """
    client = get_razorpay_client()
    if client:
        try:
            sub = client.subscription.create({
                "plan_id": plan_id,
                "total_count": total_count,
                "quantity": 1,
                "customer_notify": 1
            })
            return {
                "success": True,
                "subscription_id": sub.get("id"),
                "short_url": sub.get("short_url")
            }
        except Exception as e:
            logger.warning(f"Razorpay Subscription creation error: {e}")
            
    mock_sub_id = f"sub_mock_{hashlib.md5(plan_id.encode()).hexdigest()[:10]}"
    return {
        "success": True,
        "subscription_id": mock_sub_id,
        "short_url": f"/portal/billing?mock_checkout=true&sub_id={mock_sub_id}"
    }
