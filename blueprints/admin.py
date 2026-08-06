import uuid
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from firebase_config import db
from config import Config
from utils.razorpay_utils import create_razorpay_plan_api

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def is_admin_logged_in():
    return session.get('is_admin') is True

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if is_admin_logged_in():
        return redirect(url_for('admin.dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        # Verify against Config super admin or Firestore super_admins collection
        admin_docs = db.collection('super_admins').where('email', '==', username).get()
        valid = False
        
        if admin_docs:
            admin_data = admin_docs[0].to_dict()
            if admin_data.get('password') == password:
                valid = True
        elif username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
            valid = True
            
        if valid:
            session['is_admin'] = True
            session['admin_email'] = username
            flash('Successfully logged in as Super Admin.', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid Super Admin credentials.', 'danger')
            
    return render_template('admin/login.html')

@admin_bp.route('/logout')
def logout():
    session.pop('is_admin', None)
    session.pop('admin_email', None)
    flash('Logged out from Super Admin panel.', 'info')
    return redirect(url_for('admin.login'))

@admin_bp.route('/dashboard')
def dashboard():
    if not is_admin_logged_in():
        return redirect(url_for('admin.login'))
        
    tenants = [doc.to_dict() for doc in db.collection('tenants').get()]
    plans = {doc.id: doc.to_dict() for doc in db.collection('plans').get()}
    
    total_tenants = len(tenants)
    active_tenants = sum(1 for t in tenants if t.get('status') == 'active')
    blocked_tenants = sum(1 for t in tenants if t.get('status') == 'blocked')
    
    # Calculate estimated revenue
    total_revenue = 0.0
    for t in tenants:
        plan_id = t.get('current_plan_id')
        if plan_id and plan_id in plans and t.get('status') == 'active':
            total_revenue += float(plans[plan_id].get('price', 0))
            
    metrics = {
        'total_tenants': total_tenants,
        'active_tenants': active_tenants,
        'blocked_tenants': blocked_tenants,
        'total_revenue': total_revenue,
        'total_plans': len(plans)
    }
    
    return render_template('admin/dashboard.html', metrics=metrics, recent_tenants=tenants[:5])

@admin_bp.route('/tenants', methods=['GET', 'POST'])
def tenants():
    if not is_admin_logged_in():
        return redirect(url_for('admin.login'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            business_name = request.form.get('business_name', '').strip()
            owner_email = request.form.get('owner_email', '').strip()
            owner_password = request.form.get('owner_password', 'Password123!').strip()
            plan_id = request.form.get('plan_id')
            lat = float(request.form.get('latitude', 17.385044))
            lng = float(request.form.get('longitude', 78.486671))
            radius = float(request.form.get('radius_meters', 200))
            
            if not business_name or not owner_email:
                flash('Business Name and Owner Email are required.', 'danger')
            else:
                tenant_id = f"tenant_{uuid.uuid4().hex[:8]}"
                now_str = datetime.now(timezone.utc).isoformat()
                
                tenant_data = {
                    'tenant_id': tenant_id,
                    'business_name': business_name,
                    'owner_email': owner_email,
                    'owner_password': owner_password,
                    'status': 'active',
                    'current_plan_id': plan_id,
                    'subscription_start': now_str,
                    'subscription_end': "2027-12-31T23:59:59Z",
                    'razorpay_subscription_id': f"sub_admin_assigned_{uuid.uuid4().hex[:6]}",
                    'geofence': {
                        'latitude': lat,
                        'longitude': lng,
                        'radius_meters': radius,
                        'address': 'Configured HQ Location'
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
                
                db.collection('tenants').document(tenant_id).set(tenant_data)
                flash(f'Tenant "{business_name}" created successfully with ID {tenant_id}.', 'success')
                
        elif action == 'toggle_status':
            tenant_id = request.form.get('tenant_id')
            new_status = request.form.get('new_status')
            if tenant_id and new_status in ['active', 'blocked', 'expired']:
                db.collection('tenants').document(tenant_id).update({'status': new_status})
                flash(f'Tenant status updated to "{new_status}".', 'info')
                
        elif action == 'update_plan':
            tenant_id = request.form.get('tenant_id')
            plan_id = request.form.get('plan_id')
            if tenant_id and plan_id:
                db.collection('tenants').document(tenant_id).update({
                    'current_plan_id': plan_id,
                    'status': 'active'
                })
                flash('Tenant subscription plan updated successfully.', 'success')
                
        elif action == 'delete':
            tenant_id = request.form.get('tenant_id')
            if tenant_id:
                # Hard delete tenant document
                db.collection('tenants').document(tenant_id).delete()
                flash(f'Tenant {tenant_id} and associated records deleted.', 'warning')
                
        return redirect(url_for('admin.tenants'))

    tenants_list = [doc.to_dict() for doc in db.collection('tenants').get()]
    plans_list = [doc.to_dict() for doc in db.collection('plans').get()]
    
    return render_template('admin/tenants.html', tenants=tenants_list, plans=plans_list)

@admin_bp.route('/plans', methods=['GET', 'POST'])
def plans():
    if not is_admin_logged_in():
        return redirect(url_for('admin.login'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            name = request.form.get('name', '').strip()
            price = float(request.form.get('price', 0))
            max_employees = int(request.form.get('max_employees', 20))
            billing_cycle = request.form.get('billing_cycle', 'monthly')
            features_raw = request.form.get('features', '')
            features = [f.strip() for f in features_raw.split(',') if f.strip()]
            
            # Sync with Razorpay API
            rzp_res = create_razorpay_plan_api(name, price, billing_cycle, max_employees)
            rzp_plan_id = rzp_res.get('razorpay_plan_id')
            
            plan_id = f"plan_{uuid.uuid4().hex[:6]}"
            plan_data = {
                'plan_id': plan_id,
                'name': name,
                'price': price,
                'max_employees': max_employees,
                'billing_cycle': billing_cycle,
                'features': features or ["Geo-Fencing", "Camera Verification"],
                'status': 'active',
                'razorpay_plan_id': rzp_plan_id,
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
            db.collection('plans').document(plan_id).set(plan_data)
            flash(f'Subscription Plan "{name}" created & synced with Razorpay ({rzp_plan_id}).', 'success')
            
        elif action == 'archive':
            plan_id = request.form.get('plan_id')
            if plan_id:
                db.collection('plans').document(plan_id).update({'status': 'archived'})
                flash('Plan archived.', 'info')
                
        return redirect(url_for('admin.plans'))

    plans_list = [doc.to_dict() for doc in db.collection('plans').get()]
    return render_template('admin/plans.html', plans=plans_list)
