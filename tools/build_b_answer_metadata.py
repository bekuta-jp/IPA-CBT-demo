#!/usr/bin/env python3
"""Build *provisional* per-subquestion input metadata from IPA published answer examples.

Only the official archived answer-example text already stored in sets/b-*.json is used.
Source question scans and exact-correct-answer flags are deliberately untouched.
A split answer is never treated as a verified CBT input type or a verified length.
All generated answers remain LLM-graded until separately compared to the problem PDF.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_VER = 'ap-b-field-meta-v1'
PARSER_VER = 'answer-example-subquestion-parser-v1'
ALL_SESSIONS = [
    f'{year}-{season}'
    for year in range(2016, 2026)
    for season in (('october',) if year == 2020 else ('spring', 'autumn'))
]

FOOTER = re.compile(r'\n\s*\d{1,2}\s*/\s*\d{1,2}\s*\n\s*©\s*\d{4}[^\n]*', re.IGNORECASE)
QUESTION_HEADER = re.compile(r'^\s*設問\s*[0-9０-９]{1,2}[ \t\u3000]*')
TOP_MARKER = re.compile(r'^\s*(\(\s*[0-9０-９]{1,2}\s*\))\s*(.*)$')
ALPHA_MARKER = re.compile(r'^\s*([a-zａ-ｚ])\s{1,}(.+)$')
KANA_MARKER = re.compile(r'^\s*([ア-ン])\s{1,}(.+)$')
NUMBER_MARKER = re.compile(r'^\s*([0-9０-９]{1,2})\s+(・.*)$')
NAMED_MARKER = re.compile(r'^\s*(設定項目|理由|名称|条件|対象|項目|値|内容|要因|対応策|実施内容|説明|施策)\s+(.+)$')


def compact_source(raw: str) -> str:
    raw = FOOTER.sub('', raw or '').strip()
    raw = QUESTION_HEADER.sub('', raw, count=1)
    return raw.strip()


def nested(text: str):
    for pat in (ALPHA_MARKER, KANA_MARKER, NUMBER_MARKER, NAMED_MARKER):
        m = pat.match(text)
        if m:
            return m.group(1).strip(), m.group(2).strip()
    return None


def segments(raw: str) -> list[tuple[str, str]]:
    """Split when answer-example headings are explicit; continuation lines stay intact."""
    text = compact_source(raw)
    if not text:
        return []
    parts: list[list[str]] = []
    current_section = ''
    for line in text.splitlines():
        if not line.strip():
            if parts and parts[-1][1]:
                parts[-1][1] += '\n'
            continue
        mark = TOP_MARKER.match(line)
        if mark:
            current_section = re.sub(r'\s+', '', mark.group(1))
            tail = mark.group(2).strip()
            sub = nested(tail)
            if sub:
                label, answer = f'{current_section} {sub[0]}', sub[1]
            else:
                label, answer = current_section, tail
            if answer:
                parts.append([label, answer])
            else:
                parts.append([label, ''])
            continue
        sub = nested(line)
        if sub:
            label = ((current_section + ' ') if current_section else '') + sub[0]
            if sub[1]:
                parts.append([label, sub[1]])
                continue
        if not parts:
            parts.append(['', line.strip()])
        else:
            parts[-1][1] += '\n' + line.strip()

    kept: list[tuple[str, str]] = []
    for label, answer in parts:
        answer = answer.strip()
        if answer:
            kept.append((label, answer))
        elif kept:
            # Heading without an answer is not enough evidence to create its own field.
            kept[-1] = (kept[-1][0], kept[-1][1] + '\n' + label)
    if not kept:
        return [('', text)]
    return kept


def input_type(value: str) -> str:
    """Provisional layout hint only; does not imply a confirmed CBT input control."""
    value = value.strip()
    if '\n' in value or len(value) > 95:
        return 'long'
    if len(value) <= 25 and not re.search(r'[。！？\n]', value):
        # Short codes, kana answer letters and terms should fit in one line.
        return 'word'
    return 'short'


def create_sidecar(bank: dict) -> dict:
    result = {
        'schemaVersion': SOURCE_VER,
        'setId': bank['id'],
        'revision': '2026-11-provisional-v1',
        'title': bank['title'] + '：小問単位の暫定入力欄',
        'extractionMethod': PARSER_VER,
        'reviewStatus': 'unverified',
        'note': (
            'IPA公表解答例の設問番号・空欄記号を手掛かりに自動分割した暫定入力欄。'
            '原本問題画像との設問・入力形式・文字数制限の人手照合は未完了。'
            '自動採点は行わず、LLMで評価する。分割できない設問は汎用欄を維持。'
        ),
        'sources': {'question': bank.get('sourceUrl'), 'answer': bank.get('answerUrl')},
        'questions': {},
    }
    for question in bank['questions']:
        groups, fields = [], []
        for parent in question['fields']:
            reference = parent.get('reference', '')
            if not reference.strip():
                continue  # no spec, so the UI leaves the full generic box
            parts = segments(reference)
            if not parts or len(parts) > 25 or any(not value for _, value in parts):
                continue
            groups.append(parent['id'])
            for index, (suffix, answer) in enumerate(parts, 1):
                suffix = suffix.strip()
                label = parent['label'] + (' ' + suffix if suffix else '')
                fields.append({
                    'parent': parent['id'],
                    'id': f'{parent["id"]}-{index}',
                    'label': label,
                    'prompt': '原本問題冊子の' + label + 'に対応する解答を入力してください。',
                    'type': input_type(answer),
                    'reference': answer,
                    'verified': False,
                    'grading': 'llm',
                    'maxLength': 1000,
                    'maxLengthVerified': False,
                    'allowedChars': 'any',
                    'extraction': 'automatic-provisional',
                })
        result['questions'][str(question['number'])] = {
            'completeGroups': groups,
            'fields': fields,
        }
    return result


def validate_sidecar(bank: dict, sidecar: dict) -> dict:
    counts = {'parentGroups': 0, 'splitGroups': 0, 'generatedFields': 0, 'genericGroups': 0}
    assert len(bank['questions']) == 11
    assert len(sidecar['questions']) == 11
    for q in bank['questions']:
        spec = sidecar['questions'][str(q['number'])]
        parent_ids = {f['id'] for f in q['fields']}
        groups = spec['completeGroups']
        assert len(groups) == len(set(groups))
        assert set(groups) <= parent_ids
        counts['parentGroups'] += len(parent_ids)
        counts['genericGroups'] += len(parent_ids) - len(groups)
        seen = set()
        for f in spec['fields']:
            assert f['parent'] in groups
            assert f['id'] not in seen
            seen.add(f['id'])
            assert f['verified'] is False and f['grading'] == 'llm'
            assert f['reference'].strip()
            assert f['type'] in {'word', 'short', 'long'}
            assert f['maxLengthVerified'] is False
        counts['generatedFields'] += len(seen)
        for group in groups:
            if sum(f['parent'] == group for f in spec['fields']) > 1:
                counts['splitGroups'] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--check', action='store_true', help='Do not write; check generated files')
    opts = parser.parse_args()
    root: Path = opts.root
    manifest_file = root / 'sets' / 'b-index.json'
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    assert len(manifest) == 19, 'expected 19 sessions in official archive'
    generated = 0
    for entry in manifest:
        if entry['id'] == 'ap-b-2025-spring':
            assert entry.get('metadataFile') == 'sets/b-meta-2025-spring.json'
            continue  # manually reviewed pilot remains untouched
        set_file = root / entry['file']
        bank = json.loads(set_file.read_text(encoding='utf-8'))
        assert bank['id'] == entry['id']
        output = create_sidecar(bank)
        counts = validate_sidecar(bank, output)
        filename = 'sets/b-meta-' + bank['id'].removeprefix('ap-b-') + '.json'
        entry['metadataFile'] = filename
        encoded = json.dumps(output, ensure_ascii=False, indent=2) + '\n'
        if opts.check:
            assert (root / filename).read_text(encoding='utf-8') == encoded, filename
        else:
            (root / filename).write_text(encoded, encoding='utf-8')
        print(f'{bank["id"]}: {counts}')
        generated += 1
    assert generated == 18
    updated = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    if opts.check:
        assert manifest_file.read_text(encoding='utf-8') == updated
    else:
        manifest_file.write_text(updated, encoding='utf-8')
    print('Validated 18 new metadata sets; 2025-spring manual pilot preserved; 19 manifests linked.')


if __name__ == '__main__':
    main()