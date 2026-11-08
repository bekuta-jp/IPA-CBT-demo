#!/usr/bin/env python3
"""Conservatively deskew existing official 2025 AP image-only question sets.

Never rotate more than 1.15 degrees; preserve white margins by expanding canvas.
"""
import json
from pathlib import Path
from PIL import Image
from import_ipa_bulk import auto_deskew

root = Path(__file__).resolve().parents[1]
for session in ('2025-spring','2025-autumn'):
    filepath=root/'sets'/('ap-'+session+'.json')
    data=json.loads(filepath.read_text(encoding='utf-8'))
    if len(data['questions'])!=80:raise RuntimeError(f'{session}: set is not 80 questions')
    count=0
    for q in data['questions']:
        src=root/q['image']
        with Image.open(src) as im:
            raw=im.convert('RGB')
        result,angle=auto_deskew(raw)
        if angle:
            result.save(src,'WEBP',quality=91,method=5)
            count+=1
        q['deskewDegrees']=angle
    filepath.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'DESKEW {session}: {count}/80 images rotated within +/-1.15 degrees',flush=True)