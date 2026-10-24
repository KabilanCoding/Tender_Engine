"""Print a long-lived login token for an automation account (n8n), which cannot solve the login captcha.

Create the account once (analyst role is enough):
    .venv/bin/python -m scripts.manage_users create --email n8n@zynex.local --name "n8n automation" --role analyst
Then:
    .venv/bin/python -m scripts.automation_token --email n8n@zynex.local [--days 365]

Paste the token into the n8n node as the header  Authorization: Bearer <token>.  It stops working after --days, when the
account is deactivated, or when SECRET_KEY changes. Treat it like a password.
"""
import argparse
import asyncio
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token
from app.models.user import User


async def main(email: str, days: int) -> None:
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).options(selectinload(User.role)).where(User.email == email))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise SystemExit(f"No active user {email}. Create it first (see the top of this file).")
    if user.role.name not in ("admin", "analyst"):
        raise SystemExit(f"{email} is a {user.role.name}; automatic analysis needs an analyst or admin account.")
    token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role.name}, timedelta(days=days))
    print(f"Token for {email} ({user.role.name}), valid {days} days:\n\n{token}\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--days", type=int, default=365)
    a = p.parse_args()
    asyncio.run(main(a.email, a.days))
