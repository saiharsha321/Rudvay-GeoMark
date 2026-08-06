import json
import logging
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify
from firebase_config import db
from utils.razorpay_utils import verify_webhook_signature

logger = logging.getLogger(__name__)
api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/tenant/<tenant_id>/geofence', methods=['GET'])
def get_tenant_geofence(tenant_id):
    tenant_doc = db.collection('tenants').document(tenant_id).get()
    if not tenant_doc.exists:
        return jsonify({'error': 'Tenant not found'}), 404
        
    t_data = tenant_doc.to_dict()
    geofence = t_data.get('geofence', {})
    return jsonify({'tenant_id': tenant_id, 'geofence': geofence, 'status': t_data.get('status')})

@api_bp.route('/webhooks/razorpay', methods=['POST'])
def razorpay_webhook():
    signature = request.headers.get('X-Razorpay-Signature', '')
    raw_body = request.data
    
    # Cryptographic signature verification
    if not verify_webhook_signature(raw_body, signature):
        logger.warning("Razorpay Webhook signature verification failed!")
        return jsonify({'status': 'error', 'message': 'Invalid signature'}), 400
        
    try:
        event_payload = json.loads(raw_body.decode('utf-8'))
        event_type = event_payload.get('event')
        payload_entity = event_payload.get('payload', {})
        
        logger.info(f"Processing Razorpay webhook event: {event_type}")
        
        if event_type in ['subscription.charged', 'payment.captured', 'payment.authorized']:
            sub_entity = payload_entity.get('subscription', {}).get('entity', {})
            payment_entity = payload_entity.get('payment', {}).get('entity', {})
            
            sub_id = sub_entity.get('id') or payment_entity.get('subscription_id')
            email = payment_entity.get('email')
            
            # Find matching tenant by subscription_id or owner_email
            matching_tenants = []
            if sub_id:
                matching_tenants = db.collection('tenants').where('razorpay_subscription_id', '==', sub_id).get()
            if not matching_tenants and email:
                matching_tenants = db.collection('tenants').where('owner_email', '==', email).get()
                
            if matching_tenants:
                t_doc = matching_tenants[0]
                tenant_id = t_doc.id
                
                now_dt = datetime.now(timezone.utc)
                sub_end_dt = now_dt + timedelta(days=30) # Default monthly renewal
                
                db.collection('tenants').document(tenant_id).update({
                    'status': 'active',
                    'subscription_start': now_dt.isoformat(),
                    'subscription_end': sub_end_dt.isoformat(),
                    'last_payment_id': payment_entity.get('id')
                })
                logger.info(f"Tenant {tenant_id} subscription renewed & activated successfully.")
                
        elif event_type in ['subscription.halted', 'subscription.cancelled', 'payment.failed']:
            sub_entity = payload_entity.get('subscription', {}).get('entity', {})
            sub_id = sub_entity.get('id')
            
            if sub_id:
                tenants = db.collection('tenants').where('razorpay_subscription_id', '==', sub_id).get()
                if tenants:
                    tenant_id = tenants[0].id
                    db.collection('tenants').document(tenant_id).update({'status': 'blocked'})
                    logger.warning(f"Tenant {tenant_id} blocked due to event: {event_type}")
                    
        return jsonify({'status': 'ok', 'event': event_type}), 200
        
    except Exception as e:
        logger.error(f"Error processing webhook payload: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
