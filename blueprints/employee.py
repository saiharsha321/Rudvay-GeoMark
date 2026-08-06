import os
import uuid
import base64
import logging
from datetime import datetime, timezone, date
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session
from config import Config
from firebase_config import db, bucket, IS_FIREBASE_REAL
from utils.cloudinary_utils import upload_to_cloudinary, is_cloudinary_configured
from utils.geo import check_geofence_violation, haversine_distance
from utils.time_utils import get_ist_now, get_ist_today_str, get_ist_iso

from utils.face_utils import compare_face_descriptors, FACE_SIMILARITY_THRESHOLD
import json
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
employee_bp = Blueprint('employee', __name__, url_prefix='/punch')
upload_executor = ThreadPoolExecutor(max_workers=4)

def process_async_photo_upload(tenant_id, employee_id, att_id, punch_type, photo_b64, now_dt):
    """Background task to upload photo to Cloudinary/Firebase Storage and update attendance record."""
    try:
        photo_url = ""
        c_url = upload_to_cloudinary(photo_b64, folder=f"punch_photos/{tenant_id}/{employee_id}")
        if c_url:
            photo_url = c_url
        else:
            try:
                encoded = photo_b64.split(',', 1)[1] if ',' in photo_b64 else photo_b64
                img_bytes = base64.b64decode(encoded)
                timestamp = now_dt.strftime("%Y%m%d_%H%M%S")
                blob_path = f"punch_photos/{tenant_id}/{employee_id}/{timestamp}_{punch_type}.jpg"
                
                if bucket and hasattr(bucket, 'blob'):
                    blob = bucket.blob(blob_path)
                    blob.upload_from_string(img_bytes, content_type='image/jpeg')
                    try:
                        blob.make_public()
                    except Exception:
                        pass
                    photo_url = getattr(blob, 'public_url', f"/static/uploads/{os.path.basename(blob_path)}")
                else:
                    raise ValueError("No active storage bucket")
            except Exception as e:
                logger.warning(f"Async photo upload error: {e}")
                local_filename = f"{now_dt.strftime('%Y%m%d_%H%M%S')}_{punch_type}.jpg"
                local_dir = os.path.join(Config.BASE_DIR, 'static', 'uploads', tenant_id, employee_id)
                os.makedirs(local_dir, exist_ok=True)
                local_path = os.path.join(local_dir, local_filename)
                with open(local_path, 'wb') as f:
                    f.write(img_bytes)
                photo_url = f"/static/uploads/{tenant_id}/{employee_id}/{local_filename}"

        if photo_url:
            field = 'punch_in_photo_url' if punch_type == 'in' else 'punch_out_photo_url'
            db.collection(f'tenants/{tenant_id}/attendance').document(att_id).update({field: photo_url})
    except Exception as err:
        logger.error(f"Async photo upload job failed: {err}")

def find_employee_by_code_or_email(identifier):
    """
    Search across all tenants to find active employee matching code or email.
    Enforces automated tenant context discovery.
    """
    identifier = identifier.strip()
    tenants = db.collection('tenants').get()
    
    for t_doc in tenants:
        t_data = t_doc.to_dict()
        tenant_id = t_data.get('tenant_id')
        
        # Query employees sub-collection
        emp_ref = db.collection(f'tenants/{tenant_id}/employees')
        
        # Search by code
        by_code = emp_ref.where('unique_emp_code', '==', identifier).get()
        if not by_code:
            # Search by email
            by_code = emp_ref.where('email', '==', identifier).get()
            
        if by_code:
            emp_data = by_code[0].to_dict()
            return t_data, emp_data
            
    return None, None

@employee_bp.route('/', methods=['GET'])
def punch_page():
    return render_template('employee/punch.html')

@employee_bp.route('/verify', methods=['POST'])
def verify_employee():
    identifier = request.form.get('identifier', '').strip()
    if not identifier:
        return jsonify({'success': False, 'message': 'Please enter your Employee Code or Email.'}), 400
        
    tenant_data, emp_data = find_employee_by_code_or_email(identifier)
    
    if not tenant_data or not emp_data:
        return jsonify({'success': False, 'message': 'Invalid Employee Code or Email. Employee not found.'}), 404
        
    if tenant_data.get('status') != 'active':
        return jsonify({
            'success': False,
            'message': f"Access Denied: Your employer ({tenant_data.get('business_name')}) account status is '{tenant_data.get('status')}'. Please contact manager."
        }), 403
        
    if emp_data.get('status') != 'active':
        return jsonify({
            'success': False,
            'message': 'Employee account is disabled. Please contact your manager.'
        }), 403
        
    # Return tenant verification settings & geofence metadata
    v_settings = tenant_data.get('verification_settings', {
        'require_pin': False,
        'require_face': False,
        'require_geofence': True
    })
    
    has_pin = bool(emp_data.get('pin'))
    has_face = bool(emp_data.get('face_descriptor'))
    
    pin_required = v_settings.get('require_pin') or has_pin
    face_required = v_settings.get('require_face') or has_face
    
    geofence = tenant_data.get('geofence', {
        'latitude': 17.385044,
        'longitude': 78.486671,
        'radius_meters': 200.0
    })
    
    # Store session state for employee punch
    session['emp_verified'] = True
    session['emp_tenant_id'] = tenant_data.get('tenant_id')
    session['employee_id'] = emp_data.get('employee_id')
    session['emp_code'] = emp_data.get('unique_emp_code')
    session['emp_name'] = emp_data.get('full_name')
    session['pin_required'] = pin_required
    session['face_required'] = face_required
    
    return jsonify({
        'success': True,
        'employee': {
            'employee_id': emp_data.get('employee_id'),
            'full_name': emp_data.get('full_name'),
            'unique_emp_code': emp_data.get('unique_emp_code'),
            'photo_url': emp_data.get('photo_url', '')
        },
        'tenant_name': tenant_data.get('business_name'),
        'geofence': geofence,
        'verification_requirements': {
            'require_pin': pin_required,
            'require_face': face_required,
            'has_enrolled_face': has_face,
            'require_geofence': v_settings.get('require_geofence', True)
        }
    })

@employee_bp.route('/submit', methods=['POST'])
def submit_punch():
    if not session.get('emp_verified'):
        return jsonify({'success': False, 'message': 'Employee session expired. Please verify code again.'}), 401
        
    tenant_id = session.get('emp_tenant_id') or session.get('tenant_id')
    employee_id = session.get('employee_id')
    
    punch_type = request.form.get('punch_type', 'in') # 'in' or 'out'
    lat = request.form.get('latitude')
    lng = request.form.get('longitude')
    photo_b64 = request.form.get('photo_base64', '')
    submitted_pin = request.form.get('pin', '').strip()
    submitted_face_desc = request.form.get('face_descriptor', '')
    
    # Retrieve tenant and employee details
    tenant_doc = db.collection('tenants').document(tenant_id).get()
    if not tenant_doc.exists:
        return jsonify({'success': False, 'message': 'Tenant account not found.'}), 404
        
    tenant_data = tenant_doc.to_dict()
    emp_doc = db.collection(f'tenants/{tenant_id}/employees').document(employee_id).get()
    if not emp_doc.exists:
        return jsonify({'success': False, 'message': 'Employee record not found.'}), 404
    emp_data = emp_doc.to_dict()

    v_settings = tenant_data.get('verification_settings', {'require_geofence': True})

    # 1. Validate PIN (if required or set)
    if (v_settings.get('require_pin') or emp_data.get('pin')) and emp_data.get('pin'):
        if not submitted_pin or submitted_pin != str(emp_data.get('pin')).strip():
            return jsonify({'success': False, 'message': 'Security PIN Verification Failed! Incorrect PIN.'}), 400

    # 2. Validate Face Descriptor (if required or enrolled)
    if v_settings.get('require_face') or emp_data.get('face_descriptor'):
        stored_vector = emp_data.get('face_descriptor')
        if not stored_vector and v_settings.get('require_face'):
            return jsonify({
                'success': False,
                'message': 'Face verification is required by your organization, but your biometric face has not been enrolled yet. Please ask your manager to enroll your face.'
            }), 400

        if stored_vector:
            if not submitted_face_desc:
                return jsonify({
                    'success': False,
                    'message': 'Face verification required. Please allow camera access or capture a photo for live face detection.'
                }), 400
            try:
                candidate_vector = json.loads(submitted_face_desc) if isinstance(submitted_face_desc, str) else submitted_face_desc
                comparison = compare_face_descriptors(stored_vector, candidate_vector)
                if not comparison['is_match']:
                    msg = f"Biometric Face Verification Failed! Match confidence: {comparison['confidence']}%. Face mismatch detected."
                    if comparison['confidence'] < 10.0:
                        msg += " Please re-enroll this employee's face once in the Owner Portal ([Employees] -> [Face] button) to update their biometric profile."
                    return jsonify({
                        'success': False,
                        'message': msg
                    }), 400
            except Exception as f_err:
                logger.error(f"Face verification comparison error: {f_err}")
                return jsonify({'success': False, 'message': 'Face recognition processing error.'}), 400

    # 3. Validate Geofence (if required)
    is_outside = False
    distance_meters = 0.0
    radius_meters = 200.0

    if v_settings.get('require_geofence', True):
        if not lat or not lng:
            return jsonify({'success': False, 'message': 'GPS Coordinates are required for geofence validation.'}), 400
            
        try:
            lat = float(lat)
            lng = float(lng)
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid GPS coordinates format.'}), 400
            
        # Check against primary location
        primary_fence = tenant_data.get('geofence', {})
        fence_lat = float(primary_fence.get('latitude', 0.0))
        fence_lng = float(primary_fence.get('longitude', 0.0))
        radius_meters = float(primary_fence.get('radius_meters', 200.0))
        
        geo_result = check_geofence_violation(lat, lng, fence_lat, fence_lng, radius_meters)
        is_outside = geo_result['is_outside']
        distance_meters = geo_result['distance_meters']

        # If outside primary location, check branch locations if present
        if is_outside:
            branches = db.collection(f'tenants/{tenant_id}/branches').get()
            for b_doc in branches:
                b_data = b_doc.to_dict()
                b_lat = float(b_data.get('latitude', 0.0))
                b_lng = float(b_data.get('longitude', 0.0))
                b_radius = float(b_data.get('radius_meters', radius_meters))
                b_res = check_geofence_violation(lat, lng, b_lat, b_lng, b_radius)
                if not b_res['is_outside']:
                    is_outside = False
                    distance_meters = b_res['distance_meters']
                    radius_meters = b_radius
    now_dt = get_ist_now()
    timestamp = now_dt.strftime("%Y%m%d_%H%M%S")

    # REJECT attendance marking if employee is outside geofence location
    if is_outside and v_settings.get('require_geofence', True):
        alert_id = f"alert_{uuid.uuid4().hex[:8]}"
        alert_data = {
            'alert_id': alert_id,
            'employee_id': employee_id,
            'employee_name': session.get('emp_name', 'Employee'),
            'alert_type': 'GEOFENCE_VIOLATION_ATTEMPT',
            'timestamp': now_dt.isoformat(),
            'latitude': lat,
            'longitude': lng,
            'distance_meters': distance_meters,
            'allowed_radius_meters': radius_meters,
            'resolved': False
        }
        db.collection(f'tenants/{tenant_id}/alerts').document(alert_id).set(alert_data)

        excess_meters = round(distance_meters - radius_meters, 1)
        return jsonify({
            'success': False,
            'message': f"Attendance Rejected! You are outside the geofence perimeter by {excess_meters} meters. (Distance: {distance_meters}m, Allowed radius: {radius_meters}m).",
            'is_outside': True,
            'distance_meters': distance_meters,
            'radius_meters': radius_meters
        }), 400

    today_str = get_ist_today_str()
    att_id = f"att_{employee_id}_{today_str}"

    # Process Photo Upload asynchronously in background thread
    photo_url = "/static/uploads/default_punch.jpg"
    if photo_b64:
        upload_executor.submit(process_async_photo_upload, tenant_id, employee_id, att_id, punch_type, photo_b64, now_dt)
            
    # Shift timing evaluation
    emp_doc = db.collection(f'tenants/{tenant_id}/employees').document(employee_id).get()
    emp_data = emp_doc.to_dict() if emp_doc.exists else {}
    shift_id = emp_data.get('shift_id')
    
    shifts = tenant_data.get('shifts', [])
    matched_shift = next((s for s in shifts if s.get('shift_id') == shift_id), shifts[0] if shifts else {})
    
    today_str = get_ist_today_str()
    current_time_str = now_dt.strftime("%I:%M:%S %p IST")
    
    status = "ON_TIME"
    if matched_shift and punch_type == 'in':
        start_time_str = matched_shift.get('start_time', '09:00')
        grace_mins = matched_shift.get('grace_period_mins', 15)
        
        try:
            start_h, start_m = map(int, start_time_str.split(':'))
            shift_start_mins = start_h * 60 + start_m + grace_mins
            punch_mins = now_dt.hour * 60 + now_dt.minute
            if punch_mins > shift_start_mins:
                status = "LATE"
        except Exception:
            pass
            
    # Record or update attendance log in Firestore
    att_id = f"att_{employee_id}_{today_str}"
    att_ref = db.collection(f'tenants/{tenant_id}/attendance').document(att_id)
    att_doc = att_ref.get()
    
    att_data = att_doc.to_dict() if att_doc.exists else {
        'attendance_id': att_id,
        'employee_id': employee_id,
        'date': today_str,
        'punch_in_time': '',
        'punch_out_time': '',
        'punch_in_lat': 0.0,
        'punch_in_lng': 0.0,
        'punch_out_lat': 0.0,
        'punch_out_lng': 0.0,
        'punch_in_photo_url': '',
        'punch_out_photo_url': '',
        'status': status,
        'is_outside_fence': False,
        'created_at': now_dt.isoformat()
    }
    
    if punch_type == 'in':
        att_data['punch_in_time'] = current_time_str
        att_data['punch_in_lat'] = lat
        att_data['punch_in_lng'] = lng
        att_data['punch_in_photo_url'] = photo_url
    else:
        att_data['punch_out_time'] = current_time_str
        att_data['punch_out_lat'] = lat
        att_data['punch_out_lng'] = lng
        att_data['punch_out_photo_url'] = photo_url
        
    att_data['status'] = status
    att_data['is_outside_fence'] = False
    
    att_ref.set(att_data, merge=True)
    
    response_msg = f"Punch-{punch_type.upper()} recorded successfully!"
    if status == "LATE":
        response_msg += " Note: Marked as LATE."
        
    return jsonify({
        'success': True,
        'message': response_msg,
        'status': status,
        'is_outside': False,
        'distance_meters': distance_meters,
        'radius_meters': radius_meters,
        'punch_time': current_time_str,
        'photo_url': photo_url
    })

