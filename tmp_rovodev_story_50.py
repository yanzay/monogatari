"""Story 50: いつ来ますか

VERIFIED IDs (do not trust memory):
- 私 W00003, 友達 W00022, 本 W00033, 店 W00084, 人 W00113, 待ちます W00041
- 春 W00072, 夕方 W00018, 朝 W00019, 心 W00120, 嬉しい W00056, 悲しい W00057?
- お茶 W00009, 飲みます W00010, 言います W00097, 思います W00043, 話します W00094
- 庭 W00059, 後ろ W00144, 花 W00024, 雨 W00002, 傘 W00116
- 来ます W00040, 行きます (NOT IN VOCAB), 歩きます W00017
- 約束 W00132, 時々 W00131, でも (G032_demo, role='aux')
- どこ W00143, 誰 W00140, 何 W00135?, これ W00134?
- 手紙 W00075? (verify)
- 静か W00011, 温かい W00012, 古い W00067, 新しい W00066
- あります W00044, います W00029
- New: いつ W00145, 来週 W00146

Grammar IDs (verified):
- G001_wa_topic, G002_ga_subject, G005_wo_object, G004_ni_location, G009_mo_also
- G010_to_and, G014_to_omoimasu, G015_no_possessive, G017_de_means
- G003_desu, G021_aru_iru, G022_i_adj, G023_attributive, G026_masu_nonpast
- G028_to_iimasu (quotative と), G032_demo, G037_ka_question
- New: G042_itsu_when

Special tokens:
- あります/います: role='content', word_id required
- でも: role='aux', grammar_id='G032_demo' (no word_id)
- そして, でも: same pattern
"""
import json
import sys

# Verify IDs first
with open('data/vocab_state.json') as f:
    vocab = json.load(f)['words']

CHECKS = {
    'W00003':'私', 'W00022':'友達', 'W00033':'本', 'W00084':'店', 'W00113':'人',
    'W00041':'待ちます', 'W00072':'春', 'W00018':'夕方', 'W00019':'朝',
    'W00120':'心', 'W00056':'嬉しい', 'W00009':'お茶', 'W00010':'飲みます',
    'W00097':'言います', 'W00043':'思います', 'W00094':'話します',
    'W00059':'庭', 'W00144':'後ろ', 'W00024':'花', 'W00002':'雨', 'W00116':'傘',
    'W00040':'来ます', 'W00132':'約束', 'W00131':'時々',
    'W00143':'どこ', 'W00140':'誰', 'W00011':'静か', 'W00012':'温かい',
    'W00067':'古い', 'W00066':'新しい', 'W00044':'あります', 'W00029':'います',
    'W00145':'いつ', 'W00146':'来週'
}
for wid, expected in CHECKS.items():
    if wid not in vocab:
        if wid in ('W00145','W00146'):  # plan additions
            continue
        print(f'!! MISSING {wid}', file=sys.stderr)
    elif vocab[wid].get('surface') != expected:
        print(f'!! MISMATCH {wid}: vocab={vocab[wid].get("surface")} mine={expected}', file=sys.stderr)

READINGS = {
    'W00003':'watashi','W00022':'tomodachi','W00033':'hon','W00084':'mise','W00113':'hito',
    'W00041':'machimasu','W00072':'haru','W00018':'yuugata','W00019':'asa',
    'W00120':'kokoro','W00056':'ureshii','W00009':'ocha','W00010':'nomimasu',
    'W00097':'iimasu','W00043':'omoimasu','W00094':'hanashimasu',
    'W00059':'niwa','W00144':'ushiro','W00024':'hana','W00002':'ame','W00116':'kasa',
    'W00040':'kimasu','W00132':'yakusoku','W00131':'tokidoki',
    'W00143':'doko','W00140':'dare','W00011':'shizuka','W00012':'atatakai',
    'W00067':'furui','W00066':'atarashii','W00044':'arimasu','W00029':'imasu',
    'W00145':'itsu','W00146':'raishuu',
}

def cw(wid, **kwargs):
    t = {'t': CHECKS[wid], 'r': READINGS[wid], 'role': 'content', 'word_id': wid}
    t.update(kwargs)
    return t

def p(surface, gid, reading=None):
    return {'t': surface, 'role': 'particle', 'grammar_id': gid, 'r': reading or surface}

def aux(surface, gid, reading=None):
    return {'t': surface, 'role': 'aux', 'grammar_id': gid, 'r': reading or surface}

def punct(s):
    return {'t': s, 'role': 'punct'}

def des(): return aux('です', 'G003_desu', 'desu')
def wa(): return p('は', 'G001_wa_topic', 'wa')
def ga(): return p('が', 'G002_ga_subject', 'ga')
def wo(): return p('を', 'G005_wo_object', 'wo')
def no(): return p('の', 'G015_no_possessive', 'no')
def ni(): return p('に', 'G004_ni_location', 'ni')
def mo(): return p('も', 'G009_mo_also', 'mo')
def ka(): return p('か', 'G037_ka_question', 'ka')
def to_quote(): return p('と', 'G028_to_iimasu', 'to')
def to_omou(): return p('と', 'G014_to_omoimasu', 'to')

# Verb in masu form
def vmasu(wid, **kwargs):
    t = cw(wid, inflection={'form':'masu_polite_nonpast','grammar_id':'G026_masu_nonpast'})
    t.update(kwargs)
    return t
# i-adjective plain
def iadj(wid, attributive=False, **kwargs):
    form = 'attributive' if attributive else 'plain_nonpast'
    t = cw(wid, inflection={'form':form,'grammar_id':'G023_attributive' if attributive else 'G022_i_adj'})
    t.update(kwargs)
    return t

story = {
    'story_id': 50,
    'title': {'jp':'いつ来ますか。','en':'When Will You Come?',
              'tokens':[cw('W00145', is_new=True, grammar_id='G042_itsu_when'),
                        vmasu('W00040'),
                        ka(), punct('。')],
              'gloss_en':'When will you come?'},
    'subtitle': {'jp':'私は本の店の人を待ちます。','en':'I wait for the bookstore person.',
                 'tokens':[cw('W00003'), wa(), cw('W00033'), no(),
                           cw('W00084'), no(), cw('W00113'), wo(),
                           vmasu('W00041'), punct('。')],
                 'gloss_en':'I wait for the bookstore person.'},
    'sentences': []
}
S = story['sentences']

# s0: 静かな朝です。
S.append({'idx':0,'tokens':[cw('W00011', inflection={'form':'attributive','grammar_id':'G016_na_adjective'}),
    {'t':'な','role':'particle','grammar_id':'G016_na_adjective'},
    cw('W00019'), des(), punct('。')],
    'gloss_en':'It is a quiet morning.'})
# Wait — na-adjective attributive uses just な, no separate inflection. Let me fix.
S[0] = {'idx':0,'tokens':[
    {'t':'静か','r':'shizuka','role':'content','word_id':'W00011',
     'inflection':{'form':'attributive','grammar_id':'G016_na_adjective'}},
    {'t':'な','role':'particle','grammar_id':'G016_na_adjective'},
    cw('W00019'), des(), punct('。')],
    'gloss_en':'It is a quiet morning.'}

# s1: 私は手紙を書きます。 — Need 手紙 W00? and 書きます W00?. Let me lookup
# Skip — use simpler: 私はお茶を飲みます。
S.append({'idx':1,'tokens':[cw('W00003'), wa(), cw('W00009'), wo(),
    vmasu('W00010'), punct('。')],
    'gloss_en':'I drink tea.'})

# s2: 私は本の店の人を思います。
S.append({'idx':2,'tokens':[cw('W00003'), wa(),
    cw('W00033'), no(), cw('W00084'), no(), cw('W00113'),
    wo(), vmasu('W00043'), punct('。')],
    'gloss_en':'I think of the bookstore person.'})

# s3: 「いつ来ますか」と思います。 — first いつ
S.append({'idx':3,'tokens':[
    punct('「'),
    cw('W00145', grammar_id='G042_itsu_when'),
    vmasu('W00040'), ka(),
    punct('」'),
    to_omou(),
    {'t':'思います','r':'omoimasu','role':'aux','grammar_id':'G014_to_omoimasu'},
    punct('。')],
    'gloss_en':'I think, "when will (he) come?"'})

# s4: 友達も「いつ来ますか」と言います。 — second いつ
S.append({'idx':4,'tokens':[
    cw('W00022'), mo(),
    punct('「'),
    cw('W00145', grammar_id='G042_itsu_when'),
    vmasu('W00040'), ka(),
    punct('」'),
    to_quote(),
    vmasu('W00097'),
    punct('。')],
    'gloss_en':'The friend too says, "when will (he) come?"'})

# s5: 友達は嬉しい人です。 — friend is happy person, contrast with narrator's anxiety
# Actually skip — use: でも、本の店の人は来ません。
S.append({'idx':5,'tokens':[
    {'t':'でも','r':'demo','role':'aux','grammar_id':'G032_demo'},
    punct('、'),
    cw('W00033'), no(), cw('W00084'), no(), cw('W00113'), wa(),
    {'t':'来ません','r':'kimasu','role':'content','word_id':'W00040',
     'inflection':{'form':'masen','grammar_id':'G036_masen'}},
    punct('。')],
    'gloss_en':'But the bookstore person does not come.'})

# s6: 私は庭に出ます。 — Need 出ます W00?. Use 庭にいます instead.
S.append({'idx':6,'tokens':[
    cw('W00003'), wa(), cw('W00059'), ni(), cw('W00029'),
    punct('。')],
    'gloss_en':'I am in the garden.'})

# s7: 春の花は嬉しいです。 — flowers happy
S.append({'idx':7,'tokens':[
    cw('W00072'), no(), cw('W00024'), wa(),
    iadj('W00056'), des(), punct('。')],
    'gloss_en':'The spring flowers are happy.'})

# s8: でも、私の心は静かではありません。 — Hmm "ではありません" advanced. Skip.
# Use: でも、私の心は嬉しくないです。 (G038_kunai reinforcement!)
S.append({'idx':8,'tokens':[
    {'t':'でも','r':'demo','role':'aux','grammar_id':'G032_demo'},
    punct('、'),
    cw('W00003'), no(), cw('W00120'), wa(),
    {'t':'嬉しくない','r':'ureshikunai','role':'content','word_id':'W00056',
     'inflection':{'form':'kunai','grammar_id':'G038_kunai'}},
    des(), punct('。')],
    'gloss_en':'But my heart is not happy.'})

# s9: 「いつ会いますか」… 会います not in vocab. Try: 「いつ話しますか」と思います。 — third いつ
S.append({'idx':9,'tokens':[
    punct('「'),
    cw('W00145', grammar_id='G042_itsu_when'),
    vmasu('W00094'), ka(),
    punct('」'),
    to_omou(),
    {'t':'思います','r':'omoimasu','role':'aux','grammar_id':'G014_to_omoimasu'},
    punct('。')],
    'gloss_en':'I think, "when will we talk?"'})

# s10: 来週、約束です。 — first 来週
S.append({'idx':10,'tokens':[
    cw('W00146', is_new=True), punct('、'),
    cw('W00132'), des(), punct('。')],
    'gloss_en':'Next week — it is the promise.'})

# s11: 友達は「来週、本の店に行きませんか」と言います。 — but 行きます not in vocab.
# Use 来週、本の店に来ませんか (won't (he) come to the bookstore next week?) — invitation
S.append({'idx':11,'tokens':[
    cw('W00022'), wa(),
    punct('「'),
    cw('W00146'), punct('、'),
    cw('W00033'), no(), cw('W00084'), ni(),
    {'t':'来ませんか','r':'kimasu','role':'content','word_id':'W00040',
     'inflection':{'form':'masen','grammar_id':'G041_masenka_invitation'}},
    punct('』'),  # Wait, used 「 not 『. Let me close with 」
    to_quote(),
    vmasu('W00097'),
    punct('。')],
    'gloss_en':'The friend says, "won\'t (he) come to the bookstore next week?"'})

# Fix s11: replace 』 with 」 and split 来ませんか into 来ません + か
S[11]['tokens'] = [
    cw('W00022'), wa(),
    punct('「'),
    cw('W00146'), punct('、'),
    cw('W00033'), no(), cw('W00084'), ni(),
    {'t':'来ません','r':'kimasu','role':'content','word_id':'W00040',
     'inflection':{'form':'masen','grammar_id':'G041_masenka_invitation'}},
    ka(),
    punct('」'),
    to_quote(),
    vmasu('W00097'),
    punct('。')]

# s12: 私は嬉しいです。
S.append({'idx':12,'tokens':[
    cw('W00003'), wa(), iadj('W00056'), des(), punct('。')],
    'gloss_en':'I am happy.'})

# s13: 来週、本の店に行きます。 — verbless: 来週、本の店です。
S.append({'idx':13,'tokens':[
    cw('W00146'), punct('、'), cw('W00033'), no(), cw('W00084'),
    des(), punct('。')],
    'gloss_en':'Next week — the bookstore.'})

# s14: 春の夕方、温かい心です。
S.append({'idx':14,'tokens':[
    cw('W00072'), no(), cw('W00018'), punct('、'),
    iadj('W00012', attributive=True), cw('W00120'),
    des(), punct('。')],
    'gloss_en':'Spring evening, warm heart.'})

# Build all_words_used
seen = []
def collect(tokens):
    for t in tokens:
        wid = t.get('word_id')
        if wid and wid not in seen:
            seen.append(wid)
collect(story['title']['tokens'])
collect(story['subtitle']['tokens'])
for s in S:
    collect(s['tokens'])

story['new_words'] = ['W00145','W00146']
story['new_grammar'] = ['G042_itsu_when']
story['all_words_used'] = seen

with open('pipeline/story_raw.json','w') as f:
    json.dump(story, f, ensure_ascii=False, indent=2)
print(f'Story 50 written. Sentences: {len(S)}')
print(f'Words used: {len(seen)}')
