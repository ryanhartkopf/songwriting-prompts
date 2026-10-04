import json
from pathlib import Path

import pytest

PROMPTS_FILE = Path(__file__).resolve().parent.parent / "prompts.json"


@pytest.fixture(scope="module")
def prompts():
    return json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))


def test_is_non_empty_list(prompts):
    assert isinstance(prompts, list) and prompts


def test_all_entries_are_non_blank_strings(prompts):
    assert all(isinstance(p, str) and p.strip() for p in prompts)


def test_no_duplicates(prompts):
    assert len(prompts) == len(set(prompts))


def test_no_leading_or_trailing_whitespace(prompts):
    assert [p for p in prompts if p != p.strip()] == []


def test_prompts_fit_in_a_telegram_message(prompts):
    # Telegram's limit is 4096 chars; the bot adds a short prefix.
    assert max(len(p) for p in prompts) < 4000
