import os
os.environ['FORCE_LOCAL_DB'] = '1'
import unittest
import json
import hmac
import hashlib
from app import app
from utils.geo import haversine_distance, check_geofence_violation
from utils.razorpay_utils import verify_webhook_signature
from config import Config

class GeoFenceAttendanceSystemTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

        from firebase_config import db
        # Seed test tenant fixture for unit testing
        db.collection('tenants').document('tenant_demo').set({
            'tenant_id': 'tenant_demo',
            'business_name': 'Acme Global Tech',
            'owner_email': 'owner@acme.com',
            'owner_password': 'OwnerPassword123!',
            'status': 'active',
            'current_plan_id': 'plan_pro',
            'subscription_start': '2026-01-01T00:00:00Z',
            'subscription_end': '2026-12-31T23:59:59Z',
            'razorpay_subscription_id': 'sub_demo_acme_123',
            'geofence': {
                'latitude': 17.385044,
                'longitude': 78.486671,
                'radius_meters': 200.0,
                'address': 'Main Office Tech Park'
            },
            'shifts': [{
                'shift_id': 'shift_morning',
                'name': 'General Morning Shift',
                'start_time': '09:00',
                'end_time': '18:00',
                'grace_period_mins': 15
            }]
        })
        db.collection('tenants/tenant_demo/employees').document('emp_001').set({
            'employee_id': 'emp_001',
            'full_name': 'John Doe',
            'email': 'john@acme.com',
            'unique_emp_code': 'EMP-1001',
            'phone': '+91-9876543210',
            'shift_id': 'shift_morning',
            'status': 'active'
        })

    def test_haversine_distance(self):
        # Distance between same points should be 0
        d1 = haversine_distance(17.385044, 78.486671, 17.385044, 78.486671)
        self.assertEqual(d1, 0.0)

        # Distance between two nearby coordinates (~111 meters approx)
        d2 = haversine_distance(17.385044, 78.486671, 17.386044, 78.486671)
        self.assertGreater(d2, 100.0)
        self.assertLess(d2, 130.0)

        # Geofence violation check
        res_inside = check_geofence_violation(17.385044, 78.486671, 17.385044, 78.486671, 200.0)
        self.assertFalse(res_inside['is_outside'])

        res_outside = check_geofence_violation(17.500000, 78.500000, 17.385044, 78.486671, 200.0)
        self.assertTrue(res_outside['is_outside'])

    def test_razorpay_webhook_signature(self):
        secret = "test_webhook_secret_key"
        payload = b'{"event":"subscription.charged","payload":{}}'
        
        valid_sig = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook_signature(payload, valid_sig, secret))
        self.assertFalse(verify_webhook_signature(payload, "invalid_signature", secret))

    def test_admin_flow(self):
        # Admin login
        res = self.client.post('/admin/login', data={
            'username': Config.ADMIN_USERNAME,
            'password': Config.ADMIN_PASSWORD
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Super Admin Platform Overview', res.data)

    def test_tenant_flow(self):
        # Tenant login with seeded demo tenant
        res = self.client.post('/portal/login', data={
            'email': 'owner@acme.com',
            'password': 'OwnerPassword123!'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Acme Global Tech', res.data)

        # Test sub-pages render without Jinja2 UndefinedError
        for path in ['/portal/employees', '/portal/shifts', '/portal/alerts', '/portal/geofence', '/portal/billing', '/portal/branches', '/portal/departments', '/portal/leave', '/portal/audit-logs', '/portal/reports']:
            sub_res = self.client.get(path)
            self.assertEqual(sub_res.status_code, 200, f"Failed rendering {path}")
            self.assertIn(b'Acme Global Tech', sub_res.data)

    def test_reports_csv_export(self):
        # Login tenant owner first
        self.client.post('/portal/login', data={'email': 'owner@acme.com', 'password': 'OwnerPassword123!'})
        res = self.client.get('/portal/reports/export')
        self.assertEqual(res.status_code, 200)
        self.assertIn('text/csv', res.headers.get('Content-Type'))
        self.assertIn(b'Employee Name,Code', res.data)

    def test_face_descriptor_comparison(self):
        from utils.face_utils import compare_face_descriptors, calculate_euclidean_distance
        v1 = [0.1] * 128
        v2 = [0.1] * 128
        v3 = [0.9] * 128

        # Exact match distance should be 0
        self.assertEqual(calculate_euclidean_distance(v1, v2), 0.0)
        m1 = compare_face_descriptors(v1, v2)
        self.assertTrue(m1['is_match'])

        # Dissimilar vector match should fail
        m2 = compare_face_descriptors(v1, v3)
        self.assertFalse(m2['is_match'])

    def test_employee_punch_verification(self):
        # Verify seeded demo employee EMP-1001
        res = self.client.post('/punch/verify', data={
            'identifier': 'EMP-1001'
        })
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['employee']['full_name'], 'John Doe')

    def test_employee_punch_submit(self):
        # Verify employee session first
        res_v = self.client.post('/punch/verify', data={'identifier': 'EMP-1001'})
        v_data = json.loads(res_v.data)
        fence_lat = v_data['geofence']['latitude']
        fence_lng = v_data['geofence']['longitude']

        # Submit punch inside geofence
        test_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        res = self.client.post('/punch/submit', data={
            'punch_type': 'in',
            'latitude': fence_lat,
            'longitude': fence_lng,
            'photo_base64': test_b64
        })
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])
        self.assertFalse(data['is_outside'])

    def test_employee_punch_outside_geofence_rejected(self):
        # Verify employee session first
        self.client.post('/punch/verify', data={'identifier': 'EMP-1001'})

        # Submit punch outside geofence
        test_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        res = self.client.post('/punch/submit', data={
            'punch_type': 'in',
            'latitude': 17.500000,
            'longitude': 78.500000,
            'photo_base64': test_b64
        })
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.data)
        self.assertFalse(data['success'])
        self.assertTrue(data['is_outside'])
        self.assertIn("Attendance Rejected!", data['message'])

    def test_employee_session_cannot_access_owner_portal(self):
        # Verify employee code first
        self.client.post('/punch/verify', data={'identifier': 'EMP-1001'})

        # Attempt to access owner portal dashboard
        res = self.client.get('/portal/dashboard')
        # Must redirect to login page (302) instead of granting direct access (200)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/portal/login', res.location)

    def test_firebase_auth_user_creation(self):
        from firebase_config import create_firebase_user, verify_firebase_token
        user = create_firebase_user("test_user@example.com", "SecretPass123!", "Test User")
        self.assertIsNotNone(user)
        self.assertIn('uid', user)
        self.assertEqual(user['email'], 'test_user@example.com')

    def test_cloudinary_upload_helper(self):
        from utils.cloudinary_utils import upload_to_cloudinary, is_cloudinary_configured
        # Test helper functions without breaking when env keys are unconfigured
        self.assertIsInstance(is_cloudinary_configured(), bool)
        test_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        # Unconfigured upload returns None gracefully
        if not is_cloudinary_configured():
            url = upload_to_cloudinary(test_b64)
            self.assertIsNone(url)

if __name__ == '__main__':
    unittest.main()
