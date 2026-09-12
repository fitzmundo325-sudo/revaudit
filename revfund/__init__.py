import os
import json
import secrets
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import Flask, redirect, render_template, request, session, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user, logout_user
from flask_caching import Cache
from sqlalchemy import text
from werkzeug.exceptions import HTTPException

db = SQLAlchemy()
cache = Cache()

PRIVILEGED_ROLES = ('Superadmin', 'General Manager', 'Admin', 'Auditor')

# All selectable roles, in ascending order of privilege.
ROLES = ('Staff', 'Auditor', 'General Manager', 'Admin', 'Superadmin')

# Ledger access levels, chosen separately from the role.
ACCESS_LEVELS = ('Viewer', 'Editor')

# Roles allowed to manage user accounts (User Management page).
USER_MANAGEMENT_ROLES = ('Superadmin', 'Admin')

# Roles that always have full ledger access regardless of access level.
PRIVILEGED_DATA_ROLES = ('Superadmin', 'Admin', 'Auditor')


def _ensure_user_access_level_column():
    with db.engine.connect() as conn:
        existing_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info('users')")).fetchall()
        }

        if 'access_level' not in existing_columns:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN access_level VARCHAR(20) "
                "NOT NULL DEFAULT 'Viewer'"
            ))
        conn.commit()

DB_NAME = 'revfund.db'


def _load_local_env():
    env_path = Path(__file__).resolve().parent.parent / '.env'
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue

        key, value = line.split('=', 1)
        key = key.strip()
        if not key:
            continue

        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _ensure_user_role_column():
    with db.engine.connect() as conn:
        existing_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info('users')")).fetchall()
        }

        if 'role' not in existing_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(100) NOT NULL DEFAULT 'Admin'"))
        conn.commit()


def _ensure_user_presence_column():
    with db.engine.connect() as conn:
        existing_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info('users')")).fetchall()
        }

        if 'last_activity_at' not in existing_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_activity_at DATETIME"))
        if 'last_login_at' not in existing_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_login_at DATETIME"))
        conn.commit()


def _ensure_expense_trxn_code_column():
    with db.engine.connect() as conn:
        existing_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info('expenses')")).fetchall()
        }

        if 'trxn_code' not in existing_columns:
            conn.execute(text("ALTER TABLE expenses ADD COLUMN trxn_code VARCHAR(128)"))
        conn.commit()


def seed_if_empty():
    from .models import Expense
    from .views import parse_date

    if Expense.query.first() is not None:
        return
    seed_path = os.path.join(Path(__file__).resolve().parent.parent, 'seed_data.json')
    if not os.path.exists(seed_path):
        return
    with open(seed_path, encoding='utf-8') as f:
        rows = json.load(f)
    for r in rows:
        db.session.add(Expense(
            unit=r['unit'],
            payee=r['payee'],
            branch=r['branch'],
            trxn_date=parse_date(r['trxn_date']),
            particulars=r['particulars'],
            ref_no=r['ref_no'],
            account_title=r['account_title'],
            tin=r['tin'],
            address=r['address'],
            amount=r['amount'],
        ))
    db.session.commit()


def seed_user_if_empty():
    from .models import User
    from werkzeug.security import generate_password_hash

    if User.query.first():
        return
    db.session.add(User(username='Jenny', password_hash=generate_password_hash('jenny_081226'), role='Auditor', access_level='Editor'))
    db.session.add(User(username='Queben', password_hash=generate_password_hash('qjdc.cfi'), role='General Manager', access_level='Viewer'))
    db.session.add(User(username='admin', password_hash=generate_password_hash('admin123'), role='Admin', access_level='Editor'))
    db.session.commit()


def create_app():
    _load_local_env()
    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        instance_path=str(project_root / 'instance'),
        template_folder=str(project_root / 'templates'),
        static_folder=str(project_root / 'static'),
    )
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, DB_NAME)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    configured_secret_key = os.environ.get('REVFUND_SECRET_KEY')
    secret_key = configured_secret_key
    if not secret_key:
        secret_key = secrets.token_hex(32)
    app.config['SECRET_KEY'] = secret_key

    db.init_app(app)

    cache.init_app(app, config={
        'CACHE_TYPE': 'SimpleCache',
        'CACHE_DEFAULT_TIMEOUT': 300,
    })

    from .views import views
    from .auth import auth
    from .api_handles import api_handles
    from .user_admin import user_admin

    app.register_blueprint(auth, url_prefix='/')
    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(api_handles, url_prefix='/apis')
    app.register_blueprint(user_admin, url_prefix='/')

    from .models import (
        User,
        Expense,
        AuditLog,
        SystemSecret,
        MaintenanceMode,
    )

    with app.app_context():
        db.create_all()
        if not configured_secret_key:
            stored_secret = SystemSecret.query.order_by(SystemSecret.id.asc()).first()
            if not stored_secret:
                stored_secret = SystemSecret(secret_value=secrets.token_hex(32))
                db.session.add(stored_secret)
                db.session.commit()
            app.config['SECRET_KEY'] = stored_secret.secret_value
        _ensure_user_role_column()
        _ensure_user_access_level_column()
        _ensure_user_presence_column()
        _ensure_expense_trxn_code_column()
        seed_user_if_empty()
        seed_if_empty()
        print("Created database!")

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please login to access this page.'
    login_manager.login_message_category = 'info'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))

    @app.route('/maintenance')
    def maintenance():
        mode = MaintenanceMode.query.first()
        if not mode or not mode.is_enabled:
            return redirect(url_for('auth.login'))
        if current_user.is_authenticated and getattr(current_user, 'role', None) in PRIVILEGED_ROLES:
            return redirect(url_for('views.dashboard'))
        return render_template('maintenance.html', maintenance_mode=mode)

    app.config['SESSION_IDLE_TIMEOUT_SECONDS'] = int(os.environ.get('SESSION_IDLE_TIMEOUT_SECONDS', str(15 * 60)))

    @app.before_request
    def enforce_maintenance_mode():
        if request.endpoint in ('static', 'auth.login', 'auth.logout', 'maintenance'):
            return None
        if not current_user.is_authenticated:
            return None
        if getattr(current_user, 'role', None) in PRIVILEGED_ROLES:
            return None
        mode = MaintenanceMode.query.first()
        if mode and mode.is_enabled:
            return redirect(url_for('maintenance'))
        return None

    @app.before_request
    def enforce_idle_logout():
        if request.endpoint in ('static', 'auth.login', 'auth.logout', 'maintenance'):
            return None
        if not current_user.is_authenticated:
            return None

        timeout_seconds = app.config.get('SESSION_IDLE_TIMEOUT_SECONDS', 60 * 60)
        last_touch = float(session.get('_presence_touch_epoch', 0) or 0)
        if not last_touch:
            session['_presence_touch_epoch'] = datetime.now(timezone.utc).timestamp()
            return None

        if (datetime.now(timezone.utc).timestamp() - last_touch) <= timeout_seconds:
            return None

        session.clear()
        try:
            current_user.last_activity_at = None
            db.session.add(current_user)
            db.session.commit()
        except Exception:
            db.session.rollback()
        logout_user()
        flash('You were logged out because the session was idle for too long. Please log in again.', category='info')
        return redirect(url_for('auth.login'))

    @app.before_request
    def track_authenticated_user_presence():
        if request.endpoint in ('static', 'auth.login', 'auth.logout'):
            return None
        if not current_user.is_authenticated:
            return None

        now = datetime.now(timezone.utc)
        last_touch = float(session.get('_presence_touch_epoch', 0) or 0)
        if now.timestamp() - last_touch < 60:
            return None

        current_user.last_activity_at = now
        session['_presence_touch_epoch'] = now.timestamp()
        db.session.commit()
        return None

    @app.context_processor
    def inject_maintenance_mode():
        mode = MaintenanceMode.query.first()
        return {'system_maintenance_mode': mode}

    @app.context_processor
    def inject_permissions():
        return {
            'can_modify_data': current_user.can_modify_data
                               if current_user.is_authenticated else False,
        }

    LOCAL_UTC_OFFSET = timezone(timedelta(hours=8))

    @app.template_filter('local_dt')
    def _local_dt(value):
        if not value:
            return ''
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(LOCAL_UTC_OFFSET).strftime('%Y-%m-%d %H:%M:%S')

    def _safe_error_form_snapshot():
        sensitive_markers = ('password', 'secret', 'token', 'csrf')
        snapshot = {}
        try:
            for key in request.form.keys():
                normalized_key = str(key or '').lower()
                values = request.form.getlist(key)
                if any(marker in normalized_key for marker in sensitive_markers):
                    snapshot[key] = '[redacted]'
                elif len(values) > 1:
                    snapshot[key] = [str(value)[:300] for value in values[:20]]
                else:
                    snapshot[key] = str(values[0] if values else '')[:300]
        except Exception:
            return {'_error': 'Unable to read form payload.'}
        return snapshot

    def _log_application_error(error, status_code=None):
        error_id = uuid.uuid4().hex[:12]
        status = int(status_code or getattr(error, 'code', 500) or 500)
        error_type = type(error).__name__
        message = str(getattr(error, 'description', None) or error)
        details = {
            'error_id': error_id,
            'status_code': status,
            'exception_type': error_type,
            'message': message[:1000],
            'path': request.path,
            'full_path': request.full_path,
            'endpoint': request.endpoint,
            'blueprint': request.blueprint,
            'method': request.method,
            'query_args': request.args.to_dict(flat=False),
            'form': _safe_error_form_snapshot() if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') else {},
            'user_agent': str(request.user_agent)[:500],
            'referrer': str(request.referrer or '')[:500],
            'is_json': request.is_json,
        }
        if status >= 500 and not isinstance(error, HTTPException):
            details['traceback'] = ''.join(
                traceback.format_exception(type(error), error, getattr(error, '__traceback__', None))
            )[-8000:]

        try:
            db.session.rollback()
            from .audit import log_audit_event

            log_audit_event(
                action='system.error',
                entity_type='ApplicationError',
                entity_id=error_id,
                reason=f'{status} {error_type} on {request.method} {request.path}',
                details=details,
                commit=True,
            )
        except Exception:
            db.session.rollback()
            app.logger.exception('Unable to write application error to audit log. error_id=%s', error_id)

        app.logger.error(
            'Application error captured. error_id=%s status=%s path=%s type=%s',
            error_id,
            status,
            request.path,
            error_type,
            exc_info=status >= 500 and not isinstance(error, HTTPException),
        )
        return error_id

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        status = int(getattr(error, 'code', 500) or 500)
        # Only log server errors (500+), not client errors (400-499)
        if status >= 500:
            _log_application_error(error, status)
        return error

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error):
        error_id = _log_application_error(error, 500)
        return (
            f'Internal Server Error. Error ID: {error_id}',
            500,
            {'Content-Type': 'text/plain; charset=utf-8'},
        )

    return app