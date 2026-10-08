"""Shared fixtures: an in-memory database plus fake Telegram objects."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from peewee import SqliteDatabase

from classes import DailyPrompt, Entry, Prompt, User

MODELS = [User, Prompt, Entry, DailyPrompt]


@pytest.fixture(autouse=True)
def test_db():
    """Bind all models to a fresh in-memory SQLite DB for every test."""
    database = SqliteDatabase(":memory:")
    with database.bind_ctx(MODELS):
        database.connect()
        database.create_tables(MODELS)
        yield database
        database.close()


@pytest.fixture
def make_user():
    def _make(user_id="1", chat_id="1", name="Ada", email="ada@example.com",
              message_time="09:00", time_zone="America/New_York"):
        return User.create(id=user_id, chat_id=chat_id, name=name, email=email,
                           message_time=message_time, time_zone=time_zone)
    return _make


@pytest.fixture
def make_prompt():
    def _make(text="Write a line about rain."):
        return Prompt.create(text=text, reviewed=True)
    return _make


@pytest.fixture
def make_update():
    """Build a fake telegram Update whose message.reply_text is an AsyncMock."""
    def _make(text="hi", user_id=1, chat_id=1, first_name="Ada"):
        update = MagicMock()
        update.message.text = text
        update.message.reply_text = AsyncMock()
        update.effective_user.id = user_id
        update.effective_user.first_name = first_name
        update.effective_chat.id = chat_id
        return update
    return _make


@pytest.fixture
def context():
    """Fake CallbackContext with real dicts for user_data / bot_data."""
    ctx = MagicMock()
    ctx.user_data = {}
    ctx.application.bot_data = {}
    ctx.application.job_queue.get_jobs_by_name.return_value = []
    ctx.bot.send_message = AsyncMock()
    return ctx


def reply_text(update):
    """Text of the most recent reply sent through update.message.reply_text."""
    return update.message.reply_text.await_args.args[0]
