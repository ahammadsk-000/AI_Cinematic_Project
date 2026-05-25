"""Shared FastAPI dependencies: DB session, service factories, current-user auth."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.job_service import JobService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")

DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_auth_service(db: DbSession) -> AuthService:
    return AuthService(db)


def get_job_service(db: DbSession) -> JobService:
    return JobService(db)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    claims = decode_access_token(token)
    if not claims or "sub" not in claims:
        raise creds_exc
    try:
        user_id = uuid.UUID(claims["sub"])
    except (ValueError, TypeError):
        raise creds_exc
    user = await auth.users.get(user_id)
    if not user or not user.is_active:
        raise creds_exc
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AuthSvc = Annotated[AuthService, Depends(get_auth_service)]
JobSvc = Annotated[JobService, Depends(get_job_service)]
