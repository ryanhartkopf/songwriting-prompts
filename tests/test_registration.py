"""The /start conversation: name -> email -> time zone -> time."""
from unittest.mock import MagicMock

import pytest
from conftest import reply_text
from telegram.ext import ConversationHandler

import main
from classes import User


async def test_start_asks_for_name(make_update, context):
    update = make_update()
    assert await main.start(update, context) == main.NAME
    assert "name" in reply_text(update).lower()


async def test_get_name_stores_name(make_update, context):
    update = make_update("Ada")
    assert await main.get_name(update, context) == main.EMAIL
    assert context.user_data["name"] == "Ada"
    assert "Ada" in reply_text(update)


async def test_get_email_stores_email(make_update, context):
    update = make_update("ada@example.com")
    assert await main.get_email(update, context) == main.TZ
    assert context.user_data["email"] == "ada@example.com"


@pytest.mark.parametrize("choice,zone", [
    ("1", "America/Los_Angeles"),
    ("2", "America/Denver"),
    ("3", "America/Chicago"),
    ("4", "America/New_York"),
])
async def test_get_timezone_valid_choices(make_update, context, choice, zone):
    update = make_update(choice)
    assert await main.get_timezone(update, context) == main.TIME
    assert context.user_data["time_zone"] == zone


@pytest.mark.parametrize("choice", ["0", "5", "", "four", "America/Denver", " 1"])
async def test_get_timezone_invalid_choice_reprompts(make_update, context, choice):
    update = make_update(choice)
    assert await main.get_timezone(update, context) == main.TZ
    assert "time_zone" not in context.user_data
    assert "Invalid" in reply_text(update)


def filled_context(context, **overrides):
    context.user_data.update(name="Ada", email="ada@example.com",
                             time_zone="America/Chicago", **overrides)
    return context


async def test_get_time_creates_user(make_update, context):
    update = make_update("07:30", user_id=5, chat_id=50)
    result = await main.get_time(update, filled_context(context))

    assert result == ConversationHandler.END
    user = User.get_by_id("5")
    assert (user.chat_id, user.name, user.email) == ("50", "Ada", "ada@example.com")
    assert (user.time_zone, user.message_time) == ("America/Chicago", "07:30")
    assert "07:30" in reply_text(update)


async def test_get_time_schedules_daily_job(make_update, context):
    update = make_update("07:30", user_id=5, chat_id=50)
    await main.get_time(update, filled_context(context))

    kwargs = context.application.job_queue.run_daily.call_args.kwargs
    assert kwargs["callback"] is main.daily_prompt
    assert kwargs["name"] == "daily_job_50"
    assert kwargs["user_id"] == 5 and kwargs["chat_id"] == 50 and kwargs["data"] == 50
    assert tuple(kwargs["days"]) == (0, 1, 2, 3, 4, 5, 6)
    t = kwargs["time"]
    assert (t.hour, t.minute, t.second) == (7, 30, 0)
    assert str(t.tzinfo) == "America/Chicago"


async def test_get_time_updates_existing_user_and_replaces_job(make_update, context, make_user):
    make_user(user_id="5", chat_id="50", name="Old", message_time="08:00",
              time_zone="America/Denver")
    old_job = MagicMock()
    context.application.job_queue.get_jobs_by_name.return_value = [old_job]

    update = make_update("21:15", user_id=5, chat_id=50)
    await main.get_time(update, filled_context(context))

    assert User.select().count() == 1
    user = User.get_by_id("5")
    assert (user.name, user.message_time, user.time_zone) == ("Ada", "21:15", "America/Chicago")
    old_job.schedule_removal.assert_called_once()
    context.application.job_queue.get_jobs_by_name.assert_called_with("daily_job_50")
    context.application.job_queue.run_daily.assert_called_once()


async def test_get_time_without_existing_job_does_not_fail(make_update, context):
    context.application.job_queue.get_jobs_by_name.return_value = []
    await main.get_time(make_update("09:00"), filled_context(context))
    context.application.job_queue.run_daily.assert_called_once()


async def test_get_time_integrity_error_ends_conversation(make_update, context, make_user):
    # Same Telegram user id, but registered under a different chat -> PK collision.
    make_user(user_id="5", chat_id="999")
    update = make_update("09:00", user_id=5, chat_id=50)

    result = await main.get_time(update, filled_context(context))

    assert result == ConversationHandler.END
    assert "error saving" in reply_text(update)
    context.application.job_queue.run_daily.assert_not_called()


@pytest.mark.parametrize("bad", ["9am", "noon", "25:00", "12:60", ""])
async def test_get_time_rejects_invalid_time(make_update, context, bad):
    update = make_update(bad)
    result = await main.get_time(update, filled_context(context))
    assert result == main.TIME  # desired: re-prompt instead of crashing
