# -*- coding: utf-8 -*-
"""Meeting Actions — model-agnostic output contract + system prompt."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "one_line_summary": {
            "type": "string",
            "description": "TL;DR of the meeting in one sentence",
        },
        "decisions": {
            "type": "array",
            "description": "Explicit decisions made in the meeting (3–8 items max)",
            "items": {"type": "string"},
        },
        "action_items": {
            "type": "array",
            "description": "Tasks with owner and due date when stated",
            "items": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Person name or 'Unassigned'. Use transcript names only.",
                    },
                    "task": {"type": "string"},
                    "due": {
                        "type": "string",
                        "description": "Due date/time if mentioned, else 'Not specified'",
                    },
                    "source_quote": {
                        "type": "string",
                        "description": "Verbatim quote from transcript supporting this item",
                    },
                    "uncertain": {
                        "type": "boolean",
                        "description": "True if owner, task, or due is ambiguous",
                    },
                },
                "required": ["owner", "task", "due", "source_quote", "uncertain"],
            },
        },
        "open_questions": {
            "type": "array",
            "description": "Unresolved questions or follow-ups",
            "items": {"type": "string"},
        },
        "key_topics": {
            "type": "array",
            "description": "Main topics discussed (for skimming)",
            "items": {"type": "string"},
        },
        "disclaimer": {
            "type": "string",
            "description": "Not a substitute for official meeting minutes",
        },
    },
    "required": [
        "one_line_summary",
        "decisions",
        "action_items",
        "open_questions",
        "key_topics",
        "disclaimer",
    ],
}

SYSTEM_PROMPT = """You extract structured meeting notes from a transcript.
Your job is to organize what was actually said — not to invent tasks or decisions.

Rules:
1. Every action item MUST include a source_quote copied from the transcript.
2. Do not guess owners or due dates. If unclear, set uncertain=true and use "Unassigned" or "Not specified".
3. Do not add action items that were not discussed.
4. decisions[] must be explicit agreements, not vague discussion topics.
5. Write all output in English unless the transcript is clearly in another language (then match the transcript language).
6. disclaimer must state this is an AI summary and attendees should verify.

Output only valid JSON matching the schema below. No markdown fences or extra text.

JSON schema:
"""


def build_system_prompt() -> str:
    import json

    return SYSTEM_PROMPT + json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2)


REQUIRED_TOP_KEYS = OUTPUT_SCHEMA["required"]
