"""daily_prompt (scheduled job) and handle_response (user reply)."""
from types import SimpleNamespace

import pytest

import main
from classes import Entry, Prompt
from conftest import reply_text


def job_context(context, user_id=1, chat_id=1):
    context.job = SimpleNamespace(data=chat_id, user_id=user_id)
    return context


async def test_sends_a_prompt_and_marks_user_as_awaiting(context, make_user, make_prompt):
    make_user(user_id="1")
    prompt = make_prompt("Only prompt")
    await main.daily_prompt(job_context(context))

    kwargs = context.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 1
    assert "Only prompt" in kwargs["text"]
    assert context.application.bot_data["awaiting_response"][1] == prompt.id


async def test_prefers_prompts_user_has_not_answered(context, make_user, make_prompt):
    user = make_user(user_id="1")
    answered, fresh = make_prompt("answered"), make_prompt("fresh")
    Entry.create(user=user, prompt_id=answered, response="done")
    for _ in range(20):  # random selection, so repeat
        await main.daily_prompt(job_context(context))
        assert context.application.bot_data["awaiting_response"][1] == fresh.id


async def test_other_users_answers_do_not_exclude_prompts(context, make_user, make_prompt):
    make_user(user_id="1", chat_id="1")
    other = make_user(user_id="2", chat_id="2")
    prompt = make_prompt("shared")
    Entry.create(user=other, prompt_id=prompt, response="x")
    await main.daily_prompt(job_context(context, user_id=1))
    assert context.application.bot_data["awaiting_response"][1] == prompt.id


async def test_falls_back_to_any_prompt_when_all_answered(context, make_user, make_prompt):
    user, prompt = make_user(user_id="1"), make_prompt("only")
    Entry.create(user=user, prompt_id=prompt, response="done")
    await main.daily_prompt(job_context(context))
    assert context.application.bot_data["awaiting_response"][1] == prompt.id
    assert "only" in context.bot.send_message.await_args.kwargs["text"]


async def test_handles_empty_prompt_table(context, make_user):
    make_user(user_id="1")
    await main.daily_prompt(job_context(context))


# ---- handle_response -------------------------------------------------------

async def test_response_without_pending_prompt_is_rejected(make_update, context, make_user):
    make_user(user_id="1")
    update = make_update("my lyrics", user_id=1)
    await main.handle_response(update, context)
    assert "don't have a prompt" in reply_text(update)
    assert Entry.select().count() == 0


async def test_response_is_saved_and_pending_state_cleared(make_update, context, make_user, make_prompt):
    make_user(user_id="1", chat_id="1")
    prompt = make_prompt()
    context.application.bot_data["awaiting_response"] = {1: prompt.id}
    update = make_update("my lyrics", user_id=1, chat_id=1)

    await main.handle_response(update, context)

    entry = Entry.get()
    assert entry.response == "my lyrics"
    assert entry.prompt_id.id == prompt.id
    assert entry.user.id == "1"
    assert 1 not in context.application.bot_data["awaiting_response"]
    assert "saved" in reply_text(update)


async def test_second_response_to_same_prompt_is_not_saved(make_update, context, make_user, make_prompt):
    make_user(user_id="1", chat_id="1")
    context.application.bot_data["awaiting_response"] = {1: make_prompt().id}
    await main.handle_response(make_update("first"), context)
    update = make_update("second")
    await main.handle_response(update, context)
    assert Entry.select().count() == 1
    assert "don't have a prompt" in reply_text(update)


async def test_pending_prompts_are_tracked_per_user(make_update, context, make_user, make_prompt):
    make_user(user_id="1", chat_id="1")
    make_user(user_id="2", chat_id="2")
    p1, p2 = make_prompt("p1"), make_prompt("p2")
    context.application.bot_data["awaiting_response"] = {1: p1.id, 2: p2.id}
    await main.handle_response(make_update("from two", user_id=2, chat_id=2), context)
    entry = Entry.get()
    assert entry.prompt_id.id == p2.id and entry.user.id == "2"
    assert context.application.bot_data["awaiting_response"] == {1: p1.id}
