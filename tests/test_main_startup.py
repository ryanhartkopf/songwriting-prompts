"""main(): prompt seeding, job scheduling and handler registration."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from telegram.ext import CommandHandler, ConversationHandler, MessageHandler

import main
from classes import Prompt

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def app(monkeypatch):
    """Run main() against a mocked Application and the in-memory DB."""
    monkeypatch.chdir(ROOT)  # main() opens prompts.json relative to cwd
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:abc")
    fake_db = MagicMock()
    monkeypatch.setattr(main, "db", fake_db)  # tables already exist in test_db
    application = MagicMock()
    monkeypatch.setattr(main, "Application", MagicMock(builder=lambda: builder_mock(application)))
    return application


def builder_mock(application):
    b = MagicMock()
    b.token.return_value.build.return_value = application
    return b


def test_loads_prompts_into_db(app):
    import json
    expected = json.loads((ROOT / "prompts.json").read_text())
    main.main()
    assert Prompt.select().count() == len(expected)
    assert all(p.reviewed for p in Prompt.select())
    app.run_polling.assert_called_once()


def test_prompt_seeding_is_idempotent(app):
    main.main()
    first = Prompt.select().count()
    main.main()
    assert Prompt.select().count() == first


def test_schedules_job_for_each_registered_user(app, make_user):
    make_user(user_id="1", chat_id="10", message_time="06:05", time_zone="America/Denver")
    make_user(user_id="2", chat_id="20", message_time="22:45", time_zone="America/New_York")
    main.main()

    calls = {c.kwargs["name"]: c.kwargs for c in app.job_queue.run_daily.call_args_list}
    assert set(calls) == {"daily_job_10", "daily_job_20"}
    assert (calls["daily_job_10"]["time"].hour, calls["daily_job_10"]["time"].minute) == (6, 5)
    assert calls["daily_job_10"]["user_id"] == 1
    assert calls["daily_job_20"]["chat_id"] == 20


def test_no_jobs_without_users(app):
    main.main()
    app.job_queue.run_daily.assert_not_called()


def test_registers_expected_handlers(app):
    main.main()
    handlers = app.add_handlers.call_args.args[0]
    commands = {c for h in handlers if isinstance(h, CommandHandler) for c in h.commands}
    assert commands == {"help", "list", "email"}
    assert any(isinstance(h, ConversationHandler) for h in handlers)
    assert any(isinstance(h, MessageHandler) for h in handlers)
