from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import IntegrityError

from . import db, ROLES, ACCESS_LEVELS, USER_MANAGEMENT_ROLES
from .models import User, AuditLog
from .audit import log_audit_event

user_admin = Blueprint('user_admin', __name__)

ADMIN_ROLES = ('Superadmin', 'Admin')


def _can_manage_users():
    return getattr(current_user, 'role', '') in USER_MANAGEMENT_ROLES


def _deny():
    flash('You do not have permission to manage users.', 'danger')
    return redirect(url_for('views.dashboard'))


def _other_active_admins(exclude_user_id):
    """Count active Admin/Superadmin accounts other than the given user."""
    return User.query.filter(
        User.role.in_(ADMIN_ROLES),
        User.is_active == True,  # noqa: E712
        User.id != exclude_user_id,
    ).count()


@user_admin.route('/admin/users')
@login_required
def users():
    if not _can_manage_users():
        return _deny()
    all_users = User.query.order_by(User.id.asc()).all()
    return render_template('users.html', users=all_users, roles=ROLES,
                           access_levels=ACCESS_LEVELS)


@user_admin.route('/admin/users/add', methods=['POST'])
@login_required
def add_user():
    if not _can_manage_users():
        return _deny()

    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    role = request.form.get('role') or 'Staff'
    access_level = request.form.get('access_level') or 'Viewer'
    is_active = request.form.get('is_active') == 'on'

    if not username:
        flash('Username is required.', 'danger')
        return redirect(url_for('user_admin.users'))
    if len(password) < 4:
        flash('Password must be at least 4 characters long.', 'danger')
        return redirect(url_for('user_admin.users'))
    if role not in ROLES:
        flash('Invalid role selected.', 'danger')
        return redirect(url_for('user_admin.users'))
    if access_level not in ACCESS_LEVELS:
        flash('Invalid access level selected.', 'danger')
        return redirect(url_for('user_admin.users'))
    if User.query.filter_by(username=username).first():
        flash(f'Username "{username}" already exists.', 'danger')
        return redirect(url_for('user_admin.users'))

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
        access_level=access_level,
        is_active=is_active,
    )
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('Could not create user — the username may already exist.', 'danger')
        return redirect(url_for('user_admin.users'))

    log_audit_event(
        action='user.create',
        entity_type='User',
        entity_id=user.id,
        reason=f'Created user "{username}" with role {role} ({access_level}).',
        details={'username': username, 'role': role, 'access_level': access_level, 'is_active': is_active},
        commit=True,
    )
    flash(f'User "{username}" created with role {role} ({access_level}).', 'success')
    return redirect(url_for('user_admin.users'))


@user_admin.route('/admin/users/<int:user_id>/edit', methods=['POST'])
@login_required
def edit_user(user_id):
    if not _can_manage_users():
        return _deny()

    user = User.query.get_or_404(user_id)
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    role = request.form.get('role') or user.role
    access_level = request.form.get('access_level') or user.access_level
    is_active = request.form.get('is_active') == 'on'

    if not username:
        flash('Username is required.', 'danger')
        return redirect(url_for('user_admin.users'))
    # Accept the user's existing (possibly legacy) role unchanged; only
    # validate when the admin is actually switching to a different role.
    if role not in ROLES and role != user.role:
        flash('Invalid role selected.', 'danger')
        return redirect(url_for('user_admin.users'))
    if access_level not in ACCESS_LEVELS:
        flash('Invalid access level selected.', 'danger')
        return redirect(url_for('user_admin.users'))
    if password and len(password) < 4:
        flash('Password must be at least 4 characters long.', 'danger')
        return redirect(url_for('user_admin.users'))
    if User.query.filter(User.username == username, User.id != user.id).first():
        flash(f'Username "{username}" is already taken.', 'danger')
        return redirect(url_for('user_admin.users'))
    if user.id == current_user.id and not is_active:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('user_admin.users'))

    # Never lock the system out of user management: an active Admin/Superadmin
    # must always remain.
    losing_admin = (user.role in ADMIN_ROLES) and (
        role not in ADMIN_ROLES or (user.is_active and not is_active)
    )
    if losing_admin and _other_active_admins(user.id) == 0:
        flash('Cannot remove the last active administrator account.', 'danger')
        return redirect(url_for('user_admin.users'))

    changes = {}
    if username != user.username:
        changes['username'] = {'from': user.username, 'to': username}
        user.username = username
    if role != user.role:
        changes['role'] = {'from': user.role, 'to': role}
        user.role = role
    if access_level != user.access_level:
        changes['access_level'] = {'from': user.access_level, 'to': access_level}
        user.access_level = access_level
    if is_active != user.is_active:
        changes['is_active'] = {'from': user.is_active, 'to': is_active}
        user.is_active = is_active
    if password:
        changes['password'] = 'changed'
        user.password_hash = generate_password_hash(password)

    if not changes:
        flash('No changes were made.', 'info')
        return redirect(url_for('user_admin.users'))

    db.session.commit()
    log_audit_event(
        action='user.update',
        entity_type='User',
        entity_id=user.id,
        reason=f'Updated user "{user.username}".',
        details={'changes': changes},
        commit=True,
    )
    flash(f'User "{user.username}" updated.', 'success')
    return redirect(url_for('user_admin.users'))


@user_admin.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    if not _can_manage_users():
        return _deny()

    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('user_admin.users'))

    if user.role in ADMIN_ROLES and user.is_active and _other_active_admins(user.id) == 0:
        flash('Cannot delete the last active administrator account.', 'danger')
        return redirect(url_for('user_admin.users'))

    # Keep the audit chain meaningful: users with recorded events stay
    # (deactivate the account instead of deleting it).
    has_history = db.session.query(AuditLog.id).filter(
        AuditLog.actor_user_id == user.id
    ).first() is not None
    if has_history:
        flash(
            f'"{user.username}" has audit-trail history and cannot be deleted. '
            'Deactivate the account instead.',
            'warning',
        )
        return redirect(url_for('user_admin.users'))

    username = user.username
    db.session.delete(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash(
            f'"{user.username}" is referenced by existing records and cannot be '
            'deleted. Deactivate the account instead.',
            'warning',
        )
        return redirect(url_for('user_admin.users'))

    log_audit_event(
        action='user.delete',
        entity_type='User',
        entity_id=user_id,
        reason=f'Deleted user "{username}".',
        details={'username': username, 'role': user.role},
        commit=True,
    )
    flash(f'User "{username}" deleted.', 'info')
    return redirect(url_for('user_admin.users'))
