from flask import Blueprint, render_template, request, flash, redirect, url_for
import logging

logger = logging.getLogger(__name__)

public_bp = Blueprint('public', __name__)

@public_bp.route('/')
def index():
    return render_template(['public/index.html', 'index.html'])

@public_bp.route('/features')
def features():
    return render_template(['public/features.html', 'features.html'])

@public_bp.route('/solutions')
def solutions():
    return render_template(['public/solutions.html', 'solutions.html'])

@public_bp.route('/pricing')
def pricing():
    return render_template(['public/pricing.html', 'pricing.html'])

@public_bp.route('/about')
def about():
    return render_template(['public/about.html', 'about.html'])

@public_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        logger.info(f"Contact form submitted by {name} ({email}): {message}")
        flash("Thank you for reaching out! Our team at Rudvay Tech will contact you shortly.", "success")
        return redirect(url_for('public.contact'))
    return render_template(['public/contact.html', 'contact.html'])

@public_bp.route('/terms')
def terms():
    return render_template(['public/terms.html', 'terms.html'])

@public_bp.route('/privacy')
def privacy():
    return render_template(['public/privacy.html', 'privacy.html'])
