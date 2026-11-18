#!/usr/bin/env python3
"""Produce *provisional* per-subquestion answer boxes for historical AP afternoon books.

Inputs: IPA published answer-example transcriptions already stored under sets/b-*.json.
Never infer unverified choice arity, input limit, accepted answer or auto-grading.
Retain full original answer-example group in sourceQuestion fields (b.js sidecar loader).
Existing manually verified 2025-spring metadata is deliberately not overwritten.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
META_VERSION = "ap-b-field-meta-v1"
CHOICE = set("アイウエオカキクケコサシスセソタチツテト")


def clean_reference(reference: str) -> str:
    text = unicodedata.normalize("NFKC", str(reference or "")).replace("\r\n", "\n")
    text = text.replace("\u3000", " ")
    # PDF page-number/footer material sometimes spills into a reference field.
    text = re.split(r"\n\s*\d+\s*/\s*\d+\s*\n", text, maxsplit=1)[0]
    text = re.split(r"\n\s*©\s*20\d\d", text, maxsplit=1)[0]
    return text.strip()


def split_numbered(text: str) -> list[tuple[str, str]]:
    """Subdivide an official answer group by leading (1), (2), etc. only."""
    matches = list(re.finditer(r"(?m)(?:^|\n)[ \t]*\([ \t]*(\d{1,2})[ \t]*\)[ \t]*", text))
    if not matches:
        return [("", text.strip())]
    result: list[tuple[str,str]] = []
    prefix = text[:matches[0].start()].strip()
    if prefix:
        # Prefix before first numbered part can itself be a valid answer.
        result.append(("", prefix))
    for i, m in enumerate(matches):
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        if body:
            result.append((f"({m.group(1)})", body))
    return result


def split_labeled(text: str) -> list[tuple[str,str]]:
    """Extract left-column blank labels (a,b,.. / ア,イ,..) while keeping multiline answers.

    Single-letter patterns must be followed by whitespace to avoid treating text as a label.
    Long table/wording explanations remain as one answer if uncertain.
    """
    first_label = r"[a-zA-Z]|[アイウエオカキクケコサシスセソタチツテト]"
    pat = re.compile(r"(?m)(?:^|\n)[ \t]*(" + first_label + r")[ \t]{1,}(?=\S)")
    found = list(pat.finditer(text))
    if not found:
        return [("", text.strip())]
    result: list[tuple[str,str]] = []
    prefix = text[:found[0].start()].strip()
    if prefix:
        result.append(("", prefix))
    for i,m in enumerate(found):
        end = found[i+1].start() if i+1<len(found) else len(text)
        content=text[m.end():end].strip()
        if content:
            result.append((m.group(1),content))
    return result if result else [("",text.strip())]


def split_ordinal_rows(text: str) -> list[tuple[str,str]]:
    """A rare table-like key with 1 / 2 / 3 at line starts."""
    pat=re.compile(r"(?m)(?:^|\n)[ \t]*(\d{1,2})[ \t]{1,}(?=\S)")
    found=list(pat.finditer(text))
    if len(found)<2:
        return [("",text.strip())]
    numbers=[int(m.group(1)) for m in found]
    if numbers != list(range(1,len(numbers)+1)) or len(numbers)>12:
        return [("",text.strip())]
    result=[]
    prefix=text[:found[0].start()].strip()
    if prefix:result.append(("",prefix))
    for i,m in enumerate(found):
        end=found[i+1].start() if i+1<len(found) else len(text)
        value=text[m.end():end].strip()
        if value: result.append((m.group(1),value))
    return result


def segments(reference: str, parent_id: str) -> list[dict]:
    raw=clean_reference(reference)
    # The pre-existing source groups include the header 設問N.
    header=re.match(r"^設問\s*([0-9]{1,2})\s*",raw)
    if not header or f"s{header.group(1)}"!=parent_id:
        return []
    body=raw[header.end():].strip()
    if not body or len(body)>2600:
        return []
    collected=[]
    for numbered, chunk in split_numbered(body):
        subparts=split_labeled(chunk)
        for label, content in subparts:
            if not label:
                for numeric,value in split_ordinal_rows(content):
                    if value: collected.append((" ".join(x for x in [numbered,numeric] if x),value))
            elif content:
                collected.append((" ".join(x for x in [numbered,label] if x),content))
    if not collected or len(collected)>24:
        return []
    if any(not value.strip() or len(value)>1000 for _,value in collected):
        return []
    if len(set(label for label,_ in collected if label))!=len([label for label,_ in collected if label]):
        # Avoid duplicated label collisions due to OCR or malformed tables.
        return []
    return [dict(label=label.strip(),reference=value.strip()) for label,value in collected]


def infer_entry(label: str, reference: str) -> tuple[str,str]:
    """A presentation hint only; *never* a verified exam input format."""
    flat=re.sub(r"\s+"," ",reference).strip()
    if len(flat)==1 and flat in CHOICE:
        return 'word','choice_symbol_candidate'
    if re.fullmatch(r"[アイウエオカキクケコサシスセソタチツテト](\s*[,、，・]\s*[アイウエオカキクケコサシスセソタチツテト])+",flat):
        return 'short','multiple_choice_symbols_candidate'
    if len(flat)<=22 and '\n' not in reference and not re.search(r'[。！？]',flat):
        return 'word','short_entry_candidate'
    if len(flat)<=60 and '\n' not in reference:
        return 'short','one_line_text_candidate'
    return 'long','free_text_candidate'


def build_sidecar(doc:dict) -> dict:
    if not doc.get('id','').startswith('ap-b-') or len(doc.get('questions',[]))!=11:
        raise ValueError('Unexpected official B paper structure: '+str(doc.get('id')))
    out={
      'schemaVersion': META_VERSION,
      'setId':doc['id'],
      'revision':'automated-provisional-2026-11',
      'reviewStatus':'unverified',
      'title':doc['title']+'・設問／小問別解答欄（自動仮分類）',
      'sourceAnswerUrl':doc.get('answerUrl',''),
      'notes': 'IPA公式解答例に記載の設問・空欄ラベルを分割した暫定構造です。解答欄種別は参考表示であり、公式CBTの入力方法／選択肢数／文字数制限は未確認です。全設問LLM採点、機械採点なし。自動抽出の区切りが不明な設問は汎用の解答欄に戻ります。',
      'questions':{},
    }
    for question in doc['questions']:
        groups=[]
        complete=[]
        for parent in question['fields']:
            chunks=segments(parent.get('reference',''),parent['id'])
            if not chunks:
                continue
            complete.append(parent['id'])
            for i,entry in enumerate(chunks,1):
                form,candidate=infer_entry(entry['label'],entry['reference'])
                sublabel=' '+entry['label'] if entry['label'] else ''
                fieldspec={
                  'parent': parent['id'],
                  'id':f"{parent['id']}-{i}",
                  'label':parent.get('label',parent['id'])+sublabel,
                  'prompt':'原本の「'+parent.get('label',parent['id'])+sublabel+'」に対応する解答を入力してください。',
                  'type':form,
                  'formatCandidate':candidate,
                  'verified':False,
                  'grading':'llm',
                  'maxLengthVerified':False,
                  'allowedChars':'any',
                  'reference':entry['reference'],
                }
                groups.append(fieldspec)
        out['questions'][str(question['number'])]={'completeGroups':complete,'fields':groups}
    return out


def sessions():
    # 2020 spring was cancelled. Keep 2025 spring's hand-reviewed pilot sidecar intact.
    return [f'{y}-{part}' for y in range(2016,2026) for part in (('october',) if y==2020 else ('spring','autumn')) if not (y==2025 and part=='spring')]


def generate(root:Path)->dict:
    indexfile=root/'sets'/'b-index.json'
    index=json.loads(indexfile.read_text(encoding='utf-8'))
    byid={x['id']:x for x in index}
    expected=sessions()
    if len(expected)!=18 or len(index)!=19:
        raise ValueError(f'Unexpected index/session size {len(expected)}/{len(index)}')
    totals={'sessions':0,'questions':0,'originalGroups':0,'splitFields':0,'fallbackGroups':0,'autoGraded':0}
    for ss in expected:
        id=f'ap-b-{ss}'
        if id not in byid:raise ValueError('Missing session in catalog '+id)
        entry=byid[id]
        data=json.loads((root/entry['file']).read_text(encoding='utf-8'))
        result=build_sidecar(data)
        dest=root/'sets'/f'b-meta-{ss}.json'
        dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        # Validate every group either has a safely split answer field or falls back.
        for q in data['questions']:
            m=result['questions'].get(str(q['number']))
            if m is None:raise ValueError('Missing big-question metadata')
            known={f['id'] for f in q['fields']}
            if not set(m['completeGroups']) <= known:raise ValueError('Unknown parent')
            labels=set()
            for f in m['fields']:
                if f['parent'] not in known or f['id'] in labels or f.get('grading')!='llm' or f['verified'] is not False:
                    raise ValueError('Metadata integrity error '+ss)
                labels.add(f['id'])
            for group in m['completeGroups']:
                if not any(f['parent']==group for f in m['fields']):raise ValueError('Empty completed group')
            totals['originalGroups']+=len(q['fields'])
            totals['splitFields']+=len(m['fields'])
            totals['fallbackGroups']+=len(q['fields'])-len(m['completeGroups'])
        entry['metadataFile']='sets/b-meta-'+ss+'.json'
        totals['sessions']+=1
        totals['questions']+=len(data['questions'])
        print('GENERATED',id,'entries',sum(len(q['fields']) for q in result['questions'].values()),
            'fallback',sum(len(q['fields']) for q in data['questions'])-sum(len(q['completeGroups']) for q in result['questions'].values()),flush=True)
    if byid['ap-b-2025-spring'].get('metadataFile')!='sets/b-meta-2025-spring.json':
        raise ValueError('Must preserve existing verified 2025 spring pilot')
    indexfile.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('TOTALS',json.dumps(totals,ensure_ascii=False),flush=True)
    return totals

if __name__=='__main__':
    stats=generate(ROOT)
    assert stats['sessions']==18 and stats['questions']==198 and stats['autoGraded']==0