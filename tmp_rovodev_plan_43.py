"""Patch plan.json for story 43 with grammar definition + theme."""
import json

with open('pipeline/plan.json') as f:
    p = json.load(f)

p['theme'] = "no key — narrator can't find their house key, gentle frustration that turns to acceptance"
p['setting'] = "a small room, evening, after coming home"
p['constraints'] = {
    "must_reuse_words": ["W00079", "W00075", "W00037", "W00036", "W00033"],
    "guidance": [
        "use ありません at least 2 times — it is the introduction of G035",
        "do NOT use any other negation forms (those come later in the arc)",
        "13 sentences target",
        "closer should land the emotional shift, not just summarise the search"
    ]
}

# Convert verb new words from 探す → 探します (polite form is the library standard)
p['new_word_definitions']['W00128'] = {
    "id": "W00128",
    "first_story": 43,
    "grammar_tags": ["G026_masu_nonpast"],
    "surface": "探します",
    "kana": "さがします",
    "reading": "sagashimasu",
    "pos": "verb",
    "verb_class": "godan_su",
    "adj_class": None,
    "meanings": ["to search for; to look for"],
    "base": "探す"
}
p['new_word_definitions']['W00129'] = {
    "id": "W00129",
    "first_story": 43,
    "grammar_tags": ["G026_masu_nonpast"],
    "surface": "困ります",
    "kana": "こまります",
    "reading": "komarimasu",
    "pos": "verb",
    "verb_class": "godan_ru",
    "adj_class": None,
    "meanings": ["to be troubled; to be at a loss"],
    "base": "困る"
}
# W00130 is カバン noun - confirm it's correct
p['new_word_definitions']['W00130'] = {
    "id": "W00130",
    "first_story": 43,
    "grammar_tags": [],
    "surface": "カバン",
    "kana": "かばん",
    "reading": "kaban",
    "pos": "noun",
    "verb_class": None,
    "adj_class": None,
    "meanings": ["bag; satchel"]
}

# Update grammar definition
p['new_grammar'] = ["G035_arimasen"]
del p['new_grammar_definitions']['G035_<slug>']
p['new_grammar_definitions']['G035_arimasen'] = {
    "id": "G035_arimasen",
    "title": "ありません — negative existence (inanimate)",
    "short": "Negative form of あります for inanimate things: 'there is not / does not exist'.",
    "long": "ありません is the polite negative of あります and expresses the non-existence of inanimate things. The thing being denied takes は (topic), not が. Example: 鍵はありません (there is no key — about the key). For animate beings (people, animals) the equivalent is いません, the negative of います. This is the library's first introduction of any negation form.",
    "genki_ref": "L4",
    "jlpt": "N5",
    "catalog_id": "N5_ko_arimasen",
    "prerequisites": ["G021_aru_iru", "G003_desu"],
    "examples": [
        {"jp": "鍵はありません。", "en": "There is no key."},
        {"jp": "お茶はありません。", "en": "There is no tea."}
    ]
}

with open('pipeline/plan.json', 'w') as f:
    json.dump(p, f, ensure_ascii=False, indent=2)
print("plan.json patched for story 43")
