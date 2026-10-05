"""Authentication: register, login, logout, password recovery, profile."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from dependencies import get_current_user
from models import User
from schemas import (
    ChangePasswordRequest, LoginRequest, PasswordRecoveryRequest, PasswordResetRequest, ProfileUpdate,
    RegisterRequest, TokenResponse, UserOut,
)
from security import (
    InvalidTokenError, create_access_token, create_password_reset_token, decode_password_reset_token,
    hash_password, password_fingerprint, verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _token_response(user: User) -> dict:
    return {"access_token": create_access_token(user.id, user.role), "user": user}


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered.")
    user = User(first_name=body.first_name.strip(), last_name=body.last_name.strip(), email=email,
                phone=body.phone, role=body.role, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled.")
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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    user = db.get(User, payload["sub"])
    if user is None or payload.get("fp") != password_fingerprint(user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token already used or invalid.")
    user.password_hash = hash_password(body.new_password)
    db.commit()


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
    if not verify_password(body.current_password, db_user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    db_user.password_hash = hash_password(body.new_password)
    db.commit()
