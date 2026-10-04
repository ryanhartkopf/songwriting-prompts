"""The /email command."""
import smtplib
from unittest.mock import MagicMock, patch

import pytest

import main
from classes import Entry
from conftest import reply_text


@pytest.fixture(autouse=True)
def smtp_env(monkeypatch):
    monkeypatch.setenv("SMTP_SERVER", "smtp.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "bot@test")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")


@pytest.fixture
def smtp():
    """Patch smtplib.SMTP; yields (class_mock, connection_mock)."""
    with patch("main.smtplib.SMTP") as cls:
        conn = cls.return_value.__enter__.return_value
        yield cls, conn


async def test_unregistered_user_is_told_to_register(make_update, context, smtp):
    update = make_update(user_id=1, chat_id=1)
    await main.email(update, context)
    assert "/start" in reply_text(update)
    smtp[0].assert_not_called()


async def test_sends_email_with_all_responses(make_update, context, make_user, make_prompt, smtp):
    user = make_user(user_id="1", chat_id="1", email="ada@example.com")
    prompt = make_prompt("Write about rain.")
    for i in range(7):  # more than /list's limit of 5
        Entry.create(user=user, prompt_id=prompt, response=f"resp-{i}")
    update = make_update(user_id=1, chat_id=1)

    await main.email(update, context)

    cls, conn = smtp
    cls.assert_called_once_with("smtp.test", 587)
    conn.starttls.assert_called_once()
    conn.login.assert_called_once_with("bot@test", "secret")
    msg = conn.send_message.call_args.args[0]
    assert msg["To"] == "ada@example.com"
    assert msg["From"] == "bot@test"
    assert msg["Subject"] == "Your Songwriting Responses"
    body = msg.get_content()
    assert all(f"resp-{i}" in body for i in range(7))
    assert body.index("resp-6") < body.index("resp-0")  # newest first
    assert "successfully" in reply_text(update)


async def test_email_with_no_responses(make_update, context, make_user, smtp):
    make_user(user_id="1", chat_id="1")
    await main.email(make_update(user_id=1, chat_id=1), context)
    assert "no responses yet" in smtp[1].send_message.call_args.args[0].get_content()


async def test_sender_refused_reports_failure(make_update, context, make_user, smtp):
    make_user(user_id="1", chat_id="1")
    smtp[1].send_message.side_effect = smtplib.SMTPSenderRefused(550, b"nope", "bot@test")
    update = make_update(user_id=1, chat_id=1)

    await main.email(update, context)

    assert "Failed" in reply_text(update)
    assert update.message.reply_text.await_count == 1


@pytest.mark.xfail(reason="Only SMTPSenderRefused is handled; auth/connection errors propagate",
                   raises=smtplib.SMTPAuthenticationError, strict=True)
async def test_auth_failure_is_handled(make_update, context, make_user, smtp):
    make_user(user_id="1", chat_id="1")
    smtp[1].login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad creds")
    update = make_update(user_id=1, chat_id=1)
    await main.email(update, context)
    assert "Failed" in reply_text(update)
