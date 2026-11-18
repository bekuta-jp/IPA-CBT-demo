'use strict';
// Verify that the actual Subject B rendering/data-model functions can consume all 19 sidecars.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const read = rel => JSON.parse(fs.readFileSync(path.join(root, rel), 'utf8'));
const src = fs.readFileSync(path.join(root, 'b.js'), 'utf8');
const begin = src.indexOf('const META_SCHEMA=');
const end = src.indexOf('function getQ(', begin);
assert(begin > 0 && end > begin, 'B metadata functions not found in application source');
const code = `const shortTypes=new Set(['single','multi','dropdown','word','short','long']);\n` +
  `const text=v=>String(v??'');\n` + src.slice(begin, end) +
  ';({applyAnswerMetadata, validateSet, genericField, loadAnswerMetadata, safeMetadataFile})';
const app = vm.runInNewContext(code, {console, fetch: async()=>{throw Error('unexpected network access')}});

(async()=>{
  const index = read('sets/b-index.json');
  assert.equal(index.length, 19);
  let total=0, split=0, fallbacks=0;
  for (const entry of index) {
    assert(app.safeMetadataFile(entry.metadataFile), `Invalid metadata path: ${entry.id}`);
    const bank = read(entry.file);
    const metadata = read(entry.metadataFile);
    const merged = app.applyAnswerMetadata(bank, metadata);
    const norm = app.validateSet(merged);
    assert.equal(norm.questions.length, 11);
    assert.equal(norm.id, bank.id);
    for (const original of bank.questions) {
      const q = norm.questions.find(z => z.number===original.number);
      assert(q && q.fields.length>=original.fields.length, entry.id + ' Q' + original.number);
      const spec = metadata.questions[String(original.number)];
      const completed = new Set(spec.completeGroups);
      for (const p of original.fields) {
        const list = q.fields.filter(f => f.sourceGroup===p.id);
        if (completed.has(p.id)) {
          assert(list.length>=1, entry.id + ' Q'+original.number+' '+p.id);
          for (const f of list) {
            assert.equal(f.sourceAnswerGroup, p.reference);
            assert(f.reference.trim());
            assert(f.type==='word'||f.type==='short'||f.type==='long'||entry.id==='ap-b-2025-spring');
          }
          if(list.length>1)split++;
        } else {
          const fallback=q.fields.find(f=>f.id===p.id);
          assert(fallback && fallback.type==='long' && fallback.fallback);
          fallbacks++;
        }
      }
      for(const f of q.fields){
        if(entry.id!=='ap-b-2025-spring'){
          assert.equal(f.grading,'llm');
          assert.equal(f.verified,false);
          assert.equal(f.maxLengthVerified,false);
        }
      }
      total+=q.fields.length;
    }
  }
  const bank=read('sets/b-2016-spring.json');
  const meta=read('sets/b-meta-2016-spring.json');
  delete meta.questions['1'];
  const partial=app.applyAnswerMetadata(bank,meta);
  assert(partial.questions[0].fields.every(f=>f.fallback&&f.type==='long'));
  const generic=await app.loadAnswerMetadata(bank,{});
  assert(generic.questions.every(q=>q.fields.every(f=>f.fallback)));
  assert(total>1500 && split>350,{total,split});
  console.log(`PASS: 19 year-session answer metadata sets accepted; ${total} generated input fields; ${split} split groups; ${fallbacks} generic fields; missing metadata remains usable`);
})().catch(e=>{console.error(e);process.exitCode=1});