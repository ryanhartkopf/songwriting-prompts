"""Simple command handlers: /help, /list, /cancel."""
import main
from classes import Entry
from conftest import reply_text


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
