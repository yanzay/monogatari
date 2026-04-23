"""Story 66: 入ってもいいですか — てもいい. Sentence band 16-18."""
import json

CHECKS = {
    'W00003':('私','わたし'),'W00033':('本','ほん'),'W00084':('店','みせ'),'W00113':('人','ひと'),
    'W00009':('お茶','おちゃ'),'W00010':('飲みます','のみます'),
    'W00097':('言います','いいます'),'W00043':('思います','おもいます'),
    'W00056':('嬉しい','うれしい'),'W00120':('心','こころ'),'W00012':('温かい','あたたかい'),
    'W00067':('古い','ふるい'),'W00072':('春','はる'),'W00018':('夕方','ゆうがた'),
    'W00046':('明日','あした'),'W00132':('約束','やくそく'),'W00146':('来週','らいしゅう'),
    'W00098':('祖母','そぼ'),'W00022':('友達','ともだち'),
    'W00150':('行きます','いきます'),'W00040':('来ます','きます'),
    'W00006':('見ます','みます'),'W00094':('話します','はなします'),'W00050':('一緒に','いっしょに'),
    'W00029':('います','います'),'W00044':('あります','あります'),
    'W00076':('悲しい','かなしい'),'W00013':('いい','いい'),'W00011':('静か','しずか'),
    'W00078':('家','いえ'),'W00075':('部屋','へや'),'W00030':('夜','よる'),
    'W00015':('朝','あさ'),'W00135':('何','なに'),'W00148':('この','この'),
    'W00147':('あの','あの'),'W00134':('これ','これ'),'W00066':('新しい','あたらしい'),
    'W00034':('読みます','よみます'),'W00114':('好き','すき'),'W00060':('書きます','かきます'),
    'W00154':('ノート','ノート'),'W00080':('入ります','はいります'),'W00085':('座ります','すわります'),
    'W00104':('学校','がっこう'),'W00125':('ドア','ドア'),
    'W00057':('大きい','おおきい'),'W00058':('元気','げんき'),
}

def cw(wid, **kwargs):
    surface, reading = CHECKS[wid]
    t = {'t': surface, 'r': reading, 'role': 'content', 'word_id': wid}
    t.update(kwargs)
    return t
def p(s,gid,r=None): return {'t':s,'role':'particle','grammar_id':gid,'r':r or s}
def aux(s,gid,r=None): return {'t':s,'role':'aux','grammar_id':gid,'r':r or s}
def punct(s): return {'t':s,'role':'punct'}
def des(): return aux('です','G003_desu','です')
def wa(): return p('は','G001_wa_topic','は')
def ga(): return p('が','G002_ga_subject','が')
def ga_but(): return p('が','G049_ga_but','が')
def wo(): return p('を','G005_wo_object','を')
def no(): return p('の','G015_no_possessive','の')
def ni(): return p('に','G004_ni_location','に')
def to_quote(): return p('と','G028_to_iimasu','と')
def vmasu(wid):
    return cw(wid, inflection={'form':'masu_polite_nonpast','grammar_id':'G026_masu_nonpast'})
def vmashita(wid):
    base_surface, base_reading = CHECKS[wid]
    new_t = base_surface[:-2] + 'ました'
    new_r = base_reading[:-2] + 'ました'
    base_dict = {'入ります':('入る','はいる'),'座ります':('座る','すわる'),'飲みます':('飲む','のむ'),
                 '言います':('言う','いう'),'来ます':('来る','くる'),'行きます':('行く','いく'),
                 '見ます':('見る','みる'),'話します':('話す','はなす'),'読みます':('読む','よむ'),
                 '書きます':('書く','かく'),'思います':('思う','おもう')}
    bd, br = base_dict.get(base_surface, (base_surface, base_reading))
    return {'t':new_t,'r':new_r,'role':'content','word_id':wid,
            'inflection':{'form':'polite_past','grammar_id':'G013_mashita_past','base':bd,'base_r':br}}
def iadj(wid, attr=False):
    if attr:
        return cw(wid, inflection={'form':'attributive','grammar_id':'G023_attributive'})
    return cw(wid, inflection={'form':'plain_nonpast','grammar_id':'G022_i_adj'})

def te_form(wid):
    """Returns te-form token for a verb."""
    base_surface = CHECKS[wid][0]
    te_dict = {
        '入ります':('入って','はいって','入る','はいる'),
        '座ります':('座って','すわって','座る','すわる'),
        '飲みます':('飲んで','のんで','飲む','のむ'),
        '読みます':('読んで','よんで','読む','よむ'),
        '話します':('話して','はなして','話す','はなす'),
        '見ます':('見て','みて','見る','みる'),
        '食べます':('食べて','たべて','食べる','たべる'),
        '行きます':('行って','いって','行く','いく'),
        '言います':('言って','いって','言う','いう'),
    }
    surf, read, base, base_r = te_dict[base_surface]
    return {'t':surf,'r':read,'role':'content','word_id':wid,
            'inflection':{'form':'te_form','grammar_id':'G007_te_form','base':base,'base_r':base_r}}

def temo_ii(is_first=False):
    """もいい portion after a te-form."""
    tokens = [
        {'t':'も','role':'particle','grammar_id':'G009_mo_also','r':'も'},
        {'t':'いい','r':'いい','role':'content','word_id':'W00013',
         'inflection':{'form':'plain_nonpast','grammar_id':'G057_temo_ii' if is_first else 'G057_temo_ii'}},
    ]
    if is_first:
        tokens[1]['is_new_grammar'] = True
    # Wait — G058 is the new grammar id, not G057
    return tokens

def temo_ii_block(verb_wid, with_desuka=True, with_desu=False, is_first=False):
    """Builds [verb-te] + も + いい [+ ですか/です]."""
    out = [te_form(verb_wid)]
    out.append({'t':'も','role':'particle','grammar_id':'G009_mo_also','r':'も'})
    iitok = {'t':'いい','r':'いい','role':'content','word_id':'W00013',
             'inflection':{'form':'plain_nonpast','grammar_id':'G058_temo_ii'}}
    if is_first: iitok['is_new_grammar'] = True
    out.append(iitok)
    if with_desuka:
        out.append(des())
        out.append({'t':'か','role':'particle','grammar_id':'G037_ka_question','r':'か'})
    elif with_desu:
        out.append(des())
    return out

story = {
    'story_id': 66,
    'title': {'jp':'入ってもいいですか。','en':'May I Come In?',
              'tokens':[
                  te_form('W00080'),
                  {'t':'も','role':'particle','grammar_id':'G009_mo_also','r':'も'},
                  {'t':'いい','r':'いい','role':'content','word_id':'W00013',
                   'inflection':{'form':'plain_nonpast','grammar_id':'G058_temo_ii'}},
                  des(),
                  {'t':'か','role':'particle','grammar_id':'G037_ka_question','r':'か'},
                  punct('。')],
              'gloss_en':'May I come in?'},
    'subtitle': {'jp':'本の店の人が家に来ました。','en':'The bookstore person came to the house.',
                 'tokens':[cw('W00033'),no(),cw('W00084'),no(),cw('W00113'),ga(),
                           cw('W00078'),ni(),vmashita('W00040'),punct('。')],
                 'gloss_en':'The bookstore person came to my house.'},
    'sentences': []
}
S = story['sentences']

# s0: 春の夕方です。
S.append({'idx':0,'tokens':[cw('W00072'),no(),cw('W00018'),des(),punct('。')],
    'gloss_en':'It is a spring evening.'})

# s1: 私は部屋にいます。
S.append({'idx':1,'tokens':[cw('W00003'),wa(),cw('W00075'),ni(),
    {'t':'います','r':'います','role':'content','word_id':'W00029'},punct('。')],
    'gloss_en':'I am in my room.'})

# s2: 部屋は静かです。
S.append({'idx':2,'tokens':[cw('W00075'),wa(),cw('W00011'),
    aux('です','G003_desu','です'),punct('。')],
    'gloss_en':'The room is quiet.'})

# s3: ドアの音が聞こえます。 — Hmm 聞こえます not in vocab. Use:
# ドアに人が来ます。 — Someone comes to the door.
# Better: 誰かが来ます — 誰か not in vocab. Use:
# ドアに本の店の人がいます。 — The bookstore person is at the door.
S.append({'idx':3,'tokens':[cw('W00125'),ni(),cw('W00033'),no(),cw('W00084'),no(),cw('W00113'),ga(),
    {'t':'います','r':'います','role':'content','word_id':'W00029'},punct('。')],
    'gloss_en':'The bookstore person is at the door.'})

# s4: 「入ってもいいですか」とあの人は言いました。 — first temo_ii in sentence-level
# is_new_grammar must be on first sentence-level use (not title)
s4_tokens = [punct('「')] + temo_ii_block('W00080', with_desuka=True, is_first=True) + [
    punct('」'),
    to_quote(),
    cw('W00147'),cw('W00113'),wa(),
    vmashita('W00097'),punct('。')]
S.append({'idx':4,'tokens':s4_tokens,
    'gloss_en':'"May I come in?" that person said.'})

# s5: 「入ってもいいです」と私は言いました。 — second temo_ii
s5_tokens = [punct('「')] + temo_ii_block('W00080', with_desuka=False, with_desu=True) + [
    punct('」'),
    to_quote(),
    cw('W00003'),wa(),
    vmashita('W00097'),punct('。')]
S.append({'idx':5,'tokens':s5_tokens,
    'gloss_en':'"You may come in," I said.'})

# s6: あの人は部屋に入りました。
S.append({'idx':6,'tokens':[cw('W00147'),cw('W00113'),wa(),cw('W00075'),ni(),vmashita('W00080'),punct('。')],
    'gloss_en':'That person came into the room.'})

# s7: 「座ってもいいですか」と言いました。 — third temo_ii
s7_tokens = [punct('「')] + temo_ii_block('W00085', with_desuka=True) + [
    punct('」'),
    to_quote(),
    vmashita('W00097'),punct('。')]
S.append({'idx':7,'tokens':s7_tokens,
    'gloss_en':'"May I sit?" he said.'})

# s8: 「どうぞ」と私は言いました。 — どうぞ W00149
S.append({'idx':8,'tokens':[punct('「'),
    {'t':'どうぞ','r':'どうぞ','role':'content','word_id':'W00149'},
    punct('」'),
    to_quote(),
    cw('W00003'),wa(),vmashita('W00097'),punct('。')],
    'gloss_en':'"Please do," I said.'})

# s9: あの人は座りました。
S.append({'idx':9,'tokens':[cw('W00147'),cw('W00113'),wa(),vmashita('W00085'),punct('。')],
    'gloss_en':'That person sat down.'})

# s10: 「お茶を飲んでもいいですか」と言いました。 — fourth temo_ii
s10_tokens = [punct('「'),cw('W00009'),wo()] + temo_ii_block('W00010', with_desuka=True) + [
    punct('」'),
    to_quote(),
    vmashita('W00097'),punct('。')]
S.append({'idx':10,'tokens':s10_tokens,
    'gloss_en':'"May I drink tea?" he said.'})

# s11: 私たちは一緒にお茶を飲みました。 — 私たち not in vocab. Use:
# 私とあの人は一緒にお茶を飲みました。
S.append({'idx':11,'tokens':[cw('W00003'),
    p('と','G010_to_and','と'),
    cw('W00147'),cw('W00113'),wa(),
    cw('W00050'),cw('W00009'),wo(),vmashita('W00010'),punct('。')],
    'gloss_en':'That person and I drank tea together.'})

# s12: あの人は新しい本を見せました。 — 見せます W00153
# Already have 見せます in vocab now (story 62)
CHECKS['W00153'] = ('見せます','みせます')
S.append({'idx':12,'tokens':[cw('W00147'),cw('W00113'),wa(),iadj('W00066',attr=True),cw('W00033'),wo(),
    vmashita('W00153'),punct('。')],
    'gloss_en':'That person showed a new book.'})

# s13: 「この本はあなたの本です」と言いました。 — あなた not in vocab. Use:
# 「この本はあなたの好きな本です」と言いました。 — same problem
# Use plain past in quote: 「この本を買った」と言いました。 — G056 reinforce
S.append({'idx':13,'tokens':[punct('「'),
    cw('W00148'),cw('W00033'),wo(),
    {'t':'買った','r':'かった','role':'content','word_id':'W00086',
     'inflection':{'form':'plain_past','grammar_id':'G056_plain_past_pair','base':'買う','base_r':'かう'}},
    punct('」'),
    to_quote(),
    vmashita('W00097'),punct('。')],
    'gloss_en':'"I bought this book," he said.'})
CHECKS['W00086'] = ('買います','かいます')

# s14: 私はノートに書きます。「人が来た」と書きます。 — too long. Split:
# Actually just one: 私はノートに「人が来た」と書きます。 — G055 plain past in quote
S.append({'idx':14,'tokens':[cw('W00003'),wa(),cw('W00154'),ni(),
    punct('「'),cw('W00113'),ga(),
    {'t':'来た','r':'きた','role':'content','word_id':'W00040',
     'inflection':{'form':'plain_past','grammar_id':'G056_plain_past_pair','base':'来る','base_r':'くる'}},
    punct('」'),
    to_quote(),
    vmasu('W00060'),punct('。')],
    'gloss_en':'I write in the notebook, "Someone came."'})

# s15: 心が温かいです。
S.append({'idx':15,'tokens':[cw('W00120'),ga(),iadj('W00012'),des(),punct('。')],
    'gloss_en':'My heart is warm.'})

# s16 closer: 春の夕方、新しい本、温かいお茶です。
S.append({'idx':16,'tokens':[cw('W00072'),no(),cw('W00018'),punct('、'),
    iadj('W00066',attr=True),cw('W00033'),punct('、'),
    iadj('W00012',attr=True),cw('W00009'),des(),punct('。')],
    'gloss_en':'A spring evening, a new book, warm tea.'})

# Build all_words_used
seen = []
def collect(tokens):
    for t in tokens:
        wid = t.get('word_id')
        if wid and wid not in seen: seen.append(wid)
collect(story['title']['tokens'])
collect(story['subtitle']['tokens'])
for s in S: collect(s['tokens'])

story['new_words'] = []
story['new_grammar'] = ['G058_temo_ii']
story['all_words_used'] = seen

with open('pipeline/story_raw.json','w') as f:
    json.dump(story, f, ensure_ascii=False, indent=2)
print(f'Story 66 written. Sentences: {len(S)}, Words: {len(seen)}')
