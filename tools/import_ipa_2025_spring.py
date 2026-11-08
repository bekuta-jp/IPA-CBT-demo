#!/usr/bin/env python3
"""IPA 令和7年度春期・応用情報 午前：公式PDFから画像付きの80問セットを生成。

問題・選択肢は原本ページの問題領域を切り出した画像で提示。
PDFテキストは復習データのために補助的に収録（記号等は画像が正）。

GitHub Actionsでの実行を想定。source PDF はリポジトリへ収録しない。
"""
from __future__ import annotations
import io
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytesseract
from pytesseract import Output
from PIL import Image, ImageChops
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'sets' / 'ap-2025-spring.json'
ASSET_DIR = ROOT / 'assets' / 'ap-2025-spring'
MANIFEST = ROOT / 'sets' / 'index.json'
QS_URL = 'https://www.ipa.go.jp/shiken/mondai-kaiotu/nl10bi0000009lh8-att/2025r07h_ap_am_qs.pdf'
ANS_URL = 'https://www.ipa.go.jp/shiken/mondai-kaiotu/nl10bi0000009lh8-att/2025r07h_ap_am_ans.pdf'
SOURCE = '出典：独立行政法人情報処理推進機構（IPA） 令和7年度 春期 応用情報技術者試験 午前'

# 公開された IPA 解答例と照合済み。取得した解答PDFも別途検査する。
ANSWER_SETS = [
    'エ ア イ イ ウ ウ ウ ウ エ ア エ イ エ イ ウ ア エ ウ イ イ',
    'ウ ウ ウ エ ウ イ ア イ イ イ エ ウ ア ウ ウ イ イ ウ ウ イ',
    'イ イ ウ ウ ア ア イ エ ウ イ エ イ エ ウ イ ウ ア ウ ウ ア',
    'イ ア エ ウ ア イ ウ ア ウ ウ イ エ ウ エ ウ エ ウ イ イ エ',
]
ANSWERS = [a for group in ANSWER_SETS for a in group.split()]
assert len(ANSWERS) == 80
FIELDS = ['テクノロジ系']*50 + ['マネジメント系']*10 + ['ストラテジ系']*20

@dataclass
class Mark:
    number: int
    page: int
    y: float


def fetch_pdf(url: str) -> fitz.Document:
    response = requests.get(url, timeout=120, headers={'User-Agent':'Mozilla/5.0 (compatible; Educational-CBT-Importer/1.0)'})
    response.raise_for_status()
    if not response.content.startswith(b'%PDF-'):
        raise RuntimeError(f'IPA PDFの取得結果がPDFではありません: {url}, {response.status_code}, {len(response.content)}')
    print('Fetched official PDF', url.rsplit('/',1)[-1], len(response.content), 'bytes')
    return fitz.open(stream=response.content, filetype='pdf')


def ocr_markers(page: fitz.Page, page_index: int) -> tuple[list[Mark], list[tuple[str, int, int]]]:
    """Locate 問N in image-only IPA PDFs, using OCR only on the left question-number strip."""
    region = fitz.Rect(46, 38, min(page.rect.width * .29, 174), page.rect.height - 47)
    scale = 3.1
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=region,
                          colorspace=fitz.csGRAY, alpha=False)
    im = Image.frombytes('L', (pix.width,pix.height), pix.samples)
    result = pytesseract.image_to_data(im,lang='jpn+eng',config='--psm 11',output_type=Output.DICT)
    tokens=[]
    for i,raw in enumerate(result['text']):
        t=unicodedata.normalize('NFKC', raw).strip()
        if not t:continue
        try: conf=float(result['conf'][i])
        except (ValueError,TypeError):conf=-1
        if conf<5:continue
        x=int(result['left'][i]); y=int(result['top'][i]); w=int(result['width'][i]); h=int(result['height'][i])
        tokens.append((t,x,y,w,h,conf))
    # Most digits in ordinary text are to the right of the 問 column; locate the 問 glyph first.
    anchors=[]
    for i,(t,x,y,w,h,conf) in enumerate(tokens):
        key=t.replace(' ', '').replace('　','')
        full=re.match(r'^[問間閣闇](?:第)?(\d{1,2})(?!\d)',key)
        if full:
            n=int(full.group(1))
            if 1<=n<=80 and x/scale+region.x0<page.rect.width*.19:
                anchors.append(Mark(n,page_index,max(0,(y/scale+region.y0)-7)))
            continue
        if re.fullmatch(r'[問間閣闇]',key):
            for t2,x2,y2,w2,h2,conf2 in tokens:
                if not re.fullmatch(r'\d{1,2}',t2):continue
                if x2>=x+w-5 and x2<=x+w+34 and abs(y2-y)<max(h,h2):
                    n=int(t2)
                    if 1<=n<=80 and x/scale+region.x0<page.rect.width*.19:
                        anchors.append(Mark(n,page_index,max(0,y/scale+region.y0-7)))
    brief=[(t,round(x/scale+region.x0),round(y/scale+region.y0)) for (t,x,y,w,h,c) in tokens if (x/scale+region.x0)<page.rect.width*.18]
    return anchors,brief


# 2025r07h_ap_am_qs.pdf, 44-page public PDF. Question positions were measured
# on the original PDF's left margin. The file is image-only, so PyMuPDF cannot
# extract its 問N labels as text. OCR also misreads some labels (50 -> 59 etc.).
# Key = 1-based PDF page number; values = calibrated crop starting Y (PDF pt).
# IMPORTANT: This geometry is specific to this one official source PDF.
CALIBRATED_LAYOUT = {
    4:[65,275], 5:[70,250,431], 6:[66], 7:[71,251,496],
    8:[66,268], 9:[72], 10:[71,567], 11:[74,274],
    12:[68,188,328,488], 13:[72,459], 14:[65,205], 15:[72,499],
    16:[67,527], 17:[73,193,394], 18:[66,266,386], 19:[73],
    20:[69,442], 21:[72,253,474], 22:[66,286], 23:[73,313],
    24:[67,247,467], 25:[75,195,415], 26:[67], 27:[72,512],
    28:[65], 29:[72], 30:[64,450], 31:[73,273,433],
    32:[67,267,427], 33:[74,455], 34:[67,355,475], 35:[71],
    36:[65,285], 37:[73,293], 38:[65,325], 39:[71,377],
    40:[66,326], 41:[71],
}


def find_markers(doc: fitz.Document) -> list[Mark]:
    # Never silently apply these coordinates to a revised/reflowed PDF.
    if len(doc) != 44:
        raise RuntimeError(f'公式問題冊子のページ数が変更されました（{len(doc)}頁）。再調査が必要です。')
    if sum(len(ys) for ys in CALIBRATED_LAYOUT.values()) != 80:
        raise RuntimeError('固定問題位置テーブルが80問になっていません。')
    markers=[]
    for page_num,positions in CALIBRATED_LAYOUT.items():
        page=doc[page_num-1]
        if not 550 <= page.rect.width <= 700 or not 780 <= page.rect.height <= 900:
            raise RuntimeError(f'問題冊子のページ{page_num}のサイズが想定と異なります: {page.rect}')
        for y in positions:
            if y<40 or y>page.rect.height-65:
                raise RuntimeError(f'問題位置がページ外です: page={page_num}, y={y}')
            markers.append(Mark(len(markers)+1,page_num-1,float(y)))
    print('Official 2025 spring layout: 80 calibrated question regions',
          'first=',markers[0],'last=',markers[-1],flush=True)
    return markers

def page_segments(doc:fitz.Document,markers:list[Mark],i:int):
    first=markers[i]
    following=markers[i+1] if i+1<len(markers) else None
    last_page=following.page if following is not None else first.page
    for p in range(first.page,last_page+1):
        page=doc[p]
        y0=first.y if p==first.page else 49
        y1=(following.y-5 if following and p==following.page else page.rect.height-51)
        # no portion on the next page if the next question begins at the top
        if y1-y0<12:continue
        yield p,fitz.Rect(58,y0,page.rect.width-43,y1)
        if following and p==following.page:break


def convert_question(doc:fitz.Document,markers:list[Mark],i:int):
    images=[]
    extracted=[]
    for p,rect in page_segments(doc,markers,i):
        page=doc[p]
        extracted.append(page.get_text('text',sort=True,clip=rect).strip())
        pix=page.get_pixmap(matrix=fitz.Matrix(2.1,2.1),clip=rect,colorspace=fitz.csRGB,alpha=False)
        im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        # trim excessive white bottom only, preserve diagram strokes and all text.
        gray=im.convert('L')
        bounds=ImageChops.difference(gray,Image.new('L',gray.size,255)).point(lambda a:255 if a>13 else 0).getbbox()
        if bounds:
            im=im.crop((0,0,im.width,min(im.height,bounds[3]+24)))
        images.append(im)
    if not images:raise RuntimeError(f'問{i+1}の画像が空です')
    width=max(im.width for im in images)
    height=sum(im.height for im in images)+14*(len(images)-1)
    out=Image.new('RGB',(width,height),'white')
    at=0
    for im in images:
        out.paste(im,((width-im.width)//2,at));at+=im.height+14
    filename=f'q{i+1:02d}.webp'
    path=ASSET_DIR/filename
    out.save(path,'WEBP',quality=88,method=5)
    if out.width<200 or out.height<60:
        raise RuntimeError(f'問{i+1}の画像が異常なサイズです: {out.size}')
    text='\n'.join([t for t in extracted if t]).strip()
    text=re.sub(r'\n{3,}','\n\n',text)
    if len(text)<8:
        # IPA public question PDF can be image-only. OCR text is only for LLM review,
        # not the authoritative exam display; the original screenshot remains primary.
        preview=out.copy()
        preview.thumbnail((1300,3000))
        text=pytesseract.image_to_string(preview,lang='jpn+eng',config='--psm 6').strip()
        if len(text)<8:
            print(f'WARNING: question {i+1} OCR text unavailable; image-only',flush=True)
            text=f'【問{i+1}：原本画像をご参照ください。文字抽出ができませんでした。】' 
    return {
        'id':f'r07h-q{i+1:02d}','number':i+1,
        'topic':FIELDS[i],
        'stem':text, # 復習/LLM出力用の抽出文字列。試験中は表示せず原本画像を表示。
        'image':f'assets/ap-2025-spring/{filename}',
        'imageOnly':True,
        'options':['原本画像内の選択肢ア','原本画像内の選択肢イ','原本画像内の選択肢ウ','原本画像内の選択肢エ'],
        'answer':ANSWERS[i],
        'explanation':'',
        'source':f'{SOURCE} 問{i+1}。{QS_URL}',
        'modified':True,
        'modificationNote':'問題冊子から問ごとの画像を切り出し。画像内の選択肢は原順固定。復習用テキストはPDF抽出またはOCRによる参考データであり、数式・図表・文字の誤読を含む場合があるため原本画像を正とします。'
    }


def cross_check_official_answer_pdf(doc:fitz.Document):
    text='\n'.join(p.get_text('text',sort=True) for p in doc)
    # 文字抽出の並びは PDF の段組に依存するため、検出できたときのみ解答照合に使う。
    pat=re.compile(r'問\s*(\d{1,2})\s*([アイウエ])(?:\s|$)')
    found={int(n):v for n,v in pat.findall(text)}
    mismatches=[(n,v,ANSWERS[n-1]) for n,v in found.items() if 1<=n<=80 and v!=ANSWERS[n-1]]
    if mismatches:raise RuntimeError('公式解答PDFとの不一致: '+str(mismatches))
    print('Answer PDF text cross-check:',len(found),'entries available')
    if len(found)<20:
        # PDF の表の抽出順によっては自動確認できない。CI の健全性条件として停止。
        raise RuntimeError(f'公式解答の照合件数不足（{len(found)}件）')


def main():
    ASSET_DIR.mkdir(parents=True,exist_ok=True)
    qs=fetch_pdf(QS_URL)
    ans=fetch_pdf(ANS_URL)
    cross_check_official_answer_pdf(ans)
    markers=find_markers(qs)
    questions=[convert_question(qs,markers,i) for i in range(80)]
    data={
      'id':'ap-2025-spring',
      'title':'2025年度 春期（令和7年度）応用情報 午前［公式問題画像］',
      'year':2025,'season':'春期','sourceType':'ipa','exam':'AP',
      'source':SOURCE,'sourceUrl':QS_URL,'answerUrl':ANS_URL,
      'imageOnly':True,
      'notes':'IPA問題冊子の各問を画像で掲載。選択肢順は原順固定。公式解答で採点。',
      'questions':questions,
    }
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8')) if MANIFEST.exists() else []
    manifest=[x for x in manifest if x.get('id')!='ap-2025-spring']
    manifest.append({'id':'ap-2025-spring','title':data['title'],'year':2025,'season':'春期','sourceType':'ipa','count':80,'file':'sets/ap-2025-spring.json'})
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Output:',OUT,'images:',len(list(ASSET_DIR.glob('q*.webp'))))
    print('Question text lengths:',[(i+1,len(q['stem'])) for i,q in enumerate(questions) if len(q['stem'])<40])
    print('Total bytes:',sum(p.stat().st_size for p in ASSET_DIR.glob('q*.webp')))

if __name__=='__main__':main()