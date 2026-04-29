"""Class E: JSON schema compliance.

Validates every state file and story against a formal jsonschema.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


VOCAB_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["next_word_id", "words"],
    "properties": {
        "next_word_id": {"type": "string", "pattern": "^W\\d{5}$"},
        "words": {
            "type": "object",
            "patternProperties": {
                "^W\\d{5}$": {
                    "type": "object",
                    "required": ["id", "surface", "kana", "pos", "meanings", "occurrences", "first_story"],
                    "properties": {
                        "id":           {"type": "string", "pattern": "^W\\d{5}$"},
                        "surface":      {"type": "string", "minLength": 1},
                        "kana":         {"type": "string", "minLength": 1},
                        "reading":      {"type": "string"},
                        "pos":          {"type": "string"},
                        "verb_class":   {"type": "string"},
                        "meanings":     {"type": "array", "items": {"type": "string"}, "minItems": 1},
                        "occurrences":  {"type": "integer", "minimum": 0},
                        "first_story":  {"type": "string", "pattern": "^story_\\d+$"},
                        "notes":        {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": False,
        },
    },
}


GRAMMAR_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["points"],
    "properties": {
        "points": {
            "type": "object",
            "patternProperties": {
                "^G\\d{3}_": {
                    "type": "object",
                    "required": ["id", "title", "short", "long", "jlpt", "prerequisites"],
                    "properties": {
                        "id":             {"type": "string", "pattern": "^G\\d{3}_"},
                        "catalog_id":     {"type": "string"},
                        "title":          {"type": "string", "minLength": 1},
                        "short":          {"type": "string", "minLength": 1},
                        "long":           {"type": "string", "minLength": 1},
                        "examples":       {"type": "array", "items": {"type": "string"}},
                        "jlpt":           {"type": "string", "enum": ["N5", "N4", "N3", "N2", "N1"]},
                        "genki_ref":      {"type": "string"},
                        "bunpro_ref":     {"type": "string"},
                        "jlpt_sensei_ref":{"type": "string"},
                        "prerequisites":  {"type": "array", "items": {"type": "string"}},
                        "first_story":    {"type": ["string", "null"]},
                        "notes":          {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": False,
        },
    },
}


STORY_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["title", "sentences", "all_words_used", "new_words", "new_grammar"],
    "properties": {
        "id":               {"type": "string", "pattern": "^story_\\d+$"},
        "title":            {"type": "object"},
        "sentences":        {"type": "array"},
        "all_words_used":   {"type": "array", "items": {"type": "string", "pattern": "^W\\d{5}$"}},
        "new_words":        {"type": "array"},
        "new_grammar":      {"type": "array"},
    },
    "additionalProperties": True,
}


TOKEN_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["t", "role"],
    "properties": {
        "t":          {"type": "string", "minLength": 1},
        "r":          {"type": "string"},
        "role":       {"type": "string", "enum": ["content", "particle", "aux", "punct"]},
        "word_id":    {"type": "string", "pattern": "^W\\d{5}$"},
        "grammar_id": {"type": "string", "pattern": "^G\\d{3}_"},
        "is_new":          {"type": "boolean"},
        "is_new_grammar":  {"type": "boolean"},
        "inflection": {
            "type": "object",
            "properties": {
                "base":       {"type": "string"},
                "base_r":     {"type": "string"},
                "form":       {"type": "string"},
                "verb_class": {"type": "string"},
                "word_id":    {"type": "string", "pattern": "^W\\d{5}$"},
                "grammar_id": {"type": "string", "pattern": "^G\\d{3}_"},
            },
            "additionalProperties": True,
        },
    },
    "additionalProperties": True,
}


def test_vocab_schema(vocab):
    Draft202012Validator(VOCAB_SCHEMA).validate(vocab)


def test_grammar_schema(grammar):
    Draft202012Validator(GRAMMAR_SCHEMA).validate(grammar)


def test_story_schema(stories):
    validator = Draft202012Validator(STORY_SCHEMA)
    errors = []
    for story in stories:
        for err in validator.iter_errors({k: v for k, v in story.items() if not k.startswith("_")}):
            errors.append(f"{story['_id']}: {err.message}")
    assert not errors, "Story schema errors:\n  " + "\n  ".join(errors)


def test_token_schema(stories):
    """Every token must conform to TOKEN_SCHEMA."""
    validator = Draft202012Validator(TOKEN_SCHEMA)
    errors = []
    for story in stories:
        for sec_name in ("title",):
            sec = story.get(sec_name) or {}
            for j, tok in enumerate(sec.get("tokens", [])):
                for err in validator.iter_errors(tok):
                    errors.append(f"{story['_id']} {sec_name}[{j}]: {err.message}")
        for i, sent in enumerate(story.get("sentences", [])):
            for j, tok in enumerate(sent.get("tokens", [])):
                for err in validator.iter_errors(tok):
                    errors.append(f"{story['_id']} sentence[{i}][{j}]: {err.message}")
    assert not errors, "Token schema errors:\n  " + "\n  ".join(errors[:20])
