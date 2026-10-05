"""Administrator: manage users and view registered teams (no tactical content)."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_roles
from models import Team, User, UserRole
from schemas import AdminUserUpdate, TeamSummaryOut, UserOut

router = APIRouter(prefix="/api/admin", tags=["Administration"])
admin_only = require_roles(UserRole.ADMINISTRATOR)


@router.get("/users", response_model=list[UserOut])
def list_users(role: str | None = Query(default=None), _: User = Depends(admin_only), db: Session = Depends(get_db)):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role.upper())
    return query.order_by(User.created_at.desc()).all()


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: AdminUserUpdate, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if user.role == UserRole.ADMINISTRATOR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator accounts are managed by configuration.")
    if body.role and body.role != user.role:
        owns_team = db.query(Team).filter(Team.coach_id == user.id).first()
        if owns_team or user.team_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Cannot change the role of a user linked to a team.")
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    db.commit()
    return user


@router.get("/teams", response_model=list[TeamSummaryOut])
def list_registered_teams(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    return db.query(Team).order_by(Team.created_at.desc()).all()
