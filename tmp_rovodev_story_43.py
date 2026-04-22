"""Write story 43: 鍵がない (No Key) — corrected word IDs."""
import json

with open('pipeline/plan.json') as f: plan = json.load(f)
with open('data/vocab_state.json') as f: v = json.load(f)
words = v['words']
new_word_defs = plan['new_word_definitions']

def w(wid, surface=None, reading=None, inflection=None, is_new=False, is_new_grammar=False):
    word = words.get(wid) or new_word_defs.get(wid)
    surf = surface or word['surface']
    rd = reading or word.get('reading') or word.get('kana')
    t = {"t": surf, "r": rd, "role": "content", "word_id": wid}
    if inflection: t["inflection"] = inflection
    if is_new: t["is_new"] = True
    if is_new_grammar: t["is_new_grammar"] = True
    return t

def p(surface, gid=None):
    t = {"t": surface, "role": "particle"}
    if gid: t["grammar_id"] = gid
    return t

def aux(surface, gid):
    return {"t": surface, "role": "aux", "grammar_id": gid}

def punct(surface=""):
    return {"t": surface, "role": "punct"}

def disc(surface, gid):
    return {"t": surface, "role": "aux", "grammar_id": gid}

# Title: 鍵がありません (W00079 鍵 + が + ありません) — first appearance of G035
title_tokens = [
    w('W00079'),
    p('が', 'G002_ga_subject'),
    aux('ありません', 'G035_arimasen'),
]

# Subtitle: 部屋を探します (search the room)
subtitle_tokens = [
    w('W00075'),
    p('を', 'G005_wo_object'),
    w('W00128', is_new=True),  # first occurrence of 探します
    punct('。'),
]

sentences = []

# s0: 夜です。
sentences.append({
    "idx": 0,
    "tokens": [w('W00030'), aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "It is night."
})

# s1: 私は部屋に来ます。
sentences.append({
    "idx": 1,
    "tokens": [w('W00003'), p('は', 'G001_wa_topic'), w('W00075'), p('に', 'G004_ni_location'),
               w('W00040'), punct('。')],
    "gloss_en": "I come to the room."
})

# s2: カバンは机にあります。
sentences.append({
    "idx": 2,
    "tokens": [w('W00130', is_new=True), p('は', 'G001_wa_topic'), w('W00037'),
               p('に', 'G004_ni_location'), w('W00044'),
               punct('。')],
    "gloss_en": "My bag is on the desk."
})

# s3: でも、鍵はありません。  (first SENTENCE-level use of G035, gets is_new_grammar)
s3_tokens = [disc('でも', 'G032_demo'), punct('、'),
             w('W00079'), p('は', 'G001_wa_topic'),
             aux('ありません', 'G035_arimasen'),
             punct('。')]
s3_tokens[4]['is_new_grammar'] = True
sentences.append({
    "idx": 3,
    "tokens": s3_tokens,
    "gloss_en": "But the key is not here."
})

# s4: 私はカバンを探します。
sentences.append({
    "idx": 4,
    "tokens": [w('W00003'), p('は', 'G001_wa_topic'), w('W00130'), p('を', 'G005_wo_object'),
               w('W00128'), punct('。')],
    "gloss_en": "I search the bag."
})

# s5: カバンに鍵はありません。
sentences.append({
    "idx": 5,
    "tokens": [w('W00130'), p('に', 'G004_ni_location'),
               w('W00079'), p('は', 'G001_wa_topic'),
               aux('ありません', 'G035_arimasen'),
               punct('。')],
    "gloss_en": "The key is not in the bag."
})

# s6: 私は椅子と机を見ます。
sentences.append({
    "idx": 6,
    "tokens": [w('W00003'), p('は', 'G001_wa_topic'),
               w('W00036'), p('と', 'G010_to_and'),
               w('W00037'), p('を', 'G005_wo_object'),
               w('W00006'), punct('。')],
    "gloss_en": "I look at the chair and the desk."
})

# s7: 私は困ります。
sentences.append({
    "idx": 7,
    "tokens": [w('W00003'), p('は', 'G001_wa_topic'),
               w('W00129', is_new=True), punct('。')],
    "gloss_en": "I am troubled."
})

# s8: 部屋は静かです。
sentences.append({
    "idx": 8,
    "tokens": [w('W00075'), p('は', 'G001_wa_topic'),
               w('W00011'),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "The room is quiet."
})

# s9: そして、私は思います。
sentences.append({
    "idx": 9,
    "tokens": [disc('そして', 'G012_soshite_then'), punct('、'),
               w('W00003'), p('は', 'G001_wa_topic'),
               w('W00043'), punct('。')],
    "gloss_en": "And then, I think."
})

# s10: 鍵は本のそばにあります。
sentences.append({
    "idx": 10,
    "tokens": [w('W00079'), p('は', 'G001_wa_topic'),
               w('W00033'), p('の', 'G015_no_possessive'),
               w('W00045'), p('に', 'G004_ni_location'),
               w('W00044'),
               punct('。')],
    "gloss_en": "The key is beside the book."
})

# s11: 私は嬉しいです。
sentences.append({
    "idx": 11,
    "tokens": [w('W00003'), p('は', 'G001_wa_topic'),
               w('W00056', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "I am happy."
})

# s12: 静かな夜、小さい鍵です。
sentences.append({
    "idx": 12,
    "tokens": [w('W00011', surface='静かな', inflection={"form":"attributive","grammar_id":"G023_attributive"}),
               w('W00030'), punct('、'),
               w('W00055', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               w('W00079'), aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "A quiet night, a small key."
})

seen = []
def collect(tokens):
    for t in tokens:
        wid = t.get('word_id')
        if wid and wid not in seen:
            seen.append(wid)
collect(title_tokens)
collect(subtitle_tokens)
for s in sentences:
    collect(s['tokens'])

story = {
    "_id": "story_43",
    "story_id": 43,
    "title": {"jp": "鍵がありません", "en": "There Is No Key", "tokens": title_tokens},
    "subtitle": {"jp": "部屋を探します。", "en": "I search the room.", "tokens": subtitle_tokens},
    "new_words": ["W00128", "W00129", "W00130"],
    "new_grammar": ["G035_arimasen"],
    "all_words_used": seen,
    "sentences": sentences
}

with open('pipeline/story_raw.json', 'w') as f:
    json.dump(story, f, ensure_ascii=False, indent=2)
print(f"Story written. Sentences: {len(sentences)}")
print(f"all_words_used: {seen}")
