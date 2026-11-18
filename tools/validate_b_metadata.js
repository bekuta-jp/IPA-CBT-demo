'use strict';
// Unit-style integration test of the actual browser's metadata merge and validation logic.
// Only pure functions are extracted: no browser, network, or external dependencies required.
const fs=require('node:fs');
const assert=require('node:assert/strict');
const path=require('node:path');
const ROOT=path.resolve(__dirname,'..');
const js=fs.readFileSync(path.join(ROOT,'b.js'),'utf8');
const shortTypes=new Set(['single','multi','dropdown','word','short','long']);
const body=js.slice(js.indexOf('function genericField('),js.indexOf('async function loadAnswerMetadata('));
assert.ok(body.startsWith('function genericField('),'missing genericField');
const apply=new Function('shortTypes','META_SCHEMA',body+'\nreturn applyAnswerMetadata;')(shortTypes,'ap-b-field-meta-v1');
const n=js.slice(js.indexOf('function validateSet('),js.indexOf('function getQ('));
assert.ok(n.startsWith('function validateSet('),'missing validateSet');
const validate=new Function('shortTypes','text',n+'\nreturn validateSet;')(shortTypes,v=>String(v??''));
const index=JSON.parse(fs.readFileSync(path.join(ROOT,'sets','b-index.json'),'utf8'));
assert.equal(index.length,19);
let count=0, fields=0, generic=0, provisional=0, automatic=0;
for(const item of index){
  assert.match(item.metadataFile,/^sets\/b-meta-[a-z0-9-]+\.json$/);
  const data=JSON.parse(fs.readFileSync(path.join(ROOT,item.file),'utf8'));
  const meta=JSON.parse(fs.readFileSync(path.join(ROOT,item.metadataFile),'utf8'));
  const expanded=apply(data,meta);
  const valid=validate(expanded);
  assert.equal(valid.questions.length,11,item.id);
  assert.equal(valid.id,item.id);
  assert.equal(valid.metadataVersion,'ap-b-field-meta-v1');
  for(const q of valid.questions){
    count++;
    assert.ok(q.fields.length);
    const names=new Set();
    for(const f of q.fields){
      assert.ok(f.label,`blank label ${item.id} question ${q.number}`);
      assert.ok(!names.has(f.id),`duplicate answer key ${item.id}/${q.number}/${f.id}`);
      names.add(f.id);
      assert.ok(f.maxLength>0&&f.maxLength<=1000);
      assert.ok(typeof f.reference==='string'&&f.reference.length>0);
      if(f.fallback){generic++;assert.equal(f.grading,'llm');assert.equal(f.maxLengthVerified,false)}
      else if(!f.verified){provisional++;assert.equal(f.grading,'llm');assert.equal(f.maxLengthVerified,false)}
      if(f.grading==='exact'){
        assert.equal(item.id,'ap-b-2025-spring','Only reviewed 2025-spring may machine-grade');
        assert.equal(f.verified,true);
        assert.ok(f.correct.length>0);
        automatic++;
      }
      fields++;
    }
  }
  if(item.id!=='ap-b-2025-spring'){
    const unsupported=valid.questions.flatMap(q=>q.fields).filter(f=>f.grading==='exact'||f.verified);
    assert.equal(unsupported.length,0,`Unverified exact grading ${item.id}`);
  }
}
assert.equal(count,209);
assert.ok(fields>1500,`Unexpectedly few answer fields: ${fields}`);
assert.ok(provisional>1300);
const sample=JSON.parse(fs.readFileSync(path.join(ROOT,'sets','b-2016-spring.json'),'utf8'));
const met=JSON.parse(fs.readFileSync(path.join(ROOT,'sets','b-meta-2016-spring.json'),'utf8'));
const modified=structuredClone(met);
delete modified.questions['1'];
const fallback=validate(apply(sample,modified));
assert.equal(fallback.questions[0].fields.length,sample.questions[0].fields.length);
assert.ok(fallback.questions[0].fields.every(f=>f.fallback&&f.grading==='llm'));
assert.throws(()=>apply(sample,{...met,setId:'wrong-paper'}),/識別子/);
console.log('PASS: 19 sets, '+count+' big questions, '+fields+' answer fields, '+provisional+' provisional, '+generic+' generic, '+automatic+' reviewed exact');
console.log('PASS: fallback on missing question metadata, and mismatch is rejected');