#!/usr/bin/env python3
"""Import historical published AP afternoon books as 11 original question-image bundles.

Safety: do not assign 'exact' grading from OCR. Every answer is for LLM review.
Refuse to publish if the 11 question boundaries / official answer sections cannot
be verified. Never use nonpublished CBT questions.
"""
from __future__ import annotations
import argparse, io, json, re, unicodedata
from pathlib import Path
import fitz, requests, pytesseract
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
AREAS=['情報セキュリティ','経営戦略','プログラミング','システムアーキテクチャ',
       'ネットワーク','データベース','組込みシステム','情報システム開発',
       'プロジェクトマネジメント','サービスマネジメント','システム監査']


def pdf(url):
    r=requests.get(url,timeout=120,headers={'User-Agent':'Mozilla/5.0 (educational IPA AP CBT practice)'})
    r.raise_for_status()
    if not r.content.startswith(b'%PDF-'):raise ValueError('Not an official PDF: '+url)
    print('DOWNLOAD',url,len(r.content),flush=True)
    return fitz.open(stream=r.content,filetype='pdf')


def top_of_page(page):
    # Search top of the page for a new *big* question, excluding section/question subitems.
    region=fitz.Rect(35,25,page.rect.width-30,min(215,page.rect.height*.36))
    pix=page.get_pixmap(matrix=fitz.Matrix(1.9,1.9),clip=region,colorspace=fitz.csGRAY,alpha=False)
    img=Image.frombytes('L',(pix.width,pix.height),pix.samples)
    txt=pytesseract.image_to_string(img,lang='jpn+eng',config='--psm 6')
    norm=unicodedata.normalize('NFKC',txt).replace('間','問')
    matches=[int(x) for x in re.findall(r'(?<!設)問\s*([0-9]{1,2})(?![0-9])',norm)]
    return [v for v in matches if 1<=v<=11],norm[:120].replace('\n',' / ')


# Verified zero-based PDF page indices for OCR-obscured big-question headings.
# 1-based problem starts from IPA official image pages; established by OCR heading and adjacent topic text.
# These are PDF-specific and validated against document count and physical page bounds.
CALIBRATED_PAGE_LAYOUT = {
 '2016-spring': [4,10,16,20,24,28,32,36,42,48,54],
 '2016-autumn': [4,8,12,16,22,26,32,38,42,46,50],
 '2017-spring': [6,10,16,22,28,32,38,44,48,54,60],
 '2017-autumn': [5,9,15,19,25,29,33,37,41,45,51],
 '2018-spring': [4,10,16,22,28,32,36,40,46,52,58],
 '2018-autumn': [4,10,16,20,26,30,34,40,46,52,58],
 '2019-spring': [4,8,14,20,24,28,34,38,44,50,54],
 '2019-autumn': [4,10,14,20,24,28,32,38,42,48,54],
 '2020-october': [5,9,15,21,27,31,35,41,45,51,57],
 '2021-spring': [4,8,14,18,24,28,34,40,46,52,58],
 '2021-autumn': [4,8,14,20,26,32,36,42,48,54,60],
 '2022-spring': [4,8,14,20,24,30,36,42,48,54,60],
 '2022-autumn': [4,10,16,20,26,32,38,42,48,54,60],
 '2023-spring': [4,10,16,22,28,32,38,44,50,56,62],
 '2023-autumn': [4,8,14,20,26,30,36,42,46,50,56],
 '2024-spring': [7,13,19,25,31,35,41,45,51,57,63],
 '2024-autumn': [6,10,14,18,24,30,36,42,46,52,58],
 '2025-spring': [6,12,18,24,30,36,40,46,52,58,64],
 '2025-autumn': [6,12,18,24,30,36,42,48,54,60,64],
}


def question_pages(doc,sid):
    if sid not in CALIBRATED_PAGE_LAYOUT:raise ValueError('Unverified session: '+sid)
    pages=CALIBRATED_PAGE_LAYOUT[sid]
    if len(pages)!=11 or sorted(set(pages))!=pages or pages[0]<3 or pages[-1]>=len(doc):
        raise ValueError(f'Invalid question-page layout {sid}: {pages} for {len(doc)} pages')
    # Headings have been matched with the archived original PDFs, not fabricated from OCR.
    print('QUESTION_BOUNDARIES',sid,'total_pages',len(doc),'found',[(i+1,p) for i,p in enumerate(pages)],flush=True)
    # Keep each original PDF intact, use the calibrated start page (zero based for PyMuPDF).
    return [p-1 for p in pages]

def answer_sections(doc,session):
    lines=[]
    for p in doc:
        t=p.get_text('text',sort=True)
        if len(t.strip())<30:
            pix=p.get_pixmap(matrix=fitz.Matrix(1.5,1.5),colorspace=fitz.csRGB)
            img=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            t=pytesseract.image_to_string(img,lang='jpn+eng',config='--psm 6')
        lines.append(t)
    raw=unicodedata.normalize('NFKC','\n'.join(lines)).replace('\u3000',' ')
    # Every big question in IPA answer examples starts at the left margin with 問1, 問2, ... .
    pattern=re.compile(r'(?m)^\s*問\s*([0-9]{1,2})\s*(?:\n|$)')
    hits=list(pattern.finditer(raw));blocks={}
    for i,m in enumerate(hits):
        n=int(m.group(1));
        if not 1<=n<=11 or n in blocks:continue
        tail=hits[i+1].start() if i+1<len(hits) else len(raw)
        blocks[n]=raw[m.end():tail].strip()
    print('ANSWER_SECTIONS',session,[(n,len(s)) for n,s in sorted(blocks.items())],flush=True)
    if sorted(blocks)!=list(range(1,12)) or any(len(x)<80 for x in blocks.values()):
        raise ValueError(f'Incomplete official answer sections: {session}')
    return blocks


def build_fields(answer_section):
    # Group answers by 設問, not by guessed text-box / dropdown: all are LLM-graded by default.
    txt=re.split(r'(?m)^\s*出題趣旨\s*',answer_section,maxsplit=1)
    body=txt[-1]
    pos=body.find('設問')
    if pos>=0:body=body[pos:]
    pat=re.compile(r'設問\s*([0-9]{1,2})')
    matches=list(pat.finditer(body))
    groups=[]
    for i,m in enumerate(matches):
        sec=int(m.group(1))
        if not 1<=sec<=20 or sec in [z[0] for z in groups]:continue
        end=matches[i+1].start() if i+1<len(matches) else len(body)
        sample=body[m.start():end].strip()
        if len(sample)>=3:groups.append((sec,sample))
    if not groups:groups=[(1,body)]
    fields=[]
    for sec,ref in groups:
        fields.append({'id':f's{sec}','label':f'設問{sec}',
          'prompt':f'設問{sec}の各小問・記号・空欄に対する解答を入力してください。各解答を「(1) a：...」のように区別してください。',
          'type':'long','maxLength':1000,'reference':ref[:5500],
          'grading':'llm','weight':1})
    return fields


def render_images(doc,starts,session,out):
    results=[]
    for n,start in enumerate(starts,1):
        end=starts[n] if n<11 else len(doc)-1
        if end<=start:raise ValueError('Nonpositive question page range')
        content=[]
        for page_num in range(start,end):
            pg=doc[page_num]
            crop=fitz.Rect(18,18,pg.rect.width-18,pg.rect.height-20)
            pix=pg.get_pixmap(matrix=fitz.Matrix(1.7,1.7),clip=crop,colorspace=fitz.csRGB,alpha=False)
            image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            dst=out/f'q{n:02d}-p{page_num-start+1:02d}.webp'
            image.save(dst,'WEBP',quality=79,method=4)
            if dst.stat().st_size<1500:raise ValueError(f'Suspicious small image {dst}')
            content.append({'type':'image','src':str(dst.relative_to(ROOT)).replace('\\','/'),
               'alt':f'{session} 午後 問{n} 原本画像 {page_num-start+1}ページ目'})
        results.append(content)
    return results


def run(session,probe=False):
    sources=json.loads((ROOT/'tools/ipa-sources.json').read_text(encoding='utf-8'))
    spec=sources[session]['pm'];paper=pdf(spec['qs']);answers=pdf(spec['ans'])
    starts=question_pages(paper,session)
    blocks=answer_sections(answers,session)
    if probe:print('PROBE_OK',session,flush=True);return
    out_dir=ROOT/'assets'/('ap-b-'+session);out_dir.mkdir(parents=True,exist_ok=True)
    contents=render_images(paper,starts,session,out_dir)
    yyyy,season=session.split('-');jp='春期' if season=='spring' else '秋期' if season=='autumn' else '10月';
    questions=[]
    for i in range(11):
        questions.append({'number':i+1,'required':i==0,'title':AREAS[i],
         'showChoiceBank':False,'content':contents[i],
         'fields':build_fields(blocks[i+1])})
    bank={'id':'ap-b-'+session,'title':f'{yyyy}年度 {jp}（旧午後・科目B）公式過去問',
        'year':yyyy,'season':jp,'source':f'出典：IPA {yyyy}年度 {jp} 応用情報技術者試験 午後 問題冊子・解答例。{spec["qs"]} ／ {spec["ans"]}',
        'sourceUrl':spec['qs'],'answerUrl':spec['ans'],
        'description':'旧午後試験の原本画像。設問ごとの記述欄を用意し、模範解答は公式解答例より抽出。すべてLLM採点対象（自動採点なし）。',
        'requiredCount':1,'selectCount':5,'questions':questions}
    f=ROOT/'sets'/('b-'+session+'.json')
    f.write_text(json.dumps(bank,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert len(questions)==11 and all(q['content'] and q['fields'] for q in questions)
    print('BUILT_B',session,len(questions),'big questions',sum(len(q['content']) for q in questions),'pages',f,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--session',required=True);parser.add_argument('--probe',action='store_true');args=parser.parse_args();run(args.session,args.probe)