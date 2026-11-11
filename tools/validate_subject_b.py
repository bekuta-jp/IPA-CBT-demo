#!/usr/bin/env python3
"""Validate nonofficial Subject B sample schema and route integrity."""
from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[1]
sample=json.loads((ROOT/"sets/b-demo.json").read_text(encoding="utf-8"))
assert len(sample["questions"])==11
assert sample["selectCount"]==5
assert sample["questions"][0]["required"] is True
assert [q["number"] for q in sample["questions"]]==list(range(1,12))
assert len({f["id"] for q in sample["questions"] for f in q["fields"] if f.get("type") in {"single","multi","dropdown","word","short","long"}})>0
types={f["type"] for q in sample["questions"] for f in q["fields"]}
assert {"single","multi","dropdown","word","short","long"} <= types,types
for q in sample["questions"]:
    for f in q["fields"]:
        assert f["maxLength"]>0
        if f.get("grading")=="exact":assert f["type"] in {"single","multi","dropdown","word"} and f.get("correct")
root=(ROOT/"index.html").read_text(encoding="utf-8")
assert 'href="./a.html"' in root and 'href="./b.html"' in root
a=(ROOT/"a.html").read_text(encoding="utf-8")
b=(ROOT/"b.html").read_text(encoding="utf-8")
js=(ROOT/"b.js").read_text(encoding="utf-8")
assert 'src="app.js"' in a and 'src="b.js"' in b
assert 'href="./index.html"' not in b
assert "selectionCommitted?selected:[]" in js
assert "autoGraded" in js and "requiresLLM" in js
print("SUBJECT B: UI routes, selection, field types, grading schema validated")
