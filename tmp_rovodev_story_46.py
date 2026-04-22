"""Write story 46: 寒くない朝 (A Not-Cold Morning)."""
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

# Title: 寒くない朝 (W00062 寒い in kunai form + W00015 朝)
title_tokens = [
    w('W00062', surface='寒くない', inflection={"form":"kunai","grammar_id":"G038_kunai"}),
    w('W00015'),
]

# Subtitle: 春の光 (W00072 春 + の + W00139 光)
subtitle_tokens = [
    w('W00072'),
    p('の', 'G015_no_possessive'),
    w('W00139', is_new=True),
    punct('。'),
]

sentences = []

# s0: 春の朝です。
sentences.append({
    "idx": 0,
    "tokens": [w('W00072'), p('の', 'G015_no_possessive'), w('W00015'),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "It is a spring morning."
})

# s1: 朝は寒くないです。  (first sentence-level use of G038)
s1_tokens = [w('W00015'), p('は', 'G001_wa_topic'),
             w('W00062', surface='寒くない', inflection={"form":"kunai","grammar_id":"G038_kunai"}),
             aux('です', 'G003_desu'), punct('。')]
s1_tokens[2]['is_new_grammar'] = True
sentences.append({
    "idx": 1,
    "tokens": s1_tokens,
    "gloss_en": "The morning is not cold."
})

# s2: 空気は明るいです。 (The air is bright.)
sentences.append({
    "idx": 2,
    "tokens": [w('W00138', is_new=True), p('は', 'G001_wa_topic'),
               w('W00137', is_new=True, inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "The air is bright."
})

# s3: 空には花の光があります。 -- 空に + 花の光 -- a stretch but works as image
# Simpler: 春の光は温かいです。
sentences.append({
    "idx": 3,
    "tokens": [w('W00072'), p('の', 'G015_no_possessive'), w('W00139'),
               p('は', 'G001_wa_topic'),
               w('W00012', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "The spring light is warm."
})

# s4: 私は窓のそばに立ちます。
sentences.append({
    "idx": 4,
    "tokens": [w('W00003'), p('は', 'G001_wa_topic'),
               w('W00004'), p('の', 'G015_no_possessive'),
               w('W00045'), p('に', 'G004_ni_location'),
               w('W00087'), punct('。')],
    "gloss_en": "I stand by the window."
})

# s5: 鳥が空にいます。
sentences.append({
    "idx": 5,
    "tokens": [w('W00054'), p('が', 'G002_ga_subject'),
               w('W00047'), p('に', 'G004_ni_location'),
               {"t":"います","r":"imasu","role":"content","word_id":"W00029"},
               punct('。')],
    "gloss_en": "A bird is in the sky."
})

# s6: 庭に花があります。 -- 庭 not in vocab. Use 部屋に花があります。
sentences.append({
    "idx": 6,
    "tokens": [w('W00075'), p('に', 'G004_ni_location'),
               w('W00024'), p('が', 'G002_ga_subject'),
               w('W00044'), punct('。')],
    "gloss_en": "There are flowers in the room."
})

# s7: 花は美しいです。
sentences.append({
    "idx": 7,
    "tokens": [w('W00024'), p('は', 'G001_wa_topic'),
               w('W00083', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "The flowers are beautiful."
})

# s8: 冬は寒いです。でも、春は寒くないです。
# Two sentences would be too long. Combine: 冬は寒いですから、春が嬉しいです。 — but this is generic
# Better: use kunai again as comparison: 冬の朝は寒いです。春の朝は寒くないです。
sentences.append({
    "idx": 8,
    "tokens": [w('W00095'), p('の', 'G015_no_possessive'), w('W00015'),
               p('は', 'G001_wa_topic'),
               w('W00062', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "Winter mornings are cold."
})

# s9: でも、春の朝は寒くないです。 (second use of kunai)
sentences.append({
    "idx": 9,
    "tokens": [disc('でも', 'G032_demo'), punct('、'),
               w('W00072'), p('の', 'G015_no_possessive'), w('W00015'),
               p('は', 'G001_wa_topic'),
               w('W00062', surface='寒くない', inflection={"form":"kunai","grammar_id":"G038_kunai"}),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "But spring mornings are not cold."
})

# s10: 私は嬉しいです。
sentences.append({
    "idx": 10,
    "tokens": [w('W00003'), p('は', 'G001_wa_topic'),
               w('W00056', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "I am happy."
})

# s11: 春が来ますから、私は待ちません。 (callback to story 44)
sentences.append({
    "idx": 11,
    "tokens": [w('W00072'), p('が', 'G002_ga_subject'),
               w('W00040'), p('から', 'G030_kara_reason'), punct('、'),
               w('W00003'), p('は', 'G001_wa_topic'),
               w('W00041', surface='待ちません', inflection={"form":"masen","grammar_id":"G036_masen"}),
               punct('。')],
    "gloss_en": "Because spring is coming, I do not wait."
})

# s12: 明るい朝、温かい光です。 (closer)
sentences.append({
    "idx": 12,
    "tokens": [w('W00137', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               w('W00015'), punct('、'),
               w('W00012', inflection={"form":"plain_nonpast","grammar_id":"G022_i_adj"}),
               w('W00139'), aux('です', 'G003_desu'), punct('。')],
    "gloss_en": "A bright morning, a warm light."
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
    "_id": "story_46",
    "story_id": 46,
    "title": {"jp": "寒くない朝", "en": "A Not-Cold Morning", "tokens": title_tokens},
    "subtitle": {"jp": "春の光。", "en": "The light of spring.", "tokens": subtitle_tokens},
    "new_words": ["W00137", "W00138", "W00139"],
    "new_grammar": ["G038_kunai"],
    "all_words_used": seen,
    "sentences": sentences
}

with open('pipeline/story_raw.json', 'w') as f:
    json.dump(story, f, ensure_ascii=False, indent=2)
print(f"Story written. Sentences: {len(sentences)}")
print(f"all_words_used: {seen}")
