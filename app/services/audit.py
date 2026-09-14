import json

from flask import has_request_context, request
from flask_login import current_user

from app.extensions import db
from app.models import AuditLog


def log_event(action, entity, entity_id=None, payload=None, user_id=None):
    actor_id = user_id
    if actor_id is None and current_user and current_user.is_authenticated:
        actor_id = current_user.id
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "") if has_request_context() else ""
    entry = AuditLog(
        user_id=actor_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        payload=json.dumps(payload or {}, ensure_ascii=False, default=str),
        ip_address=ip[:64],
    )
    db.session.add(entry)
    return entry
