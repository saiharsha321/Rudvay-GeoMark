import os
import logging
from flask import Flask, render_template, redirect, url_for
from config import Config
from firebase_config import init_firebase

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize Firebase SDK / Local Fallback Driver
    init_firebase()

    # Register Blueprints
    from blueprints.admin import admin_bp
    from blueprints.tenant import tenant_bp
    from blueprints.employee import employee_bp
    from blueprints.api import api_bp

    app.register_blueprint(admin_bp)
    app.register_blueprint(tenant_bp)
    app.register_blueprint(employee_bp)
    app.register_blueprint(api_bp)

    @app.context_processor
    def inject_firebase_config():
        return {
            'firebase_config': {
                'apiKey': app.config.get('FIREBASE_API_KEY'),
                'authDomain': app.config.get('FIREBASE_AUTH_DOMAIN'),
                'projectId': app.config.get('FIREBASE_PROJECT_ID'),
                'storageBucket': app.config.get('FIREBASE_STORAGE_BUCKET'),
                'messagingSenderId': app.config.get('FIREBASE_MESSAGING_SENDER_ID'),
                'appId': app.config.get('FIREBASE_APP_ID'),
                'measurementId': app.config.get('FIREBASE_MEASUREMENT_ID')
            }
        }

    @app.route('/')
    def index():
        return render_template('employee/punch.html')

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('base.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('base.html'), 500

    return app

app = create_app()

if __name__ == '__main__':
    import sys
    port = int(os.environ.get('PORT', 5000))
    use_https = '--https' in sys.argv or os.environ.get('USE_HTTPS', '').lower() in ['1', 'true']
    ssl_ctx = 'adhoc' if use_https else None
    
    if use_https:
        logging.info(f"Running Flask with HTTPS (adhoc SSL certificate) on https://0.0.0.0:{port}")
    else:
        logging.info(f"Running Flask on http://0.0.0.0:{port}")
        
    app.run(host='0.0.0.0', port=port, debug=True, ssl_context=ssl_ctx)
