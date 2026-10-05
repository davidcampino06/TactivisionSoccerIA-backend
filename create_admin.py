"""Creates (or updates) the pre-configured ADMINISTRATOR account.

Users can never self-register as ADMINISTRATOR. Run once per environment:

    ADMIN_EMAIL=admin@tactivision.com ADMIN_PASSWORD='a-strong-password' python create_admin.py
"""

import os
import sys

import database
from models import User, UserRole
from security import hash_password


def main() -> int:
    email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD") or ""
    if not email or len(password) < 12:
        print("Set ADMIN_EMAIL and ADMIN_PASSWORD (min. 12 characters).")
        return 1
    if database.SessionLocal is None:
        print("DATABASE_URL is not configured.")
        return 1
    with database.SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        if user and user.role != UserRole.ADMINISTRATOR:
            print("That email belongs to a non-administrator account.")
            return 1
        if user is None:
            user = User(email=email, first_name="Platform", last_name="Administrator", role=UserRole.ADMINISTRATOR,
                        password_hash=hash_password(password))
            db.add(user)
            action = "created"
        else:
            user.password_hash = hash_password(password)
            user.is_active = True
            action = "updated"
        db.commit()
    print(f"Administrator {email} {action}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
