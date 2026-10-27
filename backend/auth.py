import os
import secrets

from fastapi import Header, HTTPException


def require_api_key(x_api_key: str = Header(default="")) -> None:
    expected = os.environ.get("API_SECRET", "")
    if not expected or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
