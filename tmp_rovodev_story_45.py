"""Write story 45: これは何ですか (What Is This?)."""
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

# Title: これは何ですか (W00134 これ + は + W00135 何 + です + か)
# Mark first か as is_new_grammar
title_tokens = [
    w('W00134'),
    p('は', 'G001_wa_topic'),
    w('W00135'),
    aux('です', 'G003_desu'),
    {"t":"か","role":"particle","grammar_id":"G037_ka_question"},
]

# Subtitle: 祖母の古い箱 (Grandmother's old box)
subtitle_tokens = [
    w('W00098'),
    p('の', 'G015_no_possessive'),
    w('W00067', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
    w('W00136'),
]

sentences = []

# s0: 祖母の部屋は静かです。
sentences.append({
    "idx": 0,
    "tokens": [w('W00098'), p('の', 'G015_no_possessive'), w('W00075'),
               p('は', 'G001_wa_topic'), w('W00011'),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "Grandmother's room is quiet."
})

# s1: 私は古い箱を見ます。
sentences.append({
    "idx": 1,
    "tokens": [w('W00003'), p('は', 'G001_wa_topic'),
               w('W00067', inflection={"form":"attributive","grammar_id":"G023_attributive"}),
               w('W00136', is_new=True),
               p('を', 'G005_wo_object'), w('W00006'), punct('。')],
    "gloss_en": "I look at an old box."
})

# s2: これは何ですか。  -- first SENTENCE-level use of G037 (and W00134, W00135)
s2_tokens = [w('W00134', is_new=True), p('は', 'G001_wa_topic'),
             w('W00135', is_new=True), aux('です', 'G003_desu'),
             {"t":"か","role":"particle","grammar_id":"G037_ka_question","is_new_grammar":True},
             punct('。')]
sentences.append({
    "idx": 2,
    "tokens": s2_tokens,
    "gloss_en": "What is this?"
})

# s3: 私は祖母を見ます。 (I look at grandmother — implies asking)
sentences.append({
    "idx": 3,
    "tokens": [w('W00003'), p('は', 'G001_wa_topic'),
               w('W00098'), p('を', 'G005_wo_object'),
               w('W00006'), punct('。')],
    "gloss_en": "I look at grandmother."
})

# s4: 「思い出です」と言います。
sentences.append({
    "idx": 4,
    "tokens": [punct('「'), w('W00099'), aux('です', 'G003_desu'),
               punct('」'), p('と', 'G028_to_iimasu'),
               w('W00097'), punct('。')],
    "gloss_en": "She says, 'It is a memory.'"
})

# s5: 箱は大切ですか。  (second か use)
sentences.append({
    "idx": 5,
    "tokens": [w('W00136'), p('は', 'G001_wa_topic'),
               w('W00100'), aux('です', 'G003_desu'),
               {"t":"か","role":"particle","grammar_id":"G037_ka_question"},
               punct('。')],
    "gloss_en": "Is the box precious?"
})

# s6: 祖母は嬉しいです。
sentences.append({
    "idx": 6,
    "tokens": [w('W00098'), p('は', 'G001_wa_topic'),
               w('W00056', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "Grandmother is happy."
})

# s7: 「ええ、大切です」と言います。 -- ええ not in vocab. Use はい? Not in vocab either. Skip the affirmation, just have her say it's precious.
# 「とても大切です」 - とても not in vocab. Just: 「大切な箱です」と言います。
sentences.append({
    "idx": 7,
    "tokens": [punct('「'), w('W00100', surface='大切な', inflection={"form":"attributive","grammar_id":"G023_attributive"}),
               w('W00136'), aux('です', 'G003_desu'),
               punct('」'), p('と', 'G028_to_iimasu'),
               w('W00097'), punct('。')],
    "gloss_en": "She says, 'It is a precious box.'"
})

# s8: 箱の中に古い時計があります。 -- 中 not in vocab. Use 箱に...
sentences.append({
    "idx": 8,
    "tokens": [w('W00136'), p('に', 'G004_ni_location'),
               w('W00067', inflection={"form":"attributive","grammar_id":"G023_attributive"}),
               w('W00071'),
               p('が', 'G002_ga_subject'), w('W00044'), punct('。')],
    "gloss_en": "In the box, there is an old clock."
})

# s9: 私は祖母の思い出を思います。
sentences.append({
    "idx": 9,
    "tokens": [w('W00003'), p('は', 'G001_wa_topic'),
               w('W00098'), p('の', 'G015_no_possessive'),
               w('W00099'), p('を', 'G005_wo_object'),
               w('W00043'), punct('。')],
    "gloss_en": "I think of grandmother's memories."
})

# s10: でも、悲しくないです。 -- 悲しくない uses kunai which is G038, not yet introduced. Skip negation.
# Try: でも、私は嬉しいです。
sentences.append({
    "idx": 10,
    "tokens": [disc('でも', 'G032_demo'), punct('、'),
               w('W00003'), p('は', 'G001_wa_topic'),
               w('W00056', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "But I am happy."
})

# s11: 思い出は美しいですから、嬉しいです。
sentences.append({
    "idx": 11,
    "tokens": [w('W00099'), p('は', 'G001_wa_topic'),
               w('W00083', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               aux('です', 'G003_desu'),
               p('から', 'G030_kara_reason'), punct('、'),
               w('W00056', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "Because the memories are beautiful, I am happy."
})

# s12: 古い箱、大切な思い出です。 (closer)
sentences.append({
    "idx": 12,
    "tokens": [w('W00067', inflection={"form":"attributive","grammar_id":"G023_attributive"}),
               w('W00136'), punct('、'),
               w('W00100', surface='大切な', inflection={"form":"attributive","grammar_id":"G023_attributive"}),
               w('W00099'), aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "An old box, a precious memory."
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
    "_id": "story_45",
    "story_id": 45,
    "title": {"jp": "これは何ですか", "en": "What Is This?", "tokens": title_tokens},
    "subtitle": {"jp": "祖母の古い箱。", "en": "Grandmother's old box.", "tokens": subtitle_tokens},
    "new_words": ["W00134", "W00135", "W00136"],
    "new_grammar": ["G037_ka_question"],
    "all_words_used": seen,
    "sentences": sentences
}

with open('pipeline/story_raw.json', 'w') as f:
    json.dump(story, f, ensure_ascii=False, indent=2)
print(f"Story written. Sentences: {len(sentences)}")
print(f"all_words_used: {seen}")
