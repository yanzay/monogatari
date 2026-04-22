"""Write story 44: 待ちません (I Don't Wait)."""
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

# Title: 待ちません (W00041 待ちます negative form)
# 待ちません is the masen-form. Token surface = 待ちません, word_id=W00041, inflection.form=masen, grammar_id=G036
title_tokens = [
    w('W00041', surface='待ちません', inflection={"form":"masen","grammar_id":"G036_masen"}),
]

# Subtitle: 友達がすぐに来ます (My friend comes right away)
subtitle_tokens = [
    w('W00022'),
    p('が', 'G002_ga_subject'),
    w('W00133', is_new=True),
    p('に', 'G004_ni_location'),
    w('W00040'),
    punct('。'),
]

sentences = []

# s0: 春の夕方です。
sentences.append({
    "idx": 0,
    "tokens": [w('W00072'), p('の', 'G015_no_possessive'), w('W00018'),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "It is a spring evening."
})

# s1: 私は窓のそばに立ちます。
sentences.append({
    "idx": 1,
    "tokens": [w('W00003'), p('は', 'G001_wa_topic'),
               w('W00004'), p('の', 'G015_no_possessive'),
               w('W00045'), p('に', 'G004_ni_location'),
               w('W00087'), punct('。')],
    "gloss_en": "I stand by the window."
})

# s2: 友達と約束があります。
sentences.append({
    "idx": 2,
    "tokens": [w('W00022'), p('と', 'G010_to_and'),
               w('W00132', is_new=True), p('が', 'G002_ga_subject'),
               w('W00044'), punct('。')],
    "gloss_en": "There is a promise with the friend."
})

# s3: 時々、電話が来ます。
sentences.append({
    "idx": 3,
    "tokens": [w('W00131', is_new=True), punct('、'),
               w('W00093'), p('が', 'G002_ga_subject'),
               w('W00040'), punct('。')],
    "gloss_en": "Sometimes, a phone call comes."
})

# s4: でも、今日は電話はありません。
# 今日 not in vocab. Replace: でも、今日 -> でも、電話はありません。
sentences.append({
    "idx": 4,
    "tokens": [disc('でも', 'G032_demo'), punct('、'),
               w('W00093'), p('は', 'G001_wa_topic'),
               aux('ありません', 'G035_arimasen'),
               punct('。')],
    "gloss_en": "But there is no phone call."
})

# s5: 私は待ちません。  -- first SENTENCE-level use of G036; gets is_new_grammar
s5_tokens = [w('W00003'), p('は', 'G001_wa_topic'),
             w('W00041', surface='待ちません', inflection={"form":"masen","grammar_id":"G036_masen"}),
             punct('。')]
s5_tokens[2]['is_new_grammar'] = True
sentences.append({
    "idx": 5,
    "tokens": s5_tokens,
    "gloss_en": "I do not wait."
})

# s6: 友達はすぐに来ます。
sentences.append({
    "idx": 6,
    "tokens": [w('W00022'), p('は', 'G001_wa_topic'),
               w('W00133'), p('に', 'G004_ni_location'),
               w('W00040'), punct('。')],
    "gloss_en": "The friend comes right away."
})

# s7: 友達は花を持ちます。-- 持ちます not in vocab. Try 友達は花と来ます。 (comes with flowers)
sentences.append({
    "idx": 7,
    "tokens": [w('W00022'), p('は', 'G001_wa_topic'),
               w('W00024'), p('と', 'G010_to_and'),
               w('W00040'), punct('。')],
    "gloss_en": "The friend comes with flowers."
})

# s8: 「元気ですね」と言います。 (Says, 'You're well, huh.')
sentences.append({
    "idx": 8,
    "tokens": [punct('「'), w('W00058'), aux('です', 'G003_desu'),
               {"t":"ね","role":"particle","grammar_id":"G034_ne_confirm"}, punct('」'),
               p('と', 'G028_to_iimasu'),
               w('W00097'), punct('。')],
    "gloss_en": "She says, 'You are well, aren't you.'"
})

# s9: 私は嬉しいです。
sentences.append({
    "idx": 9,
    "tokens": [w('W00003'), p('は', 'G001_wa_topic'),
               w('W00056', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "I am happy."
})

# s10: 私たちは一緒に話します。 -- 私たち not in vocab. Use 二人 (W00035 二人)
sentences.append({
    "idx": 10,
    "tokens": [{"t":"二人","r":"futari","role":"content","word_id":"W00035"}, p('は', 'G001_wa_topic'),
               w('W00050'), w('W00094'), punct('。')],
    "gloss_en": "The two of us talk together."
})

# s11: 約束は美しいですから、嬉しいです。
sentences.append({
    "idx": 11,
    "tokens": [w('W00132'), p('は', 'G001_wa_topic'),
               w('W00083', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               aux('です', 'G003_desu'),
               p('から', 'G030_kara_reason'), punct('、'),
               w('W00056', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "Because the promise is beautiful, I am happy."
})

# s12: 春の夕方、私は待ちません。 (callback closer)
sentences.append({
    "idx": 12,
    "tokens": [w('W00072'), p('の', 'G015_no_possessive'), w('W00018'), punct('、'),
               w('W00003'), p('は', 'G001_wa_topic'),
               w('W00041', surface='待ちません', inflection={"form":"masen","grammar_id":"G036_masen"}),
               punct('。')],
    "gloss_en": "A spring evening — I do not wait."
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
    "_id": "story_44",
    "story_id": 44,
    "title": {"jp": "待ちません", "en": "I Do Not Wait", "tokens": title_tokens},
    "subtitle": {"jp": "友達がすぐに来ます。", "en": "My friend comes right away.", "tokens": subtitle_tokens},
    "new_words": ["W00131", "W00132", "W00133"],
    "new_grammar": ["G036_masen"],
    "all_words_used": seen,
    "sentences": sentences
}

with open('pipeline/story_raw.json', 'w') as f:
    json.dump(story, f, ensure_ascii=False, indent=2)
print(f"Story written. Sentences: {len(sentences)}")
print(f"all_words_used: {seen}")
