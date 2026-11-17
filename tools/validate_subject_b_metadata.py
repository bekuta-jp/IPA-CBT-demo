#!/usr/bin/env python3
"""Validate official Subject B answer metadata as a separate overlay."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
b=json.loads((root/'sets/b-2025-spring.json').read_text(encoding='utf8'))
m=json.loads((root/'sets/b-meta-2025-spring.json').read_text(encoding='utf8'))
index=json.loads((root/'sets/b-index.json').read_text(encoding='utf8'))
assert m['schemaVersion']=='ap-b-field-meta-v1'
assert m['setId']==b['id']
assert next(x['metadataFile'] for x in index if x['id']==b['id'])=='sets/b-meta-2025-spring.json'
assert set(m['questions'])=={str(i) for i in range(1,12)}
count=0
exact=0
for q in b['questions']:
    spec=m['questions'][str(q['number'])]
    parents={f['id'] for f in q['fields']}
    assert set(spec['completeGroups'])<=parents
    fieldids=set()
    for f in spec['fields']:
        count+=1
        assert f['id'] not in fieldids
        fieldids.add(f['id'])
        assert f['parent'] in spec['completeGroups']
        assert f['type'] in {'single','multi','dropdown','word','short','long'}
        assert f['reference'].strip()
        assert f['prompt'].strip()
        assert f['grading'] in {'exact','llm'}
        if f['type'] in {'single','multi','dropdown'}:
            assert len(f['options'])>=2
        if f['grading']=='exact':
            exact+=1
            assert f['verified'] is True and f['type'] in {'single','multi','dropdown','word'}
            assert f['correct']
            if f.get('options'):
                assert all(v in f['options'] for v in f['correct'])
        if f.get('maxLengthVerified'):
            assert f.get('maxLength') and len(f['reference'])<=f['maxLength']
assert count==94 and exact==30,(count,exact)
assert 's3' not in m['questions']['11']['completeGroups'], 'generic fallback test must remain'
print(f'PASS: 2025 spring official answer metadata: {count} fields, {exact} exact, intentional generic fallback')
