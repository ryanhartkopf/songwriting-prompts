"""Simple command handlers: /help, /list, /cancel."""
from conftest import reply_text

import main
from classes import Entry


async def test_help_lists_commands(make_update, context):
    update = make_update()
    await main.help(update, context)
    text = reply_text(update)
    for cmd in ("/start", "/list", "/email", "/help"):
        assert cmd in text


async def test_cancel_ends_conversation(make_update, context):
    from telegram.ext import ConversationHandler
    update = make_update()
    assert await main.cancel(update, context) == ConversationHandler.END
    assert "canceled" in reply_text(update)


async def test_list_with_no_entries(make_update, context, make_user):
    make_user(user_id="1")
    update = make_update(user_id=1)
    await main.list(update, context)
    assert reply_text(update) == "You have no responses yet."


async def test_list_shows_prompt_and_response(make_update, context, make_user, make_prompt):
    user, prompt = make_user(user_id="1"), make_prompt("Write about rain.")
    Entry.create(user=user, prompt_id=prompt, response="It fell.")
    update = make_update(user_id=1)
    await main.list(update, context)
    text = reply_text(update)
    assert "Prompt: Write about rain." in text
    assert "Response: It fell." in text


async def test_list_returns_only_last_five_newest_first(make_update, context, make_user, make_prompt):
    user, prompt = make_user(user_id="1"), make_prompt()
    for i in range(7):
        Entry.create(user=user, prompt_id=prompt, response=f"resp-{i}")
    update = make_update(user_id=1)
    await main.list(update, context)
    text = reply_text(update)
    assert "resp-6" in text and "resp-2" in text
    assert "resp-1" not in text and "resp-0" not in text
    assert text.index("resp-6") < text.index("resp-2")


async def test_list_excludes_other_users(make_update, context, make_user, make_prompt):
    me, other = make_user(user_id="1", chat_id="1"), make_user(user_id="2", chat_id="2")
    prompt = make_prompt()
    Entry.create(user=me, prompt_id=prompt, response="mine")
    Entry.create(user=other, prompt_id=prompt, response="theirs")
    update = make_update(user_id=1)
    await main.list(update, context)
    text = reply_text(update)
    assert "mine" in text and "theirs" not in text


async def test_prompt_marks_user_as_awaiting(make_update, context, make_user, make_prompt):
    user, prompt = make_user(user_id="1"), make_prompt("Write about rain.")
    update = make_update(user_id=1)
    await main.prompt(update, context)
    text = reply_text(update)
    assert "Write about rain." in text


async def test_prompt_marks_user_as_awaiting(make_update, context, make_user, make_prompt):
    user, prompt = make_user(user_id="1"), make_prompt("Write about rain.")
    update = make_update(user_id=1)
    await main.prompt(update, context)
    assert context.application.bot_data["awaiting_response"][1] == prompt.id


async def test_prompt_prefers_prompts_user_has_not_answered(make_update, context, make_user, make_prompt):
    user = make_user(user_id="1")
    answered, fresh = make_prompt("answered"), make_prompt("fresh")
    Entry.create(user=user, prompt_id=answered, response="done")
    update = make_update(user_id=1)
    for _ in range(20):  # random selection, so repeat
        await main.prompt(update, context)
        assert context.application.bot_data["awaiting_response"][1] == fresh.id


async def test_prompt_handles_empty_prompt_table(make_update, context, make_user):
    make_user(user_id="1")
    update = make_update(user_id=1)
    await main.prompt(update, context)
    text = reply_text(update)
    assert "try again later." in text
