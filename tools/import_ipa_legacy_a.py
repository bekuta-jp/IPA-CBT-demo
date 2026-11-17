#!/usr/bin/env python3
"""Import pre-2021 official AP morning questions, retaining image/answer-source provenance."""
import argparse,json
from pathlib import Path
import import_ipa_bulk as bulk
ROOT=Path(__file__).resolve().parents[1]
# OCR misses are recorded only after verification of question-heading positions.
CALIBRATED_LEGACY={}

def run(session,probe=False):
    src=json.loads((ROOT/'tools/ipa-sources.json').read_text(encoding='utf-8'))[session]['am']
    qs=bulk.get_pdf(src['qs']);ans=bulk.get_pdf(src['ans'])
    key=bulk.answer_key(ans,session)
    bulk.CALIBRATED_MISSING[session]=CALIBRATED_LEGACY.get(session,[])
    marks=bulk.find_positions(qs,session)
    if probe:print('PROBE_OK',session,flush=True);return
    dest=ROOT/'assets'/('ap-'+session);dest.mkdir(parents=True,exist_ok=True)
    yyyy,season=session.split('-');jp={'spring':'春期','autumn':'秋期','october':'10月'}[season]
    records=[];rot=[]
    for i in range(80):
        image,stem,angle=bulk.one_image(qs,marks,i,dest,session)
        rot.append(angle)
        records.append({'id':f'{session}-q{i+1:02d}','number':i+1,
          'topic':('テクノロジ系' if i<50 else 'マネジメント系' if i<60 else 'ストラテジ系'),
          'stem':stem,'image':f'assets/ap-{session}/q{i+1:02d}.webp','imageOnly':True,
          'options':['原本画像内の選択肢ア','原本画像内の選択肢イ','原本画像内の選択肢ウ','原本画像内の選択肢エ'],
          'answer':key[i+1],'explanation':'',
          'source':f'出典：IPA {yyyy}年度{jp} 応用情報技術者試験 午前 問{i+1} {src["qs"]}',
          'modified':True,'modificationNote':'公式問題の画像切り出し・保守的傾き補正。OCR文字列は参考情報であり原本画像を正とします。',
          'deskewDegrees':angle})
    data={'id':'ap-'+session,'title':f'{yyyy}年度 {jp} 応用情報 午前［公式問題画像］',
     'year':int(yyyy),'season':jp,'sourceType':'ipa','exam':'AP',
     'sourceUrl':src['qs'],'answerUrl':src['ans'],'imageOnly':True,'questions':records}
    file=ROOT/'sets'/('ap-'+session+'.json');file.parent.mkdir(parents=True,exist_ok=True)
    file.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert len(records)==80 and len(list(dest.glob('q*.webp')))==80
    print('BUILT_A',session,80,'rotated',sum(bool(x) for x in rot),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--session',required=True);p.add_argument('--probe',action='store_true');a=p.parse_args();run(a.session,a.probe)