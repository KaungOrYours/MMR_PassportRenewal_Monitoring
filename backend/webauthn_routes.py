"""Passkey (WebAuthn) device registration and login.

No username/password: the admin identity is a single fixed "admin" user,
and each enrolled device's Face ID/Touch ID key pair is a credential tied
to it. Device enrollment:

- The FIRST device ever registered requires API_SECRET as a one-time
  bootstrap proof (register_begin, when zero credentials exist yet).
- Every device after that requires either an active session (you're
  already logged in on this device) or a short-lived one-time enrollment
  code generated from an already-logged-in device (POST /enrollment-code)
  -- so API_SECRET is never used again once the first device exists.

Sessions are a bearer token, not a cookie -- see auth.py for why.
"""
import json
import os
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from webauthn import (
    base64url_to_bytes, generate_authentication_options, generate_registration_options,
    options_to_json, verify_authentication_response, verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorAttachment, AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
    ResidentKeyRequirement, UserVerificationRequirement,
)

from checker import db as models

from .auth import create_session, get_db, get_session_row, not_expired, require_session, utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])

RP_ID = os.environ.get("WEBAUTHN_RP_ID", "")
RP_ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", "")
RP_NAME = "MMR Passport Renewal Monitor"
CHALLENGE_TTL_SECONDS = 300
ENROLLMENT_CODE_TTL_SECONDS = 600


def _require_webauthn_config() -> None:
    if not RP_ID or not RP_ORIGIN:
        raise HTTPException(500, "WEBAUTHN_RP_ID / WEBAUTHN_ORIGIN not configured on the server")


@router.get("/status")
def status(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    has_credentials = db.query(models.WebAuthnCredential).count() > 0
    logged_in = get_session_row(authorization, db) is not None
    return {"has_credentials": has_credentials, "logged_in": logged_in}


class RegisterBeginRequest(BaseModel):
    device_label: str
    enrollment_code: str | None = None


@router.post("/register/begin")
def register_begin(
    payload: RegisterBeginRequest,
    x_api_key: str = Header(default=""),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_webauthn_config()
    credential_count = db.query(models.WebAuthnCredential).count()

    authorized = False
    if credential_count == 0:
        expected = os.environ.get("API_SECRET", "")
        authorized = bool(expected) and secrets.compare_digest(x_api_key, expected)
    else:
        if get_session_row(authorization, db) is not None:
            authorized = True
        if not authorized and payload.enrollment_code:
            code_row = db.get(models.EnrollmentCode, payload.enrollment_code.strip().upper())
            if code_row and not code_row.used and not_expired(code_row.expires_at):
                authorized = True
                code_row.used = True
                db.commit()

    if not authorized:
        raise HTTPException(401, "Not authorized to register a new device")

    existing = db.query(models.WebAuthnCredential).all()
    exclude = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in existing]

    options = generate_registration_options(
        rp_id=RP_ID, rp_name=RP_NAME, user_name="admin", user_id=b"admin", user_display_name="Admin",
        exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )

    token = secrets.token_urlsafe(16)
    db.add(models.WebAuthnChallenge(
        token=token, challenge=bytes_to_base64url(options.challenge), kind="registration",
        expires_at=utcnow() + timedelta(seconds=CHALLENGE_TTL_SECONDS),
    ))
    db.commit()

    return {"options": json.loads(options_to_json(options)), "challenge_token": token}


class RegisterCompleteRequest(BaseModel):
    credential: dict
    challenge_token: str
    device_label: str


@router.post("/register/complete")
def register_complete(payload: RegisterCompleteRequest, db: Session = Depends(get_db)):
    _require_webauthn_config()
    challenge_row = db.get(models.WebAuthnChallenge, payload.challenge_token)
    if challenge_row is None or challenge_row.kind != "registration" or not not_expired(challenge_row.expires_at):
        raise HTTPException(400, "Registration challenge expired or invalid -- try again")

    try:
        verification = verify_registration_response(
            credential=payload.credential,
            expected_challenge=base64url_to_bytes(challenge_row.challenge),
            expected_rp_id=RP_ID,
            expected_origin=RP_ORIGIN,
            require_user_verification=True,
        )
    except Exception as e:
        raise HTTPException(400, f"Registration verification failed: {e}")
    finally:
        db.delete(challenge_row)
        db.commit()

    db.add(models.WebAuthnCredential(
        credential_id=bytes_to_base64url(verification.credential_id),
        public_key=bytes_to_base64url(verification.credential_public_key),
        sign_count=verification.sign_count,
        device_label=payload.device_label.strip() or "Unnamed device",
    ))
    db.commit()

    token, _expires_at = create_session(db)
    return {"status": "registered", "session_token": token}


@router.post("/login/begin")
def login_begin(db: Session = Depends(get_db)):
    _require_webauthn_config()
    creds = db.query(models.WebAuthnCredential).all()
    if not creds:
        raise HTTPException(400, "No devices registered yet")

    allow = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in creds]
    options = generate_authentication_options(
        rp_id=RP_ID, allow_credentials=allow, user_verification=UserVerificationRequirement.REQUIRED,
    )

    token = secrets.token_urlsafe(16)
    db.add(models.WebAuthnChallenge(
        token=token, challenge=bytes_to_base64url(options.challenge), kind="authentication",
        expires_at=utcnow() + timedelta(seconds=CHALLENGE_TTL_SECONDS),
    ))
    db.commit()

    return {"options": json.loads(options_to_json(options)), "challenge_token": token}


class LoginCompleteRequest(BaseModel):
    credential: dict
    challenge_token: str


@router.post("/login/complete")
def login_complete(payload: LoginCompleteRequest, db: Session = Depends(get_db)):
    _require_webauthn_config()
    challenge_row = db.get(models.WebAuthnChallenge, payload.challenge_token)
    if challenge_row is None or challenge_row.kind != "authentication" or not not_expired(challenge_row.expires_at):
        raise HTTPException(400, "Login challenge expired or invalid -- try again")

    cred_id_b64 = payload.credential.get("id") if isinstance(payload.credential, dict) else None
    cred_row = db.query(models.WebAuthnCredential).filter_by(credential_id=cred_id_b64).first() if cred_id_b64 else None
    if cred_row is None:
        db.delete(challenge_row)
        db.commit()
        raise HTTPException(400, "Unknown credential")

    try:
        verification = verify_authentication_response(
            credential=payload.credential,
            expected_challenge=base64url_to_bytes(challenge_row.challenge),
            expected_rp_id=RP_ID,
            expected_origin=RP_ORIGIN,
            credential_public_key=base64url_to_bytes(cred_row.public_key),
            credential_current_sign_count=cred_row.sign_count,
            require_user_verification=True,
        )
    except Exception as e:
        raise HTTPException(400, f"Login verification failed: {e}")
    finally:
        db.delete(challenge_row)
        db.commit()

    cred_row.sign_count = verification.new_sign_count
    db.commit()

    token, _expires_at = create_session(db)
    return {"status": "logged_in", "session_token": token}


@router.post("/logout")
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    row = get_session_row(authorization, db)
    if row is not None:
        db.delete(row)
        db.commit()
    return {"status": "logged_out"}


@router.post("/enrollment-code", dependencies=[Depends(require_session)])
def create_enrollment_code(db: Session = Depends(get_db)):
    code = secrets.token_hex(4).upper()
    db.add(models.EnrollmentCode(
        code=code, expires_at=utcnow() + timedelta(seconds=ENROLLMENT_CODE_TTL_SECONDS),
    ))
    db.commit()
    return {"code": code, "expires_in_seconds": ENROLLMENT_CODE_TTL_SECONDS}


@router.get("/devices", dependencies=[Depends(require_session)])
def list_devices(db: Session = Depends(get_db)):
    rows = db.query(models.WebAuthnCredential).order_by(models.WebAuthnCredential.created_at).all()
    return [{"id": c.id, "device_label": c.device_label, "created_at": c.created_at} for c in rows]


@router.delete("/devices/{cred_id}", status_code=204, dependencies=[Depends(require_session)])
def revoke_device(cred_id: int, db: Session = Depends(get_db)):
    row = db.get(models.WebAuthnCredential, cred_id)
    if row is None:
        raise HTTPException(404, "Not found")
    if db.query(models.WebAuthnCredential).count() <= 1:
        raise HTTPException(400, "Cannot remove the last registered device -- you would lock yourself out")
    db.delete(row)
    db.commit()
