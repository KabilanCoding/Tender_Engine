"""Create and manage ZYNEX users from the command line (there is no default account).

Run from the backend/ folder with the virtual environment active:

    python -m scripts.manage_users init-roles
    python -m scripts.manage_users create --email jane@company.com --name "Jane Doe" --role admin
    python -m scripts.manage_users list
    python -m scripts.manage_users set-password --email jane@company.com
    python -m scripts.manage_users deactivate --email jane@company.com
    python -m scripts.manage_users ensure-dev-admin     # development only: first-run login, prints a random password once

The password is asked for interactively (or read from the environment variable named by --password-env,
for automation). Passwords must be at least 12 characters.
"""
import argparse
import asyncio
import getpass
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.user import Role, User  # noqa: E402

ROLES = {
    "admin": "Full access, including settings and the knowledge base",
    "analyst": "Upload documents, run analysis, generate proposals",
    "viewer": "Read-only access to reports",
}
MIN_PASSWORD = 12


def read_password(env_name: str | None) -> str:
    if env_name:
        password = os.environ.get(env_name, "")
    else:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            sys.exit("Passwords do not match.")
    if len(password) < MIN_PASSWORD:
        sys.exit(f"Password must be at least {MIN_PASSWORD} characters.")
    return password


async def init_roles(db) -> dict:
    existing = {r.name: r for r in (await db.execute(select(Role))).scalars()}
    for name, description in ROLES.items():
        if name not in existing:
            existing[name] = Role(name=name, description=description)
            db.add(existing[name])
    await db.flush()
    return existing


async def run(args) -> None:
    async with AsyncSessionLocal() as db:
        roles = await init_roles(db)
        if args.command == "init-roles":
            print("roles ready:", ", ".join(sorted(roles)))
        elif args.command == "ensure-dev-admin":
            from app.core.config import settings
            if settings.env.ENVIRONMENT != "development":
                sys.exit("ensure-dev-admin only works with ENVIRONMENT=development. Use 'create' on a real server.")
            if (await db.execute(select(User).limit(1))).scalar_one_or_none() is not None:
                print("users already exist; no development account created")
            else:
                password = secrets.token_urlsafe(12)
                db.add(User(email="admin@zynex.local", full_name="Development Admin", role_id=roles["admin"].id,
                            hashed_password=hash_password(password)))
                print("\n  Development login created (shown once, change it with set-password):")
                print(f"    e-mail:    admin@zynex.local\n    password:  {password}\n")
        elif args.command == "list":
            for u in (await db.execute(select(User).order_by(User.id))).scalars():
                print(f"{u.id:>3}  {u.email:<35} {roles_by_id(roles, u.role_id):<8} {'active' if u.is_active else 'DISABLED'}  {u.full_name}")
        else:
            user = (await db.execute(select(User).where(User.email == args.email.lower()))).scalar_one_or_none()
            if args.command == "create":
                if user:
                    sys.exit(f"{args.email} already exists.")
                db.add(User(email=args.email.lower(), full_name=args.name, role_id=roles[args.role].id,
                            hashed_password=hash_password(read_password(args.password_env))))
                print(f"created {args.email} ({args.role})")
            elif user is None:
                sys.exit(f"No user {args.email}.")
            elif args.command == "set-password":
                user.hashed_password = hash_password(read_password(args.password_env))
                print(f"password updated for {args.email}")
            elif args.command == "deactivate":
                user.is_active = False
                print(f"{args.email} can no longer log in")
        await db.commit()
    await engine.dispose()


def roles_by_id(roles: dict, role_id: int) -> str:
    return next((n for n, r in roles.items() if r.id == role_id), "?")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage ZYNEX users")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-roles", help="create the admin/analyst/viewer roles if missing")
    sub.add_parser("list", help="list users")
    sub.add_parser("ensure-dev-admin", help="development only: create admin@zynex.local with a random password if there are no users")
    create = sub.add_parser("create", help="create a user")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--role", choices=sorted(ROLES), required=True)
    for name in ("create", "set-password"):
        p = create if name == "create" else sub.add_parser(name, help="change a password")
        if name == "set-password":
            p.add_argument("--email", required=True)
        p.add_argument("--password-env", help="read the password from this environment variable")
    deactivate = sub.add_parser("deactivate", help="block a user from logging in")
    deactivate.add_argument("--email", required=True)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
