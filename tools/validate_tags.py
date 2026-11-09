#!/usr/bin/env python3
"""Validate independent question-tag sidecars without changing official question data."""
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def load(rel):
    return json.loads((ROOT/rel).read_text(encoding="utf-8"))

def main():
    idx=load("tags/index.json")
    tax=load("tags/taxonomy.json")
    assert idx.get("schemaVersion")=="ap-tag-index-v1"
    assert tax.get("schemaVersion")=="ap-tag-taxonomy-v1"
    dims=tax["dimensions"]
    tri={"yes","no","unknown"}
    valid={"reviewed","provisional","unclassified"}
    for set_id,path in idx["sets"].items():
        assert re.fullmatch(r"tags/[a-zA-Z0-9/_-]+\.json",path) and ".." not in path,path
        side=load(path)
        assert side["schemaVersion"]=="ap-tags-v1" and side["setId"]==set_id
        exam=load("sets/"+set_id+".json")
        ids={q["id"] for q in exam["questions"]}
        tags=side["questions"]
        assert set(tags)==ids,(set_id,sorted(ids-set(tags)),sorted(set(tags)-ids))
        for qid,t in tags.items():
            assert t["primary"] in dims["primary"]["values"],qid
            for d in ("topics","skills"):
                assert isinstance(t[d],list) and t[d],(qid,d)
                assert all(v in dims[d]["values"] for v in t[d]),qid
            assert all(t.get(d) in tri for d in ("calculation","quick","paper")),qid
            assert t.get("status") in valid,qid
            assert t["quick"]!="yes" or (t["calculation"]=="no" and t["paper"]=="no"),qid
        print(f"PASS {set_id}: {len(tags)} tagged, "+str(sum(t["calculation"]=="yes" for t in tags.values()))+
              " calculation, "+str(sum(t["quick"]=="yes" for t in tags.values()))+" quick")
    print("TAG CATALOG OK")

if __name__=="__main__":
    main()
