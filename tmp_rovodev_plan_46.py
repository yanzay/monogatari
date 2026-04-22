"""Patch plan.json for story 46."""
import json

with open('pipeline/plan.json') as f: p = json.load(f)

p['theme'] = "spring is finally winning out — the morning is no longer cold, light fills the air"
p['setting'] = "by an open window, early morning, late spring"

# Clean meanings
p['new_word_definitions']['W00137']['meanings'] = ['bright']
p['new_word_definitions']['W00138']['meanings'] = ['air']
p['new_word_definitions']['W00139']['meanings'] = ['light']
# Set adj_class for 明るい (i-adj)
p['new_word_definitions']['W00137']['adj_class'] = 'i'

p['constraints'] = {
    "must_reuse_words": ["W00062", "W00015", "W00072", "W00012", "W00047", "W00024"],
    "guidance": [
        "use 〜くない (i-adj negative) at least 2 times — it is the introduction of G038",
        "DO NOT use other negation forms (ありません/〜ません) more than once each",
        "13 sentences target",
        "the closer should land warmth — the negation is the door, not the destination"
    ]
}

p['new_grammar'] = ["G038_kunai"]
del p['new_grammar_definitions']['G038_<slug>']
p['new_grammar_definitions']['G038_kunai'] = {
    "id": "G038_kunai",
    "title": "〜くない — i-adjective negative",
    "short": "Replace the final い of an i-adjective with くない to negate.",
    "long": "い-adjectives negate by replacing the final い with くない: 寒い→寒くない (not cold), 大きい→大きくない (not big). Add です to keep polite register: 寒くないです. The polite alternative 寒くありません is also valid (ありません = polite negative of あります), but 〜くないです is more conversational and is what we introduce here. Note that いい is irregular: いい→よくない. The library has carefully avoided introducing this form until now because it requires both i-adj familiarity (G022) and a comfortable handling of negation (G035, G036) — both now in place.",
    "genki_ref": "L5",
    "jlpt": "N5",
    "catalog_id": "N5_i_adj_neg",
    "prerequisites": ["G022_i_adj", "G003_desu"],
    "examples": [
        {"jp": "朝は寒くないです。", "en": "The morning is not cold."},
        {"jp": "部屋は大きくないです。", "en": "The room is not big."}
    ]
}

with open('pipeline/plan.json', 'w') as f:
    json.dump(p, f, ensure_ascii=False, indent=2)
print("plan.json patched for story 46")
