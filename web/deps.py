from typing import Optional
from fastapi import Request

import db


def current_uid(request: Request) -> Optional[str]:
    return request.session.get("user_id")


def set_flash(request: Request, level: str, message: str) -> None:
    msgs = request.session.get("flash", [])
    msgs.append({"level": level, "message": message})
    request.session["flash"] = msgs


def pop_flash(request: Request) -> list:
    return request.session.pop("flash", [])


def require_user(request: Request) -> Optional[str]:
    """Returns the current user id, or None. Callers must redirect if None."""
    return current_uid(request)


def current_user_record(request: Request) -> Optional[dict]:
    uid = current_uid(request)
    return db.get_user(uid) if uid else None