"""Database seed script for local development and testing.

Creates:
- 1 Admin
- 1 Professor
- 2 Students

Repeatable: Running multiple times will not duplicate records.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure services/api is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db import async_session_factory
from app.models.enums import UserRole
from app.models.user import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")

SEED_USERS = [
    {
        "email": "admin@campus.local",
        "name": "Platform Administrator",
        "role": UserRole.ADMIN,
        "password": "AdminPassword123!",
    },
    {
        "email": "professor@campus.local",
        "name": "Prof. Homi Bhabha",
        "role": UserRole.PROFESSOR,
        "password": "ProfessorPassword123!",
    },
    {
        "email": "student1@campus.local",
        "name": "Aarav Sharma",
        "role": UserRole.STUDENT,
        "password": "StudentPassword123!",
    },
    {
        "email": "student2@campus.local",
        "name": "Diya Patel",
        "role": UserRole.STUDENT,
        "password": "StudentPassword123!",
    },
]


async def seed_users(session: AsyncSession) -> list[User]:
    """Seed users idempotently."""
    created_or_updated: list[User] = []

    for user_data in SEED_USERS:
        email = user_data["email"]
        stmt = select(User).where(func.lower(User.email) == email.lower())
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                email=email,
                name=user_data["name"],
                role=user_data["role"],
                password_hash=hash_password(user_data["password"]),
                is_active=True,
            )
            session.add(user)
            logger.info("Created user: %s (%s)", user.email, user.role.value)
        else:
            user.name = user_data["name"]
            user.role = user_data["role"]
            user.password_hash = hash_password(user_data["password"])
            user.is_active = True
            logger.info("Updated existing user: %s (%s)", user.email, user.role.value)

        created_or_updated.append(user)

    await session.commit()
    return created_or_updated


async def main() -> None:
    """Run seeding routine."""
    logger.info("Starting database seeding...")
    async with async_session_factory() as session:
        users = await seed_users(session)
        logger.info("Successfully seeded %d users.", len(users))


if __name__ == "__main__":
    asyncio.run(main())
