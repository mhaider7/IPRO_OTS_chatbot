import pytest

from retrieval.topics import in_support_scope, is_fixed_topic


@pytest.mark.parametrize("history", [
    ["What is the status of my ticket?"],
    ["Any update on my ticket? Is it resolved?"],
    ["I was charged twice for printing"],
    ["I want to dispute the printing fee on my account"],
    ["Why is there a hold on my account?"],
    ["My account was suspended"],
    ["Can you check my equipment loan history?"],
    ["I reset my password", "It still won't let me in"],
    ["I set up Okta Verify", "I lost my phone and no longer have the device"],
    ["Duo keeps asking for a code", "My phone is broken"],
])
def test_fixed_topics_flagged_before_search(history):
    assert is_fixed_topic(history[-1], history)


@pytest.mark.parametrize("text", [
    "How do I connect to the campus Wi-Fi?",
    "How do I reset my password?",
    "How do I set up Okta Verify?",
    "How do I print from the VCL?",
])
def test_self_service_questions_not_flagged(text):
    assert not is_fixed_topic(text, [text])


def test_topic_change_does_not_inherit_lockout():
    history = ["I reset my password", "It still won't let me in", "How's the weather today?"]
    assert not in_support_scope(history[-1], history)
