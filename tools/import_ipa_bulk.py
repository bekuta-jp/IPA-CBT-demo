#!/usr/bin/env python3
"""Import one verified official IPA AP morning PDF into a Github Pages JSON + WebP corpus.

The source examination paper is an image-scanned PDF. Source images are authoritative;
OCR text is best-effort and strictly for exported LLM review data. Fail closed when the
80-question segmentation cannot be verified. No questions/answers are invented.
"""
from __future__ import annotations
import argparse
import json
import math
import re
import statistics
import sys
from pathlib import Path
import unicodedata
import io

import cv2
import fitz
import numpy as np
import pytesseract
from pytesseract import Output
from PIL import Image, ImageChops
import requests

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = 'https://www.ipa.go.jp/shiken/mondai-kaiotu/'
SOURCES = {
 '2024-autumn': 'm42obm000000afqx-att/2024r06a_ap_am_',
 '2024-spring': 'm42obm000000afqx-att/2024r06h_ap_am_',
 '2023-autumn': 'ps6vr70000010d6y-att/2023r05a_ap_am_',
 '2023-spring': 'ps6vr70000010d6y-att/2023r05h_ap_am_',
 '2022-autumn': 'gmcbt80000008smf-att/2022r04a_ap_am_',
 '2022-spring': 'gmcbt80000009sgk-att/2022r04h_ap_am_',
 '2021-autumn': 'gmcbt8000000apad-att/2021r03a_ap_am_',
 '2021-spring': 'gmcbt8000000d5ru-att/2021r03h_ap_am_',
}
# 2022 spring answer table is image-scanned, so inspect the 80-key official image.
# This is a transcription of official PDF (20 items per column); other years are
# parsed from the official machine-readable PDF in the GitHub build itself.
MANUAL_ANSWERS = {
 '2022-spring': [
 'ア ア ウ ア ア エ エ エ イ エ イ ウ ア ア エ ウ イ ウ イ エ',
 'ウ ウ ウ ウ ア ウ ア ウ ア ア イ ウ イ ア エ エ ウ エ ア イ',
 'エ ウ イ ウ ウ エ イ ア エ ア エ ア ウ ア ウ エ イ ア イ ア',
 'ア エ イ ウ ア ア ウ ウ エ エ ウ ウ ア ウ イ エ エ ア ウ エ'
 ]
}


def get_pdf(url: str):
 r=requests.get(url,headers={'User-Agent':'Mozilla/5.0 (educational IPA past-question importer)'},timeout=120)
 r.raise_for_status()
 if not r.content.startswith(b'%PDF-'): raise ValueError('Non-PDF source '+url)
 print('FETCHED',url,len(r.content),flush=True)
 return fitz.open(stream=r.content,filetype='pdf')


def answer_key(doc, session):
 text='\n'.join(p.get_text('text',sort=True) for p in doc)
 matches=re.findall(r'問\s*([0-9]{1,2})\s*([アイウエ])',text)
 ans={int(n):v for n,v in matches if 1<=int(n)<=80}
 if session in MANUAL_ANSWERS and len(ans)<80:
  flat=' '.join(MANUAL_ANSWERS[session]).split()
  if len(flat)!=80:raise ValueError('Manual answer transcription not 80')
  ans=dict(enumerate(flat,1))
  print('Official answer sheet scanned: using verified 80-character transcription',flush=True)
 if sorted(ans)!=list(range(1,81)):
  raise ValueError(f'Official answer parse incomplete: {len(ans)}/80; missing {sorted(set(range(1,81))-set(ans))}')
 if not set(ans.values())<=set('アイウエ'):raise ValueError('Invalid answer label')
 print('OFFICIAL_ANSWERS',session,80,''.join(ans.values()),flush=True)
 return ans


def strip_ocr(page, page_index):
 # Question-number column, with some first characters clipped from OCR tokenization.
 rect=fitz.Rect(42,44,min(140,page.rect.width*.31),page.rect.height-48)
 scale=3.1
 pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=rect,colorspace=fitz.csGRAY,alpha=False)
 im=Image.frombytes('L',(pix.width,pix.height),pix.samples)
 raw=pytesseract.image_to_data(im,lang='jpn+eng',config='--psm 11',output_type=Output.DICT)
 out=[]
 for i,orig in enumerate(raw['text']):
  t=unicodedata.normalize('NFKC',orig).strip().replace(' ','')
  if not t:continue
  try:conf=float(raw['conf'][i])
  except (ValueError,TypeError):continue
  if conf<2:continue
  x=rect.x0+raw['left'][i]/scale
  y=rect.y0+raw['top'][i]/scale
  if x>105:continue
  out.append({'t':t,'x':round(x,1),'y':round(y,1),'w':round(raw['width'][i]/scale,1),'conf':conf})
 return out


def heading_candidates(tokens):
 # Tesseract may read 問 as 間, 閥, fa], fl2, F935, etc.
 candidates=[]
 for z in tokens:
  t=z['t'];x=z['x'];y=z['y']
  if x>75 or not 53<=y<=668:continue
  has_heading = bool(re.match(r'^(?:[問間閣閥闇闘]|fa[l1\]]|fl[0-9]|f[0-9]{1,2}|F[0-9]{1,2}|P[0-9]{1,2}|RIG|fis\]|F9|lli|t\d)',t))
  if not has_heading:continue
  num=None
  m=re.search(r'(?<!\d)(\d{1,2})(?!\d)',t)
  if m:num=int(m.group(1))
  if num is None:
   nearby=[v for v in tokens if v is not z and re.fullmatch(r'\d{1,2}',v['t']) and 0<=v['x']-x<=24 and abs(v['y']-y)<=8]
   if nearby:num=int(sorted(nearby,key=lambda v:abs(v['y']-y))[0]['t'])
  if num is not None and not 1<=num<=80:num=None
  candidates.append({'y':round(y-7,1),'number':num,'t':t,'conf':z['conf']})
 # top page header digit at left x<82 (問 was OCR'd as blanks)
 if not any(abs(z['y']-72)<26 for z in candidates):
  near=[z for z in tokens if z['x']<82 and 64<=z['y']<=96 and re.fullmatch(r'[0-9]{1,2}',z['t'])]
  if near:
   z=near[0];candidates.append({'y':round(z['y']-7,1),'number':int(z['t']),'t':'[lone header number]','conf':z['conf']})
 # dedup based on local line
 candidates.sort(key=lambda z:z['y'])
 keep=[]
 for z in candidates:
  if keep and abs(z['y']-keep[-1]['y'])<12:
   if (z['number'] is not None and keep[-1]['number'] is None) or z['conf']>keep[-1]['conf']+20:keep[-1]=z
  else:keep.append(z)
 return keep



# Positions of OCR-obscured question headers verified against the official
# scanned question pages and adjacent recognized question numbers.
# Entries use one-based PDF page numbers and crop start Y in PDF points.
CALIBRATED_MISSING = {
 '2021-spring':[(4,471),(5,187),(7,258)],
 '2021-autumn':[(7,287),(19,266)],
 '2022-spring':[(5,393),(12,251),(15,272)],
 '2022-autumn':[(6,71),(29,437)],
 '2023-spring':[(11,480),(13,329),(14,67),(16,265),(17,445)],
 '2023-autumn':[(11,333),(16,475),(23,275),(30,328)],
 '2024-spring':[(10,204),(16,70),(26,290),(35,249)],
 '2024-autumn':[(5,310),(8,73),(11,417)],
}

def find_positions(doc,session):
 candidates=[]; diagnostic=[]
 for pi in range(2,len(doc)-2):
  pg=doc[pi];tokens=strip_ocr(pg,pi);cand=heading_candidates(tokens)
  diagnostic.append({'page':pi+1,'height':pg.rect.height,'candidates':cand,'tokens':[(z['t'],z['x'],z['y']) for z in tokens if z['x']<=93]})
  for c in cand:candidates.append((pi,c['y'],c['number']))
 for one_based_page,y in CALIBRATED_MISSING.get(session,[]):
  p=one_based_page-1
  if any(pi==p and abs(yy-y)<12 for pi,yy,_ in candidates):raise ValueError(f'Calibrated position collides with OCR marker: {session} page={one_based_page} y={y}')
  candidates.append((p,float(y),None))
 candidates.sort(key=lambda z:(z[0],z[1]))
 print('POSITION_COUNTS',session,'pages',len(doc),'found',len(candidates),'expected 80',flush=True)
 for d in diagnostic:
  print('PAGE_DIAG',session,'page',d['page'],'candidates',[(round(v['y']),v['number'],v['t']) for v in d['candidates']],flush=True)
  print('TOKEN_DIAG',session,'page',d['page'],'tokens',d['tokens'][:85],flush=True)
 if len(candidates)!=80:
  # The matched labels are evidence for manual review; do not publish an
  # incomplete or missegmented question bank.
  raise ValueError(f'Marker count {len(candidates)}/80 in {session}; inspect PAGE_DIAG and calibrate this PDF.')
 # Require monotonic agreement when OCR actually recognizes the label.
 wrong=[]
 for n,(_,_,label) in enumerate(candidates,1):
  if label is not None and label!=n:wrong.append((n,label))
 print('LABEL_MISMATCHES',session,wrong,flush=True)
 if len(wrong)>5:
  raise ValueError(f'Question-number alignment uncertain: {wrong}')
 return [(p,y) for (p,y,_) in candidates]


def auto_deskew(img):
 # Estimate near-horizontal printed lines. Conservative: cap at +/- 1 degree.
 arr=np.asarray(img.convert('L'))
 if arr.shape[1]>1000:
  factor=1000/arr.shape[1];arr=cv2.resize(arr,None,fx=factor,fy=factor,interpolation=cv2.INTER_AREA)
 binary=np.uint8(arr<130)*255
 # long horizontal strokes are robust to Japanese glyph textures and diagrams.
 kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(14,1))
 joined=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,kernel)
 segments=cv2.HoughLinesP(joined,1,np.pi/1800,threshold=90,minLineLength=100,maxLineGap=9)
 angles=[]
 if segments is not None:
  for line in segments[:,0]:
   x1,y1,x2,y2=map(int,line)
   if x1==x2:continue
   a=math.degrees(math.atan2(y2-y1,x2-x1))
   if abs(a)<=1.6 and (x2-x1)**2+(y2-y1)**2>=120**2:angles.append(a)
 if len(angles)<4:return img,0.0
 angle=float(statistics.median(angles))
 if abs(angle)<.12 or abs(angle)>1.15:return img,0.0
 # PIL positive rotation counter-rotates downward-sloping OCR baselines.
 out=img.rotate(angle,resample=Image.Resampling.BICUBIC,expand=True,fillcolor='white')
 return out,round(angle,3)


def one_image(doc, marks, i, out_dir, session):
 page_num,y=marks[i];following=marks[i+1] if i+1<80 else None
 segments=[]
 for pi in range(page_num,(following[0] if following else page_num)+1):
  page=doc[pi]
  low=y if pi==page_num else 45
  high=(following[1]-5 if following and pi==following[0] else page.rect.height-49)
  if high-low<=15:continue
  left=38;right=page.rect.width-24
  rect=fitz.Rect(left,low,right,high)
  if rect.is_empty:continue
  pix=page.get_pixmap(matrix=fitz.Matrix(2.0,2.0),clip=rect,colorspace=fitz.csRGB,alpha=False)
  picture=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
  segments.append(picture)
 if not segments:raise ValueError('empty image for question '+str(i+1))
 width=max(x.width for x in segments);height=sum(x.height for x in segments)+12*(len(segments)-1)
 img=Image.new('RGB',(width,height),'white');y0=0
 for part in segments:img.paste(part,((width-part.width)//2,y0));y0+=part.height+12
 # Remove excessive bottom whitespace, retaining a >=24px margin.
 gray=img.convert('L')
 bounds=ImageChops.difference(gray,Image.new('L',gray.size,255)).point(lambda a:255 if a>22 else 0).getbbox()
 if bounds:img=img.crop((0,0,img.width,min(img.height,bounds[3]+24)))
 img,rot=auto_deskew(img)
 if img.width<220 or img.height<50:raise ValueError('invalid question size '+str(i+1))
 dest=out_dir/f'q{i+1:02d}.webp';img.save(dest,'WEBP',quality=88,method=5)
 # Best effort text for LLM, never displayed during the exam.
 small=img.copy();small.thumbnail((1200,1800))
 stem=pytesseract.image_to_string(small,lang='jpn+eng',config='--psm 6').strip()
 if len(stem)<6:stem=f'【問{i+1}】正確な問題文は添付の原本画像を参照してください。'
 return dest,stem,rot


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--session',required=True,choices=SOURCES.keys());ap.add_argument('--root',default=str(ROOT));args=ap.parse_args()
 session=args.session;root=Path(args.root);yy,season=session.split('-');jp='春期' if season=='spring' else '秋期';prefix=SOURCE_ROOT+SOURCES[session]
 qs=get_pdf(prefix+'qs.pdf');ansdoc=get_pdf(prefix+'ans.pdf');answers=answer_key(ansdoc,session)
 marks=find_positions(qs,session)
 dest=root/'assets'/('ap-'+session);dest.mkdir(parents=True,exist_ok=True)
 questions=[];rotations=[]
 for i in range(80):
  image,stem,angle=one_image(qs,marks,i,dest,session);rotations.append(angle)
  questions.append({'id':session+'-q'+str(i+1).zfill(2),'number':i+1,
   'topic':('テクノロジ系' if i<50 else 'マネジメント系' if i<60 else 'ストラテジ系'),
   'stem':stem,'image':'assets/ap-'+session+'/q'+str(i+1).zfill(2)+'.webp','imageOnly':True,
   'options':['原本画像内の選択肢ア','原本画像内の選択肢イ','原本画像内の選択肢ウ','原本画像内の選択肢エ'],
   'answer':answers[i+1],'explanation':'',
   'source':f'出典：IPA {yy}年度 {jp} 応用情報技術者試験 午前 問{i+1} {prefix}qs.pdf',
   'modified':True,'modificationNote':'公式公開問題の原本ページから問題単位に切り出し、傾き補正を施した画像です。復習用OCR文は参考情報であり、画像原本を正とします。',
   'deskewDegrees':angle})
 year_reiwa=int(yy)-2018
 data={'id':'ap-'+session,'title':f'{yy}年度 {jp}（令和{year_reiwa}年度）応用情報 午前［公式問題画像］',
       'year':int(yy),'season':jp,'sourceType':'ipa','exam':'AP',
       'sourceUrl':prefix+'qs.pdf','answerUrl':prefix+'ans.pdf','imageOnly':True,
       'questions':questions}
 out=root/'sets'/('ap-'+session+'.json');out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 if len(questions)!=80 or len(list(dest.glob('q*.webp')))!=80:raise ValueError('80/80 failed')
 print('BUILT',session,'80 JSON',out,'80 images; rotated',sum(bool(n) for n in rotations),
       'size',sum(p.stat().st_size for p in dest.glob('q*.webp')),flush=True)

if __name__=='__main__':main()