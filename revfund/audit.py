import hashlib
import json
from datetime import datetime

from flask import request
from flask_login import current_user

from . import db
from .models import AuditLog


def _request_ip():
    forwarded_for = request.headers.get('X-Forwarded-For', '').strip()
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.remote_addr


def _normalize_details(details):
    if details is None:
        return {}
    if isinstance(details, (dict, list)):
        return details
    return {'value': str(details)}


def _details_to_text(details):
    return json.dumps(_normalize_details(details), sort_keys=True, default=str)


def _event_payload(
    *,
    event_time,
    actor_user_id,
    actor_username,
    action,
    entity_type,
    entity_id,
    reason,
    ip_address,
    endpoint,
    http_method,
    details_text,
    previous_hash,
):
    return {
        'event_time': event_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
        'actor_user_id': actor_user_id,
        'actor_username': actor_username,
        'action': action,
        'entity_type': entity_type,
        'entity_id': entity_id,
        'reason': reason,
        'ip_address': ip_address,
        'endpoint': endpoint,
        'http_method': http_method,
        'details': details_text,
        'previous_hash': previous_hash,
    }


def _compute_hash(payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def log_audit_event(action, entity_type=None, entity_id=None, reason=None, details=None, actor_user=None, commit=False):
    if not action:
        raise ValueError('Audit action is required')

    event_time = datetime.utcnow()
    actor = actor_user
    if actor is None and getattr(current_user, 'is_authenticated', False):
        actor = current_user

    actor_user_id = getattr(actor, 'id', None)
    actor_username = getattr(actor, 'username', None)
    details_text = _details_to_text(details)

    previous_entry = AuditLog.query.order_by(AuditLog.id.desc()).first()
    previous_hash = previous_entry.current_hash if previous_entry else None

    payload = _event_payload(
        event_time=event_time,
        actor_user_id=actor_user_id,
        actor_username=actor_username,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        reason=reason,
        ip_address=_request_ip(),
        endpoint=request.path,
        http_method=request.method,
        details_text=details_text,
        previous_hash=previous_hash,
    )

    entry = AuditLog(
        event_time=event_time,
        actor_user_id=actor_user_id,
        actor_username=actor_username,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        reason=reason,
        ip_address=payload['ip_address'],
        endpoint=payload['endpoint'],
        http_method=payload['http_method'],
        details=details_text,
        previous_hash=previous_hash,
        current_hash=_compute_hash(payload),
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
    return entry


def verify_audit_chain(logs=None):
    if logs is None:
        logs = AuditLog.query.order_by(AuditLog.id.asc()).all()
    else:
        logs = sorted(list(logs), key=lambda item: item.id)

    tampered_ids = set()
    expected_previous_hash = None

    for log in logs:
        payload = _event_payload(
            event_time=log.event_time,
            actor_user_id=log.actor_user_id,
            actor_username=log.actor_username,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            reason=log.reason,
            ip_address=log.ip_address,
            endpoint=log.endpoint,
            http_method=log.http_method,
            details_text=log.details or '{}',
            previous_hash=expected_previous_hash,
        )
        expected_hash = _compute_hash(payload)
        if log.previous_hash != expected_previous_hash or log.current_hash != expected_hash:
            tampered_ids.add(log.id)
        expected_previous_hash = log.current_hash

    return tampered_ids


def reset_audit_logs():
    """Clear all audit logs and log the reset action."""
    count = AuditLog.query.delete()
    db.session.commit()
    
    # Log the reset action
    log_audit_event(
        action='AUDIT_LOGS_RESET',
        entity_type='AuditLog',
        reason=f'Admin reset: cleared {count} entries',
        commit=True
    )
    
    return count