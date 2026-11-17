from __future__ import annotations

from functools import wraps
from typing import Any, Callable
from flask import flash, redirect, request, session, url_for
from db import get_db


def current_user() -> dict[str, Any] | None:
    """Return dictionary of currently logged-in user or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    with get_db() as db:
        user = db.execute("SELECT id, username, full_name, email, role, is_active FROM users WHERE id = ?", (user_id,)).fetchone()
        if user and user["is_active"]:
            return dict(user)
    return None


def login_required(f: Callable) -> Callable:
    """Decorator to require login for a route."""
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        if not session.get("user_id"):
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for("login", next=request.url))
        user = current_user()
        if not user:
            session.clear()
            flash("Your session is invalid or user account is inactive.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def role_required(roles: list[str]) -> Callable:
    """Decorator to require specific roles (e.g. ['admin', 'manager'])."""
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            user = current_user()
            if not user:
                flash("Please sign in to access this page.", "warning")
                return redirect(url_for("login"))
            if user.get("role") not in roles:
                flash(f"Access restricted. This action requires one of the following roles: {', '.join(roles).upper()}.", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
