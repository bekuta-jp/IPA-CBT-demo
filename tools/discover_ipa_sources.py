#!/usr/bin/env python3
"""Discover original IPA AP paper and answer PDF URLs, never substitute unofficial mirrors."""
from __future__ import annotations
import json,re,sys
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
ROOT='https://www.ipa.go.jp/shiken/mondai-kaiotu/'
S=requests.Session();S.headers.update({'User-Agent':'Mozilla/5.0 (AP-CBT educational past questions)'})

def get(url):
    r=S.get(url,timeout=90);r.raise_for_status();return BeautifulSoup(r.text,'html.parser')

def discover():
    index=get(ROOT+'index.html')
    byyear={}
    for a in index.select('a[href]'):
        title=a.get_text(' ',strip=True)
        m=re.search(r'\((20\d\d)年度|（(20\d\d)年度',title)
        if m:
            year=int(m.group(1) or m.group(2))
            if year in range(2016,2026):byyear[year]=urljoin(ROOT,a['href'])
    print('YEAR_PAGES',json.dumps(byyear,ensure_ascii=False),flush=True)
    sessions={}
    for year in range(2016,2026):
        if year not in byyear:raise ValueError(f'IPA year listing missing {year}')
        soup=get(byyear[year])
        for a in soup.select('a[href]'):
            url=urljoin(byyear[year],a['href'])
            mo=re.search(r'/(' + str(year) + r'[a-zA-Z0-9]+)_ap_(am|pm)_(qs|ans)\.pdf$',url)
            if not mo:continue
            identifier,part,typ=mo.groups()
            season='spring' if identifier[-1].lower()=='h' else 'autumn'
            if year==2020:season='october'
            key=f'{year}-{season}'
            sessions.setdefault(key,{}).setdefault(part,{})[typ]=url
        print('YEAR',year,'SESSIONS',[(k,v) for k,v in sessions.items() if k.startswith(str(year))],flush=True)
    expected=[f'{y}-{s}' for y in range(2016,2026) for s in (('october',) if y==2020 else ('spring','autumn'))]
    for key in expected:
        for part in ('am','pm'):
            for typ in ('qs','ans'):
                if not sessions.get(key,{}).get(part,{}).get(typ):raise ValueError(f'Missing official {key} {part} {typ}')
    if len(sessions)!=19:raise ValueError(f'Unexpected AP session count: {len(sessions)}')
    return sessions

if __name__=='__main__':
    d=discover();print('COMPLETE_SESSIONS',len(d),flush=True)
    from pathlib import Path
    p=Path('tools/ipa-sources.json');p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')