from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from goa_eval.web.schemas import WebApiSettings


def require_write_access(request: Request, settings: WebApiSettings) -> None:
    expected = settings.write_api_key
    if not expected:
        if settings.require_write_auth:
            raise HTTPException(status_code=503, detail="write authentication is not configured")
        return
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="valid bearer token required", headers={"WWW-Authenticate": "Bearer"})
