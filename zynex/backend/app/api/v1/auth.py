from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.core.security import verify_password, create_access_token
from app.models.user import User
from app.core.dependencies import get_db
from app.core import captcha

router = APIRouter(prefix="/auth", tags=["auth"])


class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    full_name: str


@router.get("/captcha")
async def get_captcha():
    """A new login challenge: an SVG image and the id to send back with the answer."""
    cid, svg = captcha.new_challenge()
    return {"captcha_id": cid, "svg": svg}


@router.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    captcha_id: str = Form(""),
    captcha_answer: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    # the captcha is checked first, before the password, so guessing passwords needs a solved image each time
    if not captcha.verify(captcha_id, captcha_answer):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The security code is not correct. Try the new code.")
    result = await db.execute(
        select(User).where(User.email == form_data.username).options(selectinload(User.role))
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    token = create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role.name}
    )
    return Token(
        access_token=token,
        token_type="bearer",
        role=user.role.name,
        full_name=user.full_name,
    )
