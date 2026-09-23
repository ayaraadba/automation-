"""Optional HTTP Basic auth for the dashboard and REST API.

Set DASHBOARD_USERNAME / DASHBOARD_PASSWORD in production — the dashboard can
change your Instagram token, so it must not be open to the internet.
"""
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_basic = HTTPBasic(auto_error=False)


def auth_enabled() -> bool:
    return bool(os.getenv("DASHBOARD_PASSWORD"))


def require_dashboard_auth(creds: HTTPBasicCredentials | None = Depends(_basic)) -> None:
    password = os.getenv("DASHBOARD_PASSWORD")
    if not password:
        return
    username = os.getenv("DASHBOARD_USERNAME", "admin")
    ok = (
        creds is not None
        and secrets.compare_digest(creds.username.encode(), username.encode())
        and secrets.compare_digest(creds.password.encode(), password.encode())
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="dashboard"'},
        )
