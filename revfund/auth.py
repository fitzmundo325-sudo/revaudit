from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from .models import User
from .audit import log_audit_event
from werkzeug.security import check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timezone

auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user is None and username:
            # Deactivated accounts carry a 'deactivated:' prefix on their
            # username; still recognize the login attempt so we can tell the
            # ex-user their account was disabled (instead of "does not exist").
            user = User.query.filter_by(username='deactivated:' + username).first()
        if user:
            if check_password_hash(user.password_hash, password):
                if not user.is_active:
                    log_audit_event(
                        action='auth.login.failed',
                        entity_type='User',
                        entity_id=user.id,
                        reason='Account is deactivated.',
                        details={'username': username},
                        actor_user=user,
                        commit=True,
                    )
                    flash('This account has been deactivated. Contact an administrator.', category='error')
                else:
                    flash('Logged in successfully!', category='success')
                    login_user(user, remember=True)
                    now = datetime.now(timezone.utc)
                    user.last_activity_at = now
                    user.last_login_at = now
                    session['_presence_touch_epoch'] = now.timestamp()
                    log_audit_event(
                        action='auth.login.success',
                        entity_type='User',
                        entity_id=user.id,
                        reason='User authenticated successfully.',
                        details={'role': user.role},
                        actor_user=user,
                        commit=True,
                    )
                    return redirect(url_for('views.dashboard'))
            else:
                log_audit_event(
                    action='auth.login.failed',
                    entity_type='User',
                    entity_id=user.id,
                    reason='Incorrect password.',
                    details={'username': username},
                    actor_user=user,
                    commit=True,
                )
                flash('Incorrect password, try again.', category='error')
        else:
            log_audit_event(
                action='auth.login.failed',
                entity_type='User',
                entity_id=username or 'unknown',
                reason='Username does not exist.',
                details={'username': username},
                commit=True,
            )
            flash('Username does not exist.', category='error')

    return render_template('login.html')


@auth.route('/logout')
@login_required
def logout():
    actor = current_user
    actor.last_activity_at = None
    session.pop('_presence_touch_epoch', None)
    log_audit_event(
        action='auth.logout',
        entity_type='User',
        entity_id=actor.id,
        reason='User logged out.',
        details={'username': actor.username},
        actor_user=actor,
        commit=True,
    )
    logout_user()
    flash('Logged out successfully!', category='success')
    return redirect(url_for('auth.login'))