"""Converte a pesquisa da equipe (mente: claude-code) no pacote importável do CDP."""
import json, re, sys
from datetime import datetime, UTC
SRC='/tmp/claude-0/-home-user-MarketSummary/51d8515e-fc24-58f0-ab60-fbec2a191c25/scratchpad/research/raw_research_final.json'
out_path=sys.argv[1]
week='2026-10-05'
raw=json.load(open(SRC))
DATE=re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
WORDS_M={"1":"primeiro","2":"segundo","3":"terceiro","4":"quarto"}
WORDS_F={"1":"primeira","2":"segunda","3":"terceira","4":"quarta"}
ORDINALS={r'\b([1-4])\s?[ºo°](?=\s)': lambda m: WORDS_M[m.group(1)],
          r'\b([1-4])\s?[ªa](?=\s)': lambda m: WORDS_F[m.group(1)]}
def clean(t):
    """Remove números livres (mantém datas AAAA-MM-DD, anos e rótulos de trimestre)."""
    if not t: return t
    for a,b in ORDINALS.items(): t=re.sub(a,b,t)
    keep={}
    def stash(m):
        k=f'§{len(keep)}§'; keep[k]=m.group(0); return k
    t=DATE.sub(stash,t)
    t=re.sub(r'\b[1-4]T\d{2}\b',stash,t)
    t=re.sub(r'\b(19|20)\d{2}\b',stash,t)
    t=re.sub(r'(?<![§\w])[-+]?\d+(?:[.,]\d+)*\s?(%|x|bps|bp|pp|p\.p\.)?','', t)
    t=re.sub(r'\(\s*[,;:/-]?\s*\)','',t)
    t=re.sub(r'\s+([,.;:])', lambda m: m.group(1), t)
    t=re.sub(r'\s{2,}',' ',t).strip()
    for k,v in keep.items(): t=t.replace(k,v)
    return t
now=datetime.now(UTC).isoformat()
notes=[]
for iid,n in sorted(raw['notes'].items()):
    stance=0 if n['abstain'] else int(n['stance'])
    conf=0.0 if n['abstain'] else float(n['confidence'])
    risks=[clean(x) for x in n['key_risks']]
    el=n['election_sensitivity']
    if el not in ('nao_aplicavel',):
        risks.append(f"Sensibilidade ao segundo turno: {el.replace('_',' ')}.")
    if n['state_owned_or_politically_exposed']:
        risks.append("Emissor estatal ou politicamente exposto (tratado como tema neutro).")
    sq=n['short_squeeze']
    note={
      'note_id': f"cdp-{week}-{iid.lower()}", 'issuer_id': iid, 'week': week, 'role':'fundamental',
      'provider':'claude-code', 'model': None, 'prompt_version':'cdp-pesquisa-semanal-v1',
      'stance': stance, 'confidence': round(conf,2), 'horizon_weeks': int(n['horizon_weeks']),
      'thesis': clean(n['thesis']), 'bull_points':[clean(x) for x in n['bull_points']],
      'bear_points':[clean(x) for x in n['bear_points']],
      'catalysts':[{'description':clean(c['description']), 'expected_date': c['expected_date'] or None, 'direction': c['direction']} for c in n['catalysts']],
      'key_risks': risks,
      'squeeze': None if sq['verdict']=='nao_aplicavel' else {'verdict': sq['verdict'], 'rationale': clean(sq['rationale'])},
      'evidence':[{'kind':'source','ref_id':e['url'],'note':clean(f"{e['title']} ({e['date']}): {e['note']}")} for e in n['evidence'] if e['url'].startswith('http')],
      'created_at': now, 'is_synthetic': False,
    }
    if note['squeeze'] is not None:
        sr=dict(note)
        sr.update({'note_id': note['note_id']+'-short', 'role':'short_risk', 'stance':0,
                   'confidence': round(conf,2) if conf>0 else 0.5,
                   'thesis': note['squeeze']['rationale'] or 'Avaliação de risco de short.',
                   'bull_points':[], 'bear_points':[], 'catalysts': note['catalysts']})
        note=dict(note); note['squeeze']=None
        notes.append(sr)
    notes.append(note)
macro=[]
for scope,m in sorted(raw['macro'].items()):
    macro.append({'note_id': f"cdp-{week}-macro-{scope.lower()}", 'week': week, 'scope': scope, 'stance': int(m['stance']),
      'regime': clean(m['regime']), 'summary': clean(m['summary']),
      'key_events':[{'description':clean(c['description']), 'expected_date': c['expected_date'] or None, 'direction': c['direction']} for c in m['key_events']],
      'risks':[clean(x) for x in m['risks']], 'portfolio_implications':[clean(x) for x in m['portfolio_implications']],
      'evidence':[{'kind':'source','ref_id':e['url'],'note':clean(f"{e['title']} ({e['date']}): {e['note']}")} for e in m['evidence'] if e['url'].startswith('http')],
      'provider':'claude-code','model':None,'prompt_version':'cdp-pesquisa-semanal-v1','created_at':now,'is_synthetic':False})
json.dump({'notes':notes,'macro':macro,'views':[]}, open(out_path,'w'), ensure_ascii=False, indent=2)
print(len(notes),'notas', len(macro),'macro ->', out_path)
