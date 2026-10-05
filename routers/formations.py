"""Formation catalogue. The ERD has no team_id on formations, so they are shared
(e.g. 4-3-3); they contain no private tactical content."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models import Formation, User, UserRole
from schemas import FormationCreate, FormationOut

router = APIRouter(prefix="/api/formations", tags=["Formations"])


@router.get("", response_model=list[FormationOut])
def list_formations(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Formation).order_by(Formation.name).all()


@router.post("", response_model=FormationOut, status_code=status.HTTP_201_CREATED)
def create_formation(body: FormationCreate, _: User = Depends(require_roles(UserRole.COACH, UserRole.ANALYST)),
                     db: Session = Depends(get_db)):
    if db.query(Formation).filter(Formation.name == body.name).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Formation already exists.")
    formation = Formation(**body.model_dump())
    db.add(formation)
    db.commit()
    return formation
