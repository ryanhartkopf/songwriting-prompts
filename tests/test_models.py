import pytest
from peewee import IntegrityError

from classes import Entry, Prompt, User


def test_user_roundtrip(make_user):
    make_user(user_id="42", chat_id="99")
    user = User.get_by_id("42")
    assert user.chat_id == "99"
    assert user.time_zone == "America/New_York"


def test_chat_id_must_be_unique(make_user):
    make_user(user_id="1", chat_id="100")
    with pytest.raises(IntegrityError):
        make_user(user_id="2", chat_id="100")


def test_user_id_must_be_unique(make_user):
    make_user(user_id="1", chat_id="100")
    with pytest.raises(IntegrityError):
        make_user(user_id="1", chat_id="200")


def test_prompt_reviewed_defaults_to_false():
    assert Prompt.create(text="x").reviewed is False


def test_prompt_user_is_optional():
    assert Prompt.create(text="x").user is None


def test_entry_has_timestamp_and_relations(make_user, make_prompt):
    user, prompt = make_user(), make_prompt()
    entry = Entry.create(user=user, prompt_id=prompt, response="la la")
    entry = Entry.get_by_id(entry.id)
    assert entry.timestamp is not None
    assert entry.prompt_id.id == prompt.id
    assert entry.user.id == user.id


def test_backrefs(make_user, make_prompt):
    user, prompt = make_user(), make_prompt()
    Entry.create(user=user, prompt_id=prompt, response="a")
    Entry.create(user=user, prompt_id=prompt, response="b")
    assert user.entries.count() == 2
    assert prompt.entries.count() == 2
