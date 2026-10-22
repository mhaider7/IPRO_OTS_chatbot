"""Compatibility re-export: the fixed escalation topic list lives in retrieval/topics.py."""
from retrieval.topics import *  # noqa: F401,F403
from retrieval.topics import HUMAN_REQUEST, fixed_topic, in_support_scope, is_fixed_topic, support_issue, topic_for  # noqa: F401
