"""Tests for the database seeding script."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import UserRole
from app.models.user import User
from scripts.seed import SEED_USERS, seed_users


@pytest.mark.asyncio
async def test_seed_users_repeatability() -> None:
    """Verify that calling seed_users multiple times creates 4 users and does not duplicate."""
    stored_users: dict[str, User] = {}
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()

    def mock_add(user: User) -> None:
        stored_users[user.email.lower()] = user

    mock_session.add.side_effect = mock_add

    call_index = 0

    async def mock_execute(_stmt: object) -> MagicMock:
        nonlocal call_index
        email = SEED_USERS[call_index % len(SEED_USERS)]["email"].lower()
        call_index += 1
        res = MagicMock()
        res.scalar_one_or_none.return_value = stored_users.get(email)
        return res

    mock_session.execute = mock_execute

    # Pass 1: empty database -> creates 4 users
    users_pass_1 = await seed_users(mock_session)
    assert len(users_pass_1) == 4
    assert len(stored_users) == 4

    roles = [u.role for u in users_pass_1]
    assert roles.count(UserRole.ADMIN) == 1
    assert roles.count(UserRole.PROFESSOR) == 1
    assert roles.count(UserRole.STUDENT) == 2

    # Pass 2: rerun -> finds existing users, updates them, does not duplicate
    count_before = len(stored_users)
    users_pass_2 = await seed_users(mock_session)
    assert len(users_pass_2) == 4
    assert len(stored_users) == count_before
