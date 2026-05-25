"""Authentication use-cases: register, authenticate, issue token, resolve current user.

Composes the user repository with the pure crypto helpers in core.security.
Raises domain exceptions (never HTTPException) so it stays framework-agnostic.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError, ConflictError, NotFoundError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.user import Token, UserCreate, UserRead


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)

    async def register(self, data: UserCreate) -> Token:
        if await self.users.get_by_email(data.email):
            raise ConflictError("An account with this email already exists.")
        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
        )
        await self.users.add(user)
        return self._issue(user)

    async def authenticate(self, email: str, password: str) -> Token:
        user = await self.users.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise AuthError("Incorrect email or password.")
        if not user.is_active:
            raise AuthError("This account is disabled.")
        return self._issue(user)

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self.users.get(user_id)
        if not user:
            raise NotFoundError("User not found.")
        return user

    @staticmethod
    def _issue(user: User) -> Token:
        token = create_access_token(subject=str(user.id))
        return Token(access_token=token, user=UserRead.model_validate(user))
