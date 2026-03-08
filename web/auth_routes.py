"""
Authentication routes for OntServe web application.

Handles login, logout, and user profile pages.
"""

from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user, login_user, logout_user
from sqlalchemy import select

from web.models import db, User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))

        if not username or not password:
            flash('Please enter both username and password', 'error')
            return render_template('auth/login.html')

        stmt = select(User).where(User.username == username)
        user = db.session.execute(stmt).scalar_one_or_none()

        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=remember)

            # Update last login with timezone-aware datetime
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()

            current_app.logger.info(f"User {username} logged in successfully")

            next_page = request.args.get('next') or request.form.get('next')
            if next_page:
                parsed = urlparse(next_page)
                if not parsed.netloc and not parsed.scheme:
                    return redirect(next_page)
            return redirect(url_for('main.index'))
        else:
            current_app.logger.warning(f"Failed login attempt for username: {username}")
            flash('Invalid username or password', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """User logout."""
    username = current_user.username if current_user.is_authenticated else 'Unknown'
    logout_user()
    current_app.logger.info(f"User {username} logged out")
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile')
@login_required
def profile():
    """User profile page."""
    return render_template('auth/profile.html', user=current_user)
