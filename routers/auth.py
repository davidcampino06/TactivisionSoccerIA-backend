"""Authentication: register, login, logout, password recovery, profile.

Passwords arrive encrypted with RSA-OAEP (see password_crypto.py), are checked against the
password rules (password_policy.py) and stored only as bcrypt hashes. Every error carries a
``code`` that the frontend translates to Spanish.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from dependencies import get_current_user
from errors import AppError
from models import User
from password_crypto import public_key_spki_base64, reveal_password
from password_policy import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, failed_rules
from schemas import (
    ChangePasswordRequest, LoginRequest, PasswordRecoveryRequest, PasswordResetRequest, ProfileUpdate,
    RegisterRequest, TokenResponse, UserOut,
)
from security import (
    InvalidTokenError, create_access_token, create_password_reset_token, decode_password_reset_token,
    hash_password, password_fingerprint, verify_password,
)
from services.login_attempts import get_login_attempt_tracker

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _token_response(user: User) -> dict:
    return {"access_token": create_access_token(user.id, user.role), "user": user}


def _enforce_password_rules(password: str, *, email: str, first_name: str, last_name: str) -> None:
    broken = failed_rules(password, email=email, first_name=first_name, last_name=last_name)
    if broken:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "PASSWORD_POLICY",
                       "The password does not meet the password rules.", failed_rules=broken)


@router.get("/public-key")
def public_key():
    """Public key the browser uses to encrypt passwords before sending them."""
    return {
        "algorithm": "RSA-OAEP-256",
        "format": "spki-base64",
        "key": public_key_spki_base64(),
        "password_rules": {"min_length": PASSWORD_MIN_LENGTH, "max_length": PASSWORD_MAX_LENGTH},
    }


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    first_name, last_name = body.first_name.strip(), body.last_name.strip()
    password = reveal_password(body.password)
    _enforce_password_rules(password, email=email, first_name=first_name, last_name=last_name)
    if db.query(User).filter(User.email == email).first():
        raise AppError(status.HTTP_409_CONFLICT, "EMAIL_TAKEN", "Email is already registered.")
    user = User(first_name=first_name, last_name=last_name, email=email,
                phone=body.phone, role=body.role, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    tracker = get_login_attempt_tracker()
    locked_seconds = tracker.seconds_locked(email)
    if locked_seconds:
        raise AppError(status.HTTP_429_TOO_MANY_REQUESTS, "ACCOUNT_LOCKED",
                       "Too many failed attempts. Try again later.",
                       headers={"Retry-After": str(locked_seconds)}, retry_after_seconds=locked_seconds)

    password = reveal_password(body.password)
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(password, user.password_hash):
        remaining = tracker.record_failure(email)
        if remaining == 0:
            seconds = tracker.seconds_locked(email)
            raise AppError(status.HTTP_429_TOO_MANY_REQUESTS, "ACCOUNT_LOCKED",
                           "Too many failed attempts. Try again later.",
                           headers={"Retry-After": str(seconds)}, retry_after_seconds=seconds)
        raise AppError(status.HTTP_401_UNAUTHORIZED, "INVALID_CREDENTIALS", "Invalid email or password.",
                       remaining_attempts=remaining)
    if not user.is_active:
        raise AppError(status.HTTP_403_FORBIDDEN, "ACCOUNT_DISABLED", "Account is disabled.")
    tracker.record_success(email)
    return _token_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(_: User = Depends(get_current_user)):
    """JWT is stateless: the client deletes the token. Tokens also expire automatically."""


@router.post("/password-recovery", status_code=status.HTTP_202_ACCEPTED)
def password_recovery(body: PasswordRecoveryRequest, db: Session = Depends(get_db)):
    response = {"message": "If the email is registered, recovery instructions were generated."}
    user = db.query(User).filter(User.email == body.email.lower(), User.is_active.is_(True)).first()
    if user and settings.password_reset_expose_token:
        # Development only: there is no e-mail service yet.
        response["reset_token"] = create_password_reset_token(user.id, user.password_hash)
        response["warning"] = "DEVELOPMENT MODE: token returned in the response instead of by e-mail."
    return response


@router.post("/password-reset", status_code=status.HTTP_204_NO_CONTENT)
def password_reset(body: PasswordResetRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_password_reset_token(body.token)
    except InvalidTokenError as error:
        raise AppError(status.HTTP_400_BAD_REQUEST, "INVALID_RESET_TOKEN", str(error)) from error
    user = db.get(User, payload["sub"])
    if user is None or payload.get("fp") != password_fingerprint(user.password_hash):
        raise AppError(status.HTTP_400_BAD_REQUEST, "INVALID_RESET_TOKEN", "Token already used or invalid.")
    new_password = reveal_password(body.new_password)
    _enforce_password_rules(new_password, email=user.email, first_name=user.first_name, last_name=user.last_name)
    user.password_hash = hash_password(new_password)
    db.commit()
    get_login_attempt_tracker().record_success(user.email)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=UserOut)
def update_profile(body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.merge(user)
    db.commit()
    return db.get(User, user.id)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_user = db.get(User, user.id)
    if not verify_password(reveal_password(body.current_password), db_user.password_hash):
        raise AppError(status.HTTP_400_BAD_REQUEST, "CURRENT_PASSWORD_INCORRECT", "Current password is incorrect.")
    new_password = reveal_password(body.new_password)
    _enforce_password_rules(new_password, email=db_user.email, first_name=db_user.first_name,
                            last_name=db_user.last_name)
    if verify_password(new_password, db_user.password_hash):
        raise AppError(status.HTTP_400_BAD_REQUEST, "PASSWORD_REUSED", "The new password must be different.")
    db_user.password_hash = hash_password(new_password)
    db.commit()
