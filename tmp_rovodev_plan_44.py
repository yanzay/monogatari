"""Patch plan.json for story 44."""
import json

with open('pipeline/plan.json') as f: p = json.load(f)

p['theme'] = "narrator no longer waits — friend comes by unexpectedly, the rhythm of waiting is broken"
p['setting'] = "a small room with a window, late afternoon"

# Clean meanings (no semicolons)
for wid in ['W00131', 'W00132', 'W00133']:
    nw = p['new_word_definitions'][wid]
    if wid == 'W00131':
        nw['meanings'] = ['sometimes']
        nw['pos'] = 'adverb'  # is treated as adverb
    elif wid == 'W00132':
        nw['meanings'] = ['promise']
    elif wid == 'W00133':
        nw['meanings'] = ['immediately']
        nw['pos'] = 'adverb'

p['constraints'] = {
    "must_reuse_words": ["W00041", "W00022", "W00004", "W00081"],  # 待ちます, 友達, 窓, 電話
    "guidance": [
        "use 〜ません at least 2 times — it is the introduction of G036",
        "DO NOT use ありません here — keep G035 reinforcement to one or two careful uses",
        "13 sentences target",
        "closer should reflect the broken pattern, not just repeat the friend's arrival"
    ]
}

# Update grammar definition
p['new_grammar'] = ["G036_masen"]
del p['new_grammar_definitions']['G036_<slug>']
p['new_grammar_definitions']['G036_masen'] = {
    "id": "G036_masen",
    "title": "〜ません — polite present negative (verbs)",
    "short": "Polite negative form of verbs: 〜ます becomes 〜ません.",
    "long": "Replace the polite verb ending 〜ます with 〜ません to negate. 待ちます→待ちません ('do not wait'). 来ます→来ません ('do not come'). The negation applies to the polite present and habitual senses; for past negative use 〜ませんでした (not yet introduced). This is the verb-side complement to G035 ありません — together they let the library deny both events and existences.",
    "genki_ref": "L3",
    "jlpt": "N5",
    "catalog_id": "N5_masen",
    "prerequisites": ["G026_masu_nonpast", "G003_desu"],
    "examples": [
        {"jp": "私は待ちません。", "en": "I do not wait."},
        {"jp": "友達は来ません。", "en": "The friend does not come."}
    ]
}

with open('pipeline/plan.json', 'w') as f:
    json.dump(p, f, ensure_ascii=False, indent=2)
print("plan.json patched for story 44")
