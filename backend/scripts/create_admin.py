"""Create an administrator or reset an existing account's password locally."""

import argparse
from getpass import getpass

from sqlalchemy import delete, func, select

from app.data_service.auth import hash_password
from app.data_service.settings import DataServiceSettings
from app.persistence.database import create_database_engine, create_session_factory, session_scope
from app.persistence.models import AuditLog, AuthSession, User


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name")
    parser.add_argument("--reset-password", action="store_true")
    args = parser.parse_args()
    email = args.email.strip().lower()
    if "@" not in email or " " in email or len(email) > 320:
        parser.error("Provide a valid email address")
    if not args.reset_password and (not args.name or not args.name.strip() or len(args.name) > 200):
        parser.error("--name is required for new accounts (1-200 characters)")
    password = getpass("New password (at least 12 characters): ")
    if not 12 <= len(password) <= 1024 or password != getpass("Repeat password: "):
        parser.error("Passwords must match and contain 12-1024 characters")
    engine = create_database_engine(DataServiceSettings().database_url())
    try:
        with session_scope(create_session_factory(engine)) as session:
            user = session.scalar(
                select(User).where(func.lower(User.email) == email).with_for_update()
            )
            if args.reset_password:
                if user is None:
                    parser.error("Account does not exist")
                user.password_hash = hash_password(password)
                session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
                action = "password_reset_cli"
            else:
                if user is not None:
                    parser.error("Account already exists; use --reset-password if needed")
                user = User(
                    email=email,
                    name=args.name.strip(),
                    role="admin",
                    password_hash=hash_password(password),
                )
                session.add(user)
                session.flush()
                action = "admin_created_cli"
            session.add(
                AuditLog(
                    action=action,
                    entity_type="user",
                    entity_id=str(user.id),
                    details={"source": "local_cli"},
                )
            )
        print("Account updated. Sign in through /api/v1/auth/login.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
