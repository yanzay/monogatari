"""Patch plan.json for story 45."""
import json

with open('pipeline/plan.json') as f: p = json.load(f)

p['theme'] = "at grandmother's house, narrator finds an old box and asks what it is"
p['setting'] = "grandmother's quiet room, late afternoon, dust and warm light"

# Clean meanings
for wid, m in [('W00134','this'),('W00135','what'),('W00136','box')]:
    p['new_word_definitions'][wid]['meanings'] = [m]

p['constraints'] = {
    "must_reuse_words": ["W00098", "W00067", "W00075", "W00033"],  # 祖母, 古い, 部屋, 本
    "guidance": [
        "use か (sentence-final question) at least 2 times — it is the introduction of G037",
        "DO NOT use other question grammars (どこ, 誰, etc) — those come later",
        "13 sentences target",
        "the question shape is the new texture — embrace it, but stay quiet"
    ]
}

p['new_grammar'] = ["G037_ka_question"]
del p['new_grammar_definitions']['G037_<slug>']
p['new_grammar_definitions']['G037_ka_question'] = {
    "id": "G037_ka_question",
    "title": "か — sentence-final question marker",
    "short": "Adding か at the end of a sentence makes it a yes/no or wh-question.",
    "long": "Adding か to the end of any polite sentence turns it into a question. With a question word like 何 or どこ it is a wh-question (これは何ですか — what is this?); without one it is a yes/no question (元気ですか — are you well?). Spoken Japanese often drops か with rising intonation, but the written register keeps it. The question mark ? is unnecessary and considered Western — か is the punctuation. The library has shipped one untagged か (story 32 s7) which this introduction retroactively governs.",
    "genki_ref": "L1",
    "jlpt": "N5",
    "catalog_id": "N5_ka_question",
    "prerequisites": ["G003_desu"],
    "examples": [
        {"jp": "これは何ですか。", "en": "What is this?"},
        {"jp": "元気ですか。", "en": "Are you well?"}
    ]
}

with open('pipeline/plan.json', 'w') as f:
    json.dump(p, f, ensure_ascii=False, indent=2)
print("plan.json patched for story 45")
