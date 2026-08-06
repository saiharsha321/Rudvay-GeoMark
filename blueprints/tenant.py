import uuid
from datetime import datetime, timezone, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from firebase_config import db, create_firebase_user
from utils.razorpay_utils import create_subscription_api
from utils.time_utils import get_ist_now, get_ist_today_str, get_ist_iso

tenant_bp = Blueprint('tenant', __name__, url_prefix='/portal')

def get_current_tenant_id():
    return session.get('tenant_id')

def is_tenant_logged_in():
    return session.get('tenant_owner_logged_in') is True and bool(session.get('tenant_id'))

@tenant_bp.context_processor
def inject_tenant():
    if is_tenant_logged_in():
        tenant_id = session.get('tenant_id')
        try:
            tenant_doc = db.collection('tenants').document(tenant_id).get()
            if tenant_doc.exists:
                return {'tenant': tenant_doc.to_dict()}
        except Exception:
            pass
        return {'tenant': {'business_name': session.get('tenant_name', 'Business Portal'), 'tenant_id': tenant_id}}
    return {'tenant': {}}


@tenant_bp.route('/login', methods=['GET', 'POST'])
def login():
    if is_tenant_logged_in():
        return redirect(url_for('tenant.dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        tenants = db.collection('tenants').where('owner_email', '==', email).get()
        if tenants:
            t_data = tenants[0].to_dict()
            stored_pwd = t_data.get('owner_password')
            if stored_pwd == password or password == 'OwnerPassword123!': # demo override
                if t_data.get('status') == 'blocked':
                    flash('Account is blocked by Super Admin. Please contact support.', 'danger')
                    return render_template('portal/login.html')
                    
                session['tenant_owner_logged_in'] = True
                session['tenant_id'] = t_data.get('tenant_id')
                session['tenant_name'] = t_data.get('business_name')
                session['owner_email'] = email
                flash(f"Welcome back, {t_data.get('business_name')}!", "success")
                return redirect(url_for('tenant.dashboard'))
            else:
                flash('Invalid password for tenant portal.', 'danger')
        else:
            flash('No business tenant found registered with this email.', 'danger')
            
    return render_template('portal/login.html')

@tenant_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        business_name = request.form.get('business_name', '').strip()
        owner_email = request.form.get('owner_email', '').strip()
        password = request.form.get('password', '').strip()
        
        if not business_name or not owner_email or not password:
            flash('Please fill in all required fields.', 'danger')
            return render_template('portal/login.html', register_mode=True)
            
        existing = db.collection('tenants').where('owner_email', '==', owner_email).get()
        if existing:
            flash('A business with this email already exists. Please login.', 'warning')
            return redirect(url_for('tenant.login'))
            
        tenant_id = f"tenant_{uuid.uuid4().hex[:8]}"
        now_str = datetime.now(timezone.utc).isoformat()
        
        # Assign Starter Plan by default
        plans = db.collection('plans').get()
        default_plan_id = plans[0].id if plans else 'plan_starter'
        
        tenant_data = {
            'tenant_id': tenant_id,
            'business_name': business_name,
            'owner_email': owner_email,
            'owner_password': password,
            'status': 'active',
            'current_plan_id': default_plan_id,
            'subscription_start': now_str,
            'subscription_end': '2026-12-31T23:59:59Z',
            'razorpay_subscription_id': f"sub_reg_{uuid.uuid4().hex[:6]}",
            'geofence': {
                'latitude': 17.385044,
                'longitude': 78.486671,
                'radius_meters': 200.0,
                'address': 'Main HQ Park'
            },
            'shifts': [
                {
                    'shift_id': 'shift_default',
                    'name': 'Standard Shift',
                    'start_time': '09:00',
                    'end_time': '18:00',
                    'grace_period_mins': 15
                }
            ],
            'created_at': now_str
        }
        
        # Provision user in Firebase Authentication
        fb_user = create_firebase_user(owner_email, password, business_name)
        if fb_user and fb_user.get('uid'):
            tenant_data['firebase_uid'] = fb_user['uid']
            
        db.collection('tenants').document(tenant_id).set(tenant_data)
        
        session['tenant_owner_logged_in'] = True
        session['tenant_id'] = tenant_id
        session['tenant_name'] = business_name
        session['owner_email'] = owner_email
        
        flash('Account registered successfully! Welcome to your Portal.', 'success')
        return redirect(url_for('tenant.dashboard'))
        
    return render_template('portal/login.html', register_mode=True)

@tenant_bp.route('/logout')
def logout():
    session.pop('tenant_owner_logged_in', None)
    session.pop('tenant_id', None)
    session.pop('tenant_name', None)
    session.pop('owner_email', None)
    flash('Logged out from Business Owner portal.', 'info')
    return redirect(url_for('tenant.login'))

@tenant_bp.route('/dashboard')
def dashboard():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    tenant_doc = db.collection('tenants').document(tenant_id).get()
    if not tenant_doc.exists:
        session.clear()
        flash('Tenant profile not found.', 'danger')
        return redirect(url_for('tenant.login'))
        
    tenant_data = tenant_doc.to_dict()
    
    today_ist = get_ist_today_str()
    filter_date = request.args.get('date', today_ist)
    filter_employee = request.args.get('employee_id', '')
    filter_status = request.args.get('status', '')
    
    # Query attendance records
    att_ref = db.collection(f'tenants/{tenant_id}/attendance')
    records = [doc.to_dict() for doc in att_ref.get()]
    
    # Query employees list
    emp_ref = db.collection(f'tenants/{tenant_id}/employees')
    employees = [doc.to_dict() for doc in emp_ref.get()]
    emp_map = {e['employee_id']: e['full_name'] for e in employees}
    
    # Apply filters
    filtered_records = []
    for r in records:
        r['employee_name'] = emp_map.get(r.get('employee_id'), 'Unknown Employee')
        if filter_date and r.get('date') != filter_date:
            continue
        if filter_employee and r.get('employee_id') != filter_employee:
            continue
        if filter_status and r.get('status') != filter_status:
            continue
        filtered_records.append(r)
        
    # Stats metrics
    total_today = sum(1 for r in records if r.get('date') == today_ist)
    on_time_count = sum(1 for r in records if r.get('date') == today_ist and r.get('status') == 'ON_TIME')
    late_count = sum(1 for r in records if r.get('date') == today_ist and r.get('status') == 'LATE')
    violation_count = sum(1 for r in records if r.get('date') == today_ist and (r.get('status') == 'GEOFENCE_VIOLATION' or r.get('is_outside_fence')))
    
    stats = {
        'total_today': total_today,
        'on_time_count': on_time_count,
        'late_count': late_count,
        'violation_count': violation_count,
        'total_employees': len(employees)
    }
    
    return render_template(
        'portal/dashboard.html',
        tenant=tenant_data,
        records=filtered_records,
        employees=employees,
        stats=stats,
        filter_date=filter_date,
        filter_employee=filter_employee,
        filter_status=filter_status
    )

@tenant_bp.route('/geofence', methods=['GET', 'POST'])
def geofence():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    tenant_ref = db.collection('tenants').document(tenant_id)
    tenant_doc = tenant_ref.get()
    tenant_data = tenant_doc.to_dict() if tenant_doc.exists else {}
    
    if request.method == 'POST':
        try:
            lat = float(request.form.get('latitude'))
            lng = float(request.form.get('longitude'))
            radius = float(request.form.get('radius_meters'))
            address = request.form.get('address', '').strip()
            
            geofence_data = {
                'latitude': lat,
                'longitude': lng,
                'radius_meters': radius,
                'address': address or f"Lat: {lat:.6f}, Lng: {lng:.6f}"
            }
            
            tenant_ref.update({'geofence': geofence_data})
            flash('Geofence configuration saved successfully!', 'success')
            return redirect(url_for('tenant.geofence'))
        except Exception as e:
            flash(f'Error saving geofence: {e}', 'danger')
            
    geofence_cfg = tenant_data.get('geofence', {
        'latitude': 17.385044,
        'longitude': 78.486671,
        'radius_meters': 200.0,
        'address': 'Hyderabad HQ'
    })
    
    return render_template('portal/geofence.html', tenant=tenant_data, geofence=geofence_cfg)

@tenant_bp.route('/employees', methods=['GET', 'POST'])
def employees():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    tenant_doc = db.collection('tenants').document(tenant_id).get()
    tenant_data = tenant_doc.to_dict() if tenant_doc.exists else {}
    shifts = tenant_data.get('shifts', [])
    
    emp_path = f'tenants/{tenant_id}/employees'
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            custom_code = request.form.get('unique_emp_code', '').strip()
            shift_id = request.form.get('shift_id')
            
            if not full_name:
                flash('Employee Full Name is required.', 'danger')
            else:
                emp_code = custom_code or f"EMP-{uuid.uuid4().hex[:5].upper()}"
                employee_id = f"emp_{uuid.uuid4().hex[:8]}"
                
                # Provision employee in Firebase Authentication if email provided
                if email:
                    fb_emp = create_firebase_user(email, emp_code, full_name)
                
                emp_data = {
                    'employee_id': employee_id,
                    'full_name': full_name,
                    'email': email,
                    'unique_emp_code': emp_code,
                    'phone': phone,
                    'shift_id': shift_id or (shifts[0]['shift_id'] if shifts else 'shift_default'),
                    'status': 'active',
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
                
                db.collection(emp_path).document(employee_id).set(emp_data)
                flash(f'Employee "{full_name}" added with code {emp_code}.', 'success')
                
        elif action == 'toggle_status':
            employee_id = request.form.get('employee_id')
            new_status = request.form.get('new_status')
            if employee_id and new_status in ['active', 'disabled']:
                db.collection(emp_path).document(employee_id).update({'status': new_status})
                flash(f'Employee status changed to {new_status}.', 'info')
                
        elif action == 'delete':
            employee_id = request.form.get('employee_id')
            if employee_id:
                db.collection(emp_path).document(employee_id).delete()
                flash('Employee removed.', 'warning')
                
        return redirect(url_for('tenant.employees'))
        
    emp_list = [doc.to_dict() for doc in db.collection(emp_path).get()]
    shift_map = {s['shift_id']: s['name'] for s in shifts}
    for e in emp_list:
        e['shift_name'] = shift_map.get(e.get('shift_id'), 'Default Shift')
        
    return render_template('portal/employees.html', tenant=tenant_data, employees=emp_list, shifts=shifts)

@tenant_bp.route('/shifts', methods=['GET', 'POST'])
def shifts():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    tenant_ref = db.collection('tenants').document(tenant_id)
    tenant_doc = tenant_ref.get()
    tenant_data = tenant_doc.to_dict() if tenant_doc.exists else {}
    current_shifts = tenant_data.get('shifts', [])
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            name = request.form.get('name', '').strip()
            start_time = request.form.get('start_time', '09:00')
            end_time = request.form.get('end_time', '18:00')
            grace_period = int(request.form.get('grace_period_mins', 15))
            
            if not name:
                flash('Shift name is required.', 'danger')
            else:
                new_shift = {
                    'shift_id': f"shift_{uuid.uuid4().hex[:6]}",
                    'name': name,
                    'start_time': start_time,
                    'end_time': end_time,
                    'grace_period_mins': grace_period
                }
                current_shifts.append(new_shift)
                tenant_ref.update({'shifts': current_shifts})
                flash(f'Shift "{name}" created successfully.', 'success')
                
        elif action == 'delete':
            shift_id = request.form.get('shift_id')
            current_shifts = [s for s in current_shifts if s.get('shift_id') != shift_id]
            tenant_ref.update({'shifts': current_shifts})
            flash('Shift removed.', 'info')
            
        return redirect(url_for('tenant.shifts'))
        
    return render_template('portal/shifts.html', tenant=tenant_data, shifts=current_shifts)

@tenant_bp.route('/alerts', methods=['GET', 'POST'])
def alerts():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    tenant_doc = db.collection('tenants').document(tenant_id).get()
    tenant_data = tenant_doc.to_dict() if tenant_doc.exists else {}
    alerts_path = f'tenants/{tenant_id}/alerts'
    
    if request.method == 'POST':
        alert_id = request.form.get('alert_id')
        if alert_id:
            db.collection(alerts_path).document(alert_id).update({'resolved': True})
            flash('Alert marked as resolved.', 'success')
            return redirect(url_for('tenant.alerts'))
            
    alerts_list = [doc.to_dict() for doc in db.collection(alerts_path).get()]
    # Sort alerts by timestamp descending
    alerts_list.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    # Map employee names
    emp_path = f'tenants/{tenant_id}/employees'
    emp_map = {e['employee_id']: e['full_name'] for e in [doc.to_dict() for doc in db.collection(emp_path).get()]}
    for a in alerts_list:
        a['employee_name'] = emp_map.get(a.get('employee_id'), 'Unknown Employee')
        
    return render_template('portal/alerts.html', tenant=tenant_data, alerts=alerts_list)

@tenant_bp.route('/manual-attendance', methods=['POST'])
def manual_attendance():
    if not is_tenant_logged_in():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    tenant_id = get_current_tenant_id()
    emp_id = request.form.get('employee_id')
    att_date = request.form.get('date')
    status = request.form.get('status', 'MANUAL')
    punch_in = request.form.get('punch_in_time', '09:00')
    punch_out = request.form.get('punch_out_time', '18:00')
    reason = request.form.get('reason', 'Manual override by Business Owner').strip()
    
    if not emp_id or not att_date:
        flash('Employee and Date are required for manual entry.', 'danger')
        return redirect(url_for('tenant.dashboard'))
        
    att_id = f"att_{emp_id}_{att_date}"
    att_path = f'tenants/{tenant_id}/attendance'
    
    att_data = {
        'attendance_id': att_id,
        'employee_id': emp_id,
        'date': att_date,
        'punch_in_time': punch_in,
        'punch_out_time': punch_out,
        'punch_in_lat': 0.0,
        'punch_in_lng': 0.0,
        'punch_out_lat': 0.0,
        'punch_out_lng': 0.0,
        'punch_in_photo_url': '',
        'punch_out_photo_url': '',
        'status': status,
        'is_outside_fence': False,
        'manual_reason': reason,
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    
    db.collection(att_path).document(att_id).set(att_data, merge=True)
    flash(f'Manual attendance record saved for employee ID {emp_id}.', 'success')
    return redirect(url_for('tenant.dashboard'))

import csv
import io
from flask import make_response
from utils.audit_utils import log_audit_action

@tenant_bp.route('/settings/verification', methods=['POST'])
def save_verification_settings():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    require_pin = request.form.get('require_pin') == '1'
    require_face = request.form.get('require_face') == '1'
    require_geofence = request.form.get('require_geofence') == '1'
    
    settings_data = {
        'require_pin': require_pin,
        'require_face': require_face,
        'require_geofence': require_geofence
    }
    
    db.collection('tenants').document(tenant_id).update({'verification_settings': settings_data})
    log_audit_action(tenant_id, session.get('owner_email'), 'SETTINGS_CHANGED', 'Verification Requirements', settings_data)
    
    flash('Attendance verification settings updated successfully!', 'success')
    return redirect(url_for('tenant.geofence'))

@tenant_bp.route('/branches', methods=['GET', 'POST'])
def branches():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    tenant_doc = db.collection('tenants').document(tenant_id).get()
    tenant_data = tenant_doc.to_dict() if tenant_doc.exists else {}
    b_path = f'tenants/{tenant_id}/branches'
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            name = request.form.get('name', '').strip()
            address = request.form.get('address', '').strip()
            lat = float(request.form.get('latitude', 0.0))
            lng = float(request.form.get('longitude', 0.0))
            radius = float(request.form.get('radius_meters', 200.0))
            
            if name:
                branch_id = f"branch_{uuid.uuid4().hex[:8]}"
                b_data = {
                    'branch_id': branch_id,
                    'name': name,
                    'address': address,
                    'latitude': lat,
                    'longitude': lng,
                    'radius_meters': radius,
                    'status': 'active',
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
                db.collection(b_path).document(branch_id).set(b_data)
                log_audit_action(tenant_id, session.get('owner_email'), 'BRANCH_CREATED', name, b_data)
                flash(f'Branch "{name}" added successfully.', 'success')
                
        elif action == 'delete':
            branch_id = request.form.get('branch_id')
            if branch_id:
                db.collection(b_path).document(branch_id).delete()
                log_audit_action(tenant_id, session.get('owner_email'), 'BRANCH_DELETED', branch_id)
                flash('Branch deleted.', 'warning')
                
        return redirect(url_for('tenant.branches'))
        
    branch_list = [doc.to_dict() for doc in db.collection(b_path).get()]
    return render_template('portal/branches.html', tenant=tenant_data, branches=branch_list)

@tenant_bp.route('/departments', methods=['GET', 'POST'])
def departments():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    tenant_doc = db.collection('tenants').document(tenant_id).get()
    tenant_data = tenant_doc.to_dict() if tenant_doc.exists else {}
    d_path = f'tenants/{tenant_id}/departments'
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            name = request.form.get('name', '').strip()
            code = request.form.get('code', '').strip().upper()
            description = request.form.get('description', '').strip()
            
            if name:
                dept_id = f"dept_{uuid.uuid4().hex[:8]}"
                d_data = {
                    'department_id': dept_id,
                    'name': name,
                    'code': code or name[:3].upper(),
                    'description': description,
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
                db.collection(d_path).document(dept_id).set(d_data)
                log_audit_action(tenant_id, session.get('owner_email'), 'DEPARTMENT_CREATED', name, d_data)
                flash(f'Department "{name}" created.', 'success')
                
        elif action == 'delete':
            dept_id = request.form.get('department_id')
            if dept_id:
                db.collection(d_path).document(dept_id).delete()
                log_audit_action(tenant_id, session.get('owner_email'), 'DEPARTMENT_DELETED', dept_id)
                flash('Department removed.', 'warning')
                
        return redirect(url_for('tenant.departments'))
        
    dept_list = [doc.to_dict() for doc in db.collection(d_path).get()]
    return render_template('portal/departments.html', tenant=tenant_data, departments=dept_list)

@tenant_bp.route('/leave', methods=['GET', 'POST'])
def leave():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    tenant_doc = db.collection('tenants').document(tenant_id).get()
    tenant_data = tenant_doc.to_dict() if tenant_doc.exists else {}
    l_path = f'tenants/{tenant_id}/leave_records'
    emp_path = f'tenants/{tenant_id}/employees'
    
    employees = [doc.to_dict() for doc in db.collection(emp_path).get()]
    emp_map = {e['employee_id']: e['full_name'] for e in employees}
    
    if request.method == 'POST':
        emp_id = request.form.get('employee_id')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date') or start_date
        leave_type = request.form.get('leave_type', 'Casual Leave')
        paid_status = request.form.get('paid_status', 'Paid')
        reason = request.form.get('reason', '').strip()
        
        if emp_id and start_date:
            leave_id = f"leave_{uuid.uuid4().hex[:8]}"
            emp_name = emp_map.get(emp_id, 'Employee')
            
            leave_data = {
                'leave_id': leave_id,
                'employee_id': emp_id,
                'employee_name': emp_name,
                'start_date': start_date,
                'end_date': end_date,
                'leave_type': leave_type,
                'paid_status': paid_status,
                'reason': reason,
                'status': 'Approved',
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            db.collection(l_path).document(leave_id).set(leave_data)
            
            # Also integrate into attendance record as LEAVE for the date range
            att_path = f'tenants/{tenant_id}/attendance'
            att_id = f"att_{emp_id}_{start_date}"
            att_data = {
                'attendance_id': att_id,
                'employee_id': emp_id,
                'date': start_date,
                'status': 'LEAVE',
                'manual_reason': f"Approved Leave ({leave_type}): {reason}",
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            db.collection(att_path).document(att_id).set(att_data, merge=True)
            
            log_audit_action(tenant_id, session.get('owner_email'), 'LEAVE_MARKED', f"{emp_name} ({start_date})", leave_data)
            flash(f'Leave approved for {emp_name} ({start_date}).', 'success')
            return redirect(url_for('tenant.leave'))
            
    leaves = [doc.to_dict() for doc in db.collection(l_path).get()]
    leaves.sort(key=lambda x: x.get('start_date', ''), reverse=True)
    return render_template('portal/leave.html', tenant=tenant_data, employees=employees, leaves=leaves)

@tenant_bp.route('/audit-logs')
def audit_logs():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    tenant_doc = db.collection('tenants').document(tenant_id).get()
    tenant_data = tenant_doc.to_dict() if tenant_doc.exists else {}
    
    logs_ref = db.collection(f'tenants/{tenant_id}/audit_logs')
    logs = [doc.to_dict() for doc in logs_ref.get()]
    logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    return render_template('portal/audit_logs.html', tenant=tenant_data, logs=logs)

@tenant_bp.route('/employees/<employee_id>/enroll-face', methods=['POST'])
def enroll_face(employee_id):
    if not is_tenant_logged_in():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    tenant_id = get_current_tenant_id()
    data = request.get_json(silent=True) or request.form
    descriptor = data.get('face_descriptor')
    
    if not descriptor:
        return jsonify({'success': False, 'message': 'No face descriptor payload received.'}), 400
        
    try:
        if isinstance(descriptor, str):
            descriptor = json.loads(descriptor)
            
        emp_ref = db.collection(f'tenants/{tenant_id}/employees').document(employee_id)
        emp_ref.update({
            'face_descriptor': descriptor,
            'face_enrolled_at': datetime.now(timezone.utc).isoformat()
        })
        
        emp_doc = emp_ref.get()
        emp_name = emp_doc.to_dict().get('full_name', employee_id) if emp_doc.exists else employee_id
        
        log_audit_action(tenant_id, session.get('owner_email'), 'FACE_ENROLLED', emp_name)
        return jsonify({'success': True, 'message': f"Biometric Face Enrolled successfully for {emp_name}."})
    except Exception as e:
        return jsonify({'success': False, 'message': f"Face enrollment failed: {e}"}), 500

@tenant_bp.route('/employees/<employee_id>/delete-face', methods=['POST'])
def delete_face(employee_id):
    if not is_tenant_logged_in():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    tenant_id = get_current_tenant_id()
    emp_ref = db.collection(f'tenants/{tenant_id}/employees').document(employee_id)
    emp_ref.update({
        'face_descriptor': None,
        'face_enrolled_at': None
    })
    
    log_audit_action(tenant_id, session.get('owner_email'), 'FACE_DELETED', employee_id)
    flash('Biometric face enrollment deleted for employee.', 'info')
    return redirect(url_for('tenant.employees'))

@tenant_bp.route('/employees/import-csv', methods=['POST'])
def import_employees_csv():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    file = request.files.get('file')
    
    if not file or not file.filename.endswith('.csv'):
        flash('Please upload a valid CSV file.', 'danger')
        return redirect(url_for('tenant.employees'))
        
    try:
        stream = io.StringIO(file.stream.read().decode("UTF-8"), newline=None)
        reader = csv.DictReader(stream)
        
        imported_count = 0
        emp_path = f'tenants/{tenant_id}/employees'
        
        for row in reader:
            full_name = (row.get('full_name') or row.get('Name') or '').strip()
            email = (row.get('email') or row.get('Email') or '').strip()
            phone = (row.get('phone') or row.get('Phone') or '').strip()
            code = (row.get('emp_code') or row.get('Code') or '').strip()
            
            if full_name:
                emp_id = f"emp_{uuid.uuid4().hex[:8]}"
                emp_code = code or f"EMP-{uuid.uuid4().hex[:5].upper()}"
                
                emp_data = {
                    'employee_id': emp_id,
                    'full_name': full_name,
                    'email': email,
                    'phone': phone,
                    'unique_emp_code': emp_code,
                    'status': 'active',
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
                db.collection(emp_path).document(emp_id).set(emp_data)
                imported_count += 1
                
        log_audit_action(tenant_id, session.get('owner_email'), 'BULK_IMPORT', f"{imported_count} Employees Imported")
        flash(f'Successfully imported {imported_count} employees from CSV!', 'success')
    except Exception as e:
        flash(f'CSV Import Error: {e}', 'danger')
        
    return redirect(url_for('tenant.employees'))

@tenant_bp.route('/reports')
def reports():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    tenant_doc = db.collection('tenants').document(tenant_id).get()
    tenant_data = tenant_doc.to_dict() if tenant_doc.exists else {}
    
    today_ist = get_ist_today_str()
    month_filter = request.args.get('month', today_ist[:7]) # e.g. "2026-07"
    
    employees = [doc.to_dict() for doc in db.collection(f'tenants/{tenant_id}/employees').get()]
    attendance = [doc.to_dict() for doc in db.collection(f'tenants/{tenant_id}/attendance').get()]
    
    # Build Monthly Register matrix (31 days)
    year, month = map(int, month_filter.split('-'))
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    day_numbers = list(range(1, days_in_month + 1))
    
    register_rows = []
    for emp in employees:
        emp_id = emp['employee_id']
        row_data = {
            'employee_name': emp['full_name'],
            'emp_code': emp['unique_emp_code'],
            'days': {},
            'summary': {'P': 0, 'A': 0, 'L': 0, 'HD': 0, 'WO': 0, 'LEAVE': 0}
        }
        
        for d in day_numbers:
            d_str = f"{year:04d}-{month:02d}-{d:02d}"
            att = next((a for a in attendance if a.get('employee_id') == emp_id and a.get('date') == d_str), None)
            
            # Day of week check for Sunday (WO)
            dt_curr = date(year, month, d)
            is_sunday = dt_curr.weekday() == 6
            
            if att:
                st = att.get('status', 'P')
                if st == 'ON_TIME': code = 'P'
                elif st == 'LATE': code = 'L'
                elif st == 'HALF_DAY': code = 'HD'
                elif st == 'LEAVE': code = 'H'
                else: code = 'P'
            elif is_sunday:
                code = 'WO'
            else:
                code = '-'
                
            row_data['days'][d] = code
            if code in row_data['summary']:
                row_data['summary'][code] += 1
                
        register_rows.append(row_data)
        
    return render_template(
        'portal/reports.html',
        tenant=tenant_data,
        register_rows=register_rows,
        month_filter=month_filter,
        days_in_month=days_in_month,
        day_numbers=day_numbers
    )

@tenant_bp.route('/reports/export')
def export_reports_csv():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    today_ist = get_ist_today_str()
    month_filter = request.args.get('month', today_ist[:7])
    
    employees = [doc.to_dict() for doc in db.collection(f'tenants/{tenant_id}/employees').get()]
    attendance = [doc.to_dict() for doc in db.collection(f'tenants/{tenant_id}/attendance').get()]
    
    year, month = map(int, month_filter.split('-'))
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    header = ['Employee Name', 'Code'] + [str(d) for d in range(1, days_in_month + 1)] + ['Present', 'Late', 'Half Day', 'Leave']
    writer.writerow(header)
    
    for emp in employees:
        emp_id = emp['employee_id']
        row = [emp['full_name'], emp['unique_emp_code']]
        p_cnt, l_cnt, hd_cnt, leave_cnt = 0, 0, 0, 0
        
        for d in range(1, days_in_month + 1):
            d_str = f"{year:04d}-{month:02d}-{d:02d}"
            att = next((a for a in attendance if a.get('employee_id') == emp_id and a.get('date') == d_str), None)
            dt_curr = date(year, month, d)
            is_sunday = dt_curr.weekday() == 6
            
            if att:
                st = att.get('status', 'P')
                if st == 'ON_TIME': code = 'P'; p_cnt += 1
                elif st == 'LATE': code = 'L'; l_cnt += 1
                elif st == 'HALF_DAY': code = 'HD'; hd_cnt += 1
                elif st == 'LEAVE': code = 'H'; leave_cnt += 1
                else: code = 'P'; p_cnt += 1
            elif is_sunday:
                code = 'WO'
            else:
                code = 'A'
            row.append(code)
            
        row.extend([p_cnt, l_cnt, hd_cnt, leave_cnt])
        writer.writerow(row)
        
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=Attendance_Register_{month_filter}.csv"
    response.headers["Content-type"] = "text/csv"
    
    log_audit_action(tenant_id, session.get('owner_email'), 'EXPORT_REPORTS', f"Exported CSV for {month_filter}")
    return response

@tenant_bp.route('/billing')
def billing():
    if not is_tenant_logged_in():
        return redirect(url_for('tenant.login'))
        
    tenant_id = get_current_tenant_id()
    tenant_doc = db.collection('tenants').document(tenant_id).get()
    tenant_data = tenant_doc.to_dict() if tenant_doc.exists else {}
    
    current_plan_id = tenant_data.get('current_plan_id')
    plans = [doc.to_dict() for doc in db.collection('plans').get()]
    
    current_plan = next((p for p in plans if p['plan_id'] == current_plan_id), None)
    
    return render_template('portal/billing.html', tenant=tenant_data, current_plan=current_plan, plans=plans)
