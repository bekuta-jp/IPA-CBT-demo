'use strict';
// 非公式・静的 CBT 模擬環境。回答はサーバーに送信しない。
const $ = id => document.getElementById(id);
const letters = ['ア','イ','ウ','エ'];
const storageKey = 'ap-cbt-pages-v2';
const bank = new Map();
let questions=[], answers=[], flags=[], current=0, statusOpen=false;
let running=false, finished=false, endAt=0, startedAt=0, timer=null;
let memoText='', memoHtml='', memoImeMode='romaji', results=null, config=null, selectedSetIds=[];
let loadingSets=false, manifestLoaded=false;
const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clamp = (n,lo,hi)=>Math.min(hi,Math.max(lo,n));
function safeStore(data){try{localStorage.setItem(storageKey,JSON.stringify(data));return true}catch(_){return false}}
function saved(){try{return JSON.parse(localStorage.getItem(storageKey)||'null')}catch(_){return null}}
function remember(){if(!questions.length)return;safeStore({questions,answers,flags,current,running,finished,endAt,startedAt,memoText,memoHtml,memoImeMode,results,config,selectedSetIds})}
function restore(){const s=saved();if(!s||!Array.isArray(s.questions)||!s.questions.length||!Array.isArray(s.answers)||s.answers.length!==s.questions.length)return false;
 questions=s.questions;answers=s.answers;flags=Array.isArray(s.flags)?s.flags:Array(questions.length).fill(false);
 current=clamp(s.current||0,0,questions.length-1);running=!!s.running;finished=!!s.finished;
 endAt=s.endAt||0;startedAt=s.startedAt||0;memoText=s.memoText||'';memoHtml=sanitizeMemoHtml(s.memoHtml||esc(memoText));memoImeMode=s.memoImeMode==='kana'?'kana':'romaji';results=s.results||null;
 config=s.config||{};selectedSetIds=s.selectedSetIds||[];$('memo-input').innerHTML=memoHtml;setMemoImeMode(memoImeMode);updateMemoCount();return true}
function modal(html,cls=''){const el=$('modal-content');el.className='modal '+cls;el.innerHTML=html;$('modal-layer').classList.remove('hidden')}
function closeModal(){$('modal-layer').classList.add('hidden')}
function fileName(s){return String(s||'set').replace(/[^a-zA-Z0-9_-]/g,'_').slice(0,45)}
function downloadBlob(blob,name){const a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),3000)}
function downloadJSON(obj,name){downloadBlob(new Blob([JSON.stringify(obj,null,2)],{type:'application/json;charset=utf-8'}),name)}
function downloadText(value,name){downloadBlob(new Blob(['\ufeff',value],{type:'text/markdown;charset=utf-8'}),name)}
function shuffled(n){const a=Array.from({length:n},(_,i)=>i);for(let i=n-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a}
function textField(v,field){if(typeof v!=='string')throw Error(field+' は文字列で指定してください。');return v}
function safeImage(s){if(!s||typeof s!=='string')return '';
 if(/^data:image\/(png|jpeg|webp|gif);base64,[a-z\d+/=]+$/i.test(s))return s;
 if(/^https:\/\/[a-z\d.-]+(?:\:[0-9]+)?\/[a-z\d\/%._~+?#=&-]*$/i.test(s))return s;
 if(/^(?!\/|\.\.)(?:[a-z\d_-]+\/)*[a-z\d_.-]+\.(?:png|jpg|jpeg|webp|gif|svg)$/i.test(s))return s;
 return '';
}
function normalizeAnswer(v){if(Number.isInteger(v)&&v>=0&&v<=3)return v;
 if(typeof v==='string'){const t=v.trim();if(letters.includes(t))return letters.indexOf(t);if(/^[0-3]$/.test(t))return Number(t);if(/^[A-D]$/i.test(t))return t.toUpperCase().charCodeAt(0)-65;}throw Error('answer は 0～3 または ア／イ／ウ／エ で指定してください。')}
function normalizeSet(raw,origin='custom'){
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('セットは {id,title,questions:[...]} の形式で指定してください。');
 if(!Array.isArray(raw.questions)||raw.questions.length<1||raw.questions.length>2000)throw Error('questions は1～2000問の配列にしてください。');
 const id=String(raw.id||`${origin}-${Date.now()}-${Math.random().toString(36).slice(2)}`);
 const title=String(raw.title||id),year=raw.year==null?'':String(raw.year),season=String(raw.season||'');
 const sourceType=raw.sourceType==='ipa'?'ipa':'original';
 const qlist=raw.questions.map((q,i)=>{
  try{
   if(!q||typeof q!=='object')throw Error('問題データがありません。');
   const stem=textField(q.stem??q.question,'stem / question');
   if(!stem.trim())throw Error('問題文が空です。');
   let options=q.options??q.choices;
   if(options&&!Array.isArray(options)&&typeof options==='object')options=letters.map(k=>options[k]);
   if(!Array.isArray(options)||options.length!==4||options.some(o=>typeof o!=='string'||!o.trim()))throw Error('options は4件の文字列で指定してください。');
   const answer=normalizeAnswer(q.answer);
   const originalNo=q.number??(i+1);
   const defaultSource=sourceType==='ipa'?`出典：${year||'年度不明'}年度 ${season||'期不明'} 応用情報技術者試験 午前 問${originalNo}`:`自作問題：${title} 問${originalNo}`;
   const src=String(q.source||defaultSource);
   return {id:String(q.id||i+1),number:originalNo,topic:String(q.topic||'一般'),stem,code:String(q.code||''),image:safeImage(q.image),
   options:[...options],optionImages:Array.from({length:4},(_,k)=>safeImage(q.optionImages?.[k])),answer,imageOnly:!!q.imageOnly,
   explanation:String(q.explanation||''),source:src,modified:!!q.modified};
  }catch(e){throw Error(`${title} の${i+1}問目：${e.message}`)}
 });
 return {id,title,year,season,sourceType,exam:String(raw.exam||'AP'),questions:qlist,count:qlist.length,origin};
}
function registerSet(raw,origin='custom'){
 const set=normalizeSet(raw,origin);
 let key=set.id;
 if(bank.has(key)){if(origin==='custom'){let k=2;while(bank.has(key+'-'+k))k++;key+='-'+k;set.id=key;}else return bank.get(key)}
 bank.set(key,set);return set;
}
function registerManifest(m){if(!Array.isArray(m))throw Error('sets/index.json は配列にしてください。');let count=0;
 for(const item of m){if(!item||typeof item!=='object'||typeof item.id!=='string'||typeof item.file!=='string')continue;
  if(bank.has(item.id))continue;
  if(!/^sets\/[a-zA-Z0-9/_-]+\.json$/.test(item.file)||item.file.includes('..'))continue;
  bank.set(item.id,{id:item.id,title:String(item.title||item.id),year:String(item.year??''),season:String(item.season||''),sourceType:item.sourceType==='ipa'?'ipa':'original',exam:'AP',count:Number(item.count)||0,file:item.file,origin:'public',questions:null});count++;
 }return count}
async function loadManifest(){if(manifestLoaded)return;
 manifestLoaded=true;
 if(location.protocol==='file:')return;
 try{const r=await fetch('./sets/index.json',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);registerManifest(await r.json());}
 catch(e){console.warn('公開セット一覧が読み込めませんでした',e)}
 if(!selectedSetIds.length){const available=metadataList().find(isOfficialExamSet);selectedSetIds=[available?.id||'demo-a'];}
 renderSetupSets();
}
function metadataSort(a,b){let ya=Number(a.year)||0,yb=Number(b.year)||0;if(yb!==ya)return yb-ya;return b.season.localeCompare(a.season,'ja')||a.title.localeCompare(b.title,'ja')}
function metadataList(){return [...bank.values()].sort(metadataSort)}
function isOfficialExamSet(x){return x.sourceType==='ipa'&&x.count===80&&x.origin==='public'}
function buildSetCards(){
 const year=$('year-filter')?.value||'all',season=$('season-filter')?.value||'all',typ=$('type-filter')?.value||'all',mode=selectionMode();
 const sets=metadataList().filter(x=>(year==='all'||x.year===year)&&(season==='all'||x.season===season)&&(typ==='all'||(typ==='ipa'?isOfficialExamSet(x):typ==='sample'?!isOfficialExamSet(x):x.origin==='custom')));
 const groups=[
  {title:'本試験の公開過去問（各80問）',help:'IPA公開の午前問題。単一回では一つだけ選択します。',items:sets.filter(isOfficialExamSet)},
  {title:'試作・動作確認・自作問題',help:'少問数の試作問題とオリジナル問題。公式80問版とは別枠です。',items:sets.filter(x=>!isOfficialExamSet(x))}
 ];
 const html=groups.filter(g=>g.items.length).map(g=>
  '<div class="exam-set-group"><h3>'+g.title+'</h3><p>'+g.help+'</p>'+
  g.items.map(x=>{
   const checked=selectedSetIds.includes(x.id)?'checked':'';
   const badge=isOfficialExamSet(x)?'<span class="badge-real">IPA・80問</span>':x.sourceType==='ipa'?'<span class="badge-demo">テキスト試作</span>':x.origin==='demo'?'<span class="badge-demo">デモ</span>':'<span class="badge-demo">自作</span>';
   return '<label class="set-item"><input type="'+(mode==='single'?'radio':'checkbox')+'" name="'+(mode==='single'?'exam-set-radio':'exam-set-checkbox')+'" data-set-id="'+esc(x.id)+'" '+checked+'><span class="set-meta"><b>'+esc(x.title)+'</b>'+badge+'<small>'+esc(x.year)+' '+esc(x.season)+' '+(x.origin==='demo'?'動作確認用':x.origin==='custom'?'ローカル自作':'公開問題')+'</small></span><span class="set-count">'+x.count+'問</span></label>';
  }).join('')+'</div>'
 ).join('');
 return html||'<p class="loading-note">該当する問題セットがありません。年度や区分を変更するか、JSONを読み込んでください。</p>';
}
function selectionMode(){return document.querySelector('input[name="set-mode"]:checked')?.value||'single'}
function selectedBank(){return selectedSetIds.map(id=>bank.get(id)).filter(Boolean)}
function updateSelectionStats(){
 if(!$('selection-stats'))return;
 const n=selectedBank().reduce((a,s)=>a+s.count,0),mode=selectionMode();
 $('selection-stats').textContent=mode==='single' ? (selectedSetIds.length?'選択した回：'+(bank.get(selectedSetIds[0])?.title||''):'受験する回を一つ選択してください。') : '複数回混合：'+selectedSetIds.length+'セット／収録数 '+n+'問（最大80問をランダム出題）';
}
function renderSetupSets(){
 if(!$('set-list'))return;
 const els=metadataList(),years=[...new Set(els.filter(isOfficialExamSet).map(s=>s.year).filter(Boolean))].sort((a,b)=>Number(b)-Number(a));
 const seasons=['春期','秋期'];
 const y=$('year-filter'),sv=y.value||'all';y.innerHTML='<option value="all">全年度</option>'+years.map(x=>'<option value="'+esc(x)+'">'+esc(x)+'年度</option>').join('');y.value=years.includes(sv)?sv:'all';
 const st=$('season-filter'),ss=st.value||'all';st.innerHTML='<option value="all">全期</option>'+seasons.map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join('');st.value=seasons.includes(ss)?ss:'all';
 renderCardsOnly();
}
function renderCardsOnly(){
 if(!$('set-list'))return;
 $('set-list').innerHTML=buildSetCards();
 $('set-list').querySelectorAll('[data-set-id]').forEach(el=>el.addEventListener('change',()=>{
  const id=el.dataset.setId;
  if(selectionMode()==='single'){selectedSetIds=[id]}else{selectedSetIds=el.checked?[...new Set([...selectedSetIds,id])]:selectedSetIds.filter(s=>s!==id)}
  renderCardsOnly();
 }));
 updateSelectionStats();
}
function reset(){clearInterval(timer);running=false;finished=false;current=0;statusOpen=false;questions=[];answers=[];flags=[];results=null;memoText='';memoHtml='';$('memo-input').innerHTML='';clearSearchHighlights();updateMemoCount();try{localStorage.removeItem(storageKey)}catch(_){}showStart()}
function showStart(){
 const resumeState=saved(),canResume=!!(resumeState?.running&&resumeState?.questions?.length);
 if(!selectedSetIds.length)selectedSetIds=[];
 modal(`<h1>応用情報技術者試験 CBT 科目A</h1><p>非公式・演習用。回別問題の原順・ランダム出題、選択肢シャッフル、解答結果のLLM向け出力に対応します。</p>
 <section class="setup-section"><h2>① 問題セットを選ぶ</h2>
 <div class="setup-controls"><label>表示年度 <select id="year-filter"><option value="all">全年度</option></select></label>
 <label>期 <select id="season-filter"><option value="all">全期</option></select></label>
 <label>区分 <select id="type-filter"><option value="all">すべて</option><option value="ipa">本試験の過去問</option><option value="sample">試作・動作確認</option><option value="custom">自作問題</option></select></label></div>
 <div class="set-list" id="set-list"></div><div class="status-message" id="selection-stats"></div>
 <div class="settings-grid" style="margin-top:9px"><fieldset class="fieldset"><legend>問題セットの組合せ</legend><label><input type="radio" name="set-mode" value="single" checked> 単一回を指定</label><label><input type="radio" name="set-mode" value="multi"> 複数回からランダム抽出</label></fieldset>
 <fieldset class="fieldset"><legend>出題順</legend><label><input type="radio" name="q-order" value="original" checked> 元の問番号順</label><label><input type="radio" name="q-order" value="random"> ランダム</label><small>複数回モードは必ずランダムです。</small></fieldset></div>
 </section><section class="setup-section"><h2>② 選択肢と試験時間</h2>
 <div class="settings-grid"><fieldset class="fieldset"><legend>選択肢の順序</legend><label><input type="radio" name="a-order" value="original" checked> 原順（ア→エ）</label><label><input type="radio" name="a-order" value="random"> 選択肢もランダム</label><small>※公式問題画像のセットでは、選択肢が画像内に含まれるため原順固定です。</small></fieldset>
 <fieldset class="fieldset"><legend>出題数・制限時間</legend><div class="setup-controls"><label>問題数 <input type="number" id="limit-count" min="1" max="80" value="80"></label><label>時間（分） <input type="number" id="limit-time" min="1" max="400" placeholder="自動"></label></div><small>時間空欄：80問150分を基準に自動調整。選択問題が不足すると出題数は少なくなります。</small></fieldset></div>
 </section><section class="setup-section"><h2>③ 自作・追加の問題を読み込む</h2>
 <label for="file-input">JSONファイル（複数選択可）</label><input id="file-input" type="file" accept=".json,application/json" multiple>
 <div class="import-note">読み込んだ問題セットはこの端末だけで利用します。GitHubへ送信されません。<br>形式は同梱の <b>examples/custom-set.json</b> を参照。</div><div class="status-message" id="file-status"></div></section>
 <div id="setup-status" class="status-message"></div>
 <div class="actionrow">${canResume?'<button id="resume-btn" class="btn light">前回の続きを再開</button>':''}<button id="start-btn" class="btn">試験開始</button></div>
 <p class="setup-prompt">終了後、画面には点数のみ表示します。問題・模範解答・自分の解答はJSON／Markdownで保存してLLMに渡せます。</p>`, 'setup');
 $('year-filter').onchange=renderCardsOnly;$('season-filter').onchange=renderCardsOnly;$('type-filter').onchange=renderCardsOnly;
 document.querySelectorAll('[name="set-mode"]').forEach(x=>x.addEventListener('change',()=>{if(x.checked&&x.value==='single'&&selectedSetIds.length>1)selectedSetIds=[selectedSetIds[0]];document.querySelectorAll('[name="q-order"]').forEach(r=>{r.disabled=x.value==='multi'&&x.checked;});renderCardsOnly()}));
 $('file-input').onchange=importFiles;$('start-btn').onclick=beginFromSelection;
 if($('resume-btn'))$('resume-btn').onclick=()=>{if(restore()){closeModal();refresh();if(running){tickTimer();timer=setInterval(tickTimer,500)}}};
 renderSetupSets();loadManifest();
}
async function importFiles(e){const files=[...e.target.files];const status=$('file-status');if(!files.length)return;let n=0,errors=[];
 for(const f of files){try{
  if(f.size>8_000_000)throw Error('8MBを超えています。');
  const raw=JSON.parse(await f.text());
  let sets;
  if(Array.isArray(raw))sets=raw.length&&raw.every(x=>x&&Array.isArray(x.questions))?raw:[{id:f.name.replace(/\.json$/i,''),title:f.name.replace(/\.json$/i,''),questions:raw}];
  else if(Array.isArray(raw.sets))sets=raw.sets;else sets=[raw];
  for(const s of sets){const added=registerSet(s,'custom');n++;selectedSetIds=[...new Set([...selectedSetIds,added.id])];}
 }catch(err){errors.push(f.name+': '+err.message)}}
 if(selectionMode()==='single'&&selectedSetIds.length>1)selectedSetIds=[selectedSetIds[selectedSetIds.length-1]];
 status.classList.toggle('error',errors.length>0);status.textContent=`${n}セットの読み込みが完了しました。${errors.length?'\nエラー：'+errors.join('\n'):''}`;
 renderSetupSets();
}
async function fetchSet(set){if(set.questions)return set;
 const resp=await fetch('./'+set.file,{cache:'no-store'});
 if(!resp.ok)throw Error(`${set.title}（HTTP ${resp.status}）`);
 const obj=await resp.json();
 if(obj.id!==set.id)throw Error(`${set.title}：一覧とデータのIDが一致しません。`);
 const parsed=normalizeSet(obj,'public');
 bank.set(set.id,parsed);return parsed;
}
function createExamQuestion(q,s,shuffleAnswers){
 // 原本画像に選択肢を含む問題は、解答ボタンのラベルだけを動かさない。
 const order=shuffleAnswers&&!q.imageOnly?shuffled(4):[0,1,2,3],idx=order.indexOf(q.answer);
 return {uid:`${s.id}::${q.id}`,setId:s.id,setTitle:s.title,year:s.year,season:s.season,originalNumber:q.number,
  topic:q.topic,stem:q.stem,code:q.code,image:q.image,imageOnly:q.imageOnly,
  originalOptions:q.options,originalAnswer:q.answer,
  options:order.map(i=>q.options[i]),optionImages:order.map(i=>q.optionImages[i]),
  optionOrder:order,answer:idx,explanation:q.explanation,source:q.source,modified:q.modified};
}
async function beginFromSelection(){if(loadingSets)return;
 const mode=selectionMode(),qOrder=document.querySelector('[name="q-order"]:checked')?.value||'original',aOrder=document.querySelector('[name="a-order"]:checked')?.value||'original';
 const lim=clamp(Number($('limit-count').value)||80,1,80),rawTime=$('limit-time').value.trim(),minutes=rawTime?clamp(Number(rawTime)||1,1,400):null;
 const btn=$('start-btn'),notice=$('setup-status');let chosen=selectedBank();
 if(!chosen.length){notice.textContent='少なくとも1つの問題セットを選択してください。';notice.className='status-message error';return}
 if(mode==='single'&&chosen.length!==1){notice.textContent='単一回モードでは1セットだけを選択してください。';notice.className='status-message error';return}
 loadingSets=true;btn.disabled=true;btn.textContent='問題セットを確認中…';notice.className='status-message';notice.textContent='読み込み中';
 try{
  chosen=await Promise.all(chosen.map(fetchSet));
  let pool=chosen.flatMap(s=>s.questions.map(q=>({q,s})));
  // 複数回に同じ問題文・選択肢があるときのみ重複排除する。
  if(mode==='multi'){const seen=new Set();pool=pool.filter(({q})=>{const k=JSON.stringify([q.stem,q.options]);if(seen.has(k))return false;seen.add(k);return true;})}
  if(!pool.length)throw Error('選択したセットに問題がありません。');
  if(mode==='multi'||qOrder==='random')pool=shuffled(pool.length).map(i=>pool[i]);
  else pool=pool.sort((a,b)=>Number(a.q.number)-Number(b.q.number));
  pool=pool.slice(0,lim);
  const qs=pool.map(({q,s})=>createExamQuestion(q,s,aOrder==='random'));
  const mins=minutes||Math.max(1,Math.ceil(qs.length*150/80));
  start(qs,mins,{setMode:mode,questionOrder:mode==='multi'?'random':qOrder,choiceOrder:aOrder,questionLimit:lim,minutes:mins,sourceSetIds:chosen.map(s=>s.id),sourceSetTitles:chosen.map(s=>s.title)});
 }catch(e){notice.className='status-message error';notice.textContent='開始できません：'+e.message}finally{loadingSets=false;if($('start-btn')){$('start-btn').disabled=false;$('start-btn').textContent='試験開始'}}
}
function start(qs,mins,conf){clearInterval(timer);questions=qs;answers=Array(qs.length).fill(null);flags=Array(qs.length).fill(false);current=0;statusOpen=false;running=true;finished=false;results=null;config=conf;
 startedAt=Date.now();endAt=startedAt+mins*60000;memoText='';memoHtml='';$('memo-input').innerHTML='';clearSearchHighlights();updateMemoCount();$('memo-window').classList.remove('visible');$('calc-window').classList.remove('visible');closeModal();remember();refresh();tickTimer();timer=setInterval(tickTimer,500)}
function tickTimer(){if(!running)return;
 const ms=Math.max(0,endAt-Date.now()),sec=Math.ceil(ms/1000),h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60),s=sec%60;
 $('remaining').textContent=[h,m,s].map(n=>String(n).padStart(2,'0')).join(':');$('remaining').style.color=sec<=300?'#b7223b':'';if(ms===0)endExam(true);
}
function renderGrid(){
 $('status-grid').innerHTML=questions.map((_,i)=>`<button class="qcell ${answers[i]!==null?'answered':''} ${flags[i]?'flagged':''} ${i===current?'current':''}" aria-label="問${i+1}${answers[i]!==null?'解答済み':'未解答'}" data-jump="${i}">${i+1}</button>`).join('');
 $('status-grid').querySelectorAll('[data-jump]').forEach(b=>b.onclick=()=>{current=Number(b.dataset.jump);statusOpen=false;refresh()});
}
function renderImage(url,cls,alt){return url?`<img class="${cls}" src="${esc(url)}" alt="${esc(alt)}">`:''}
function refresh(){if(!questions.length){$('subheading').textContent='問題セットを選択してください';$('question-body').textContent='';$('choices').textContent='';$('remaining').textContent='--:--:--';return}
 const q=questions[current],n=questions.length;
 $('subheading').textContent=`${n}ページ中${current+1}ページ目`;
 $('answer-title').textContent=`問${q.originalNumber ?? current+1}`;
 $('question-body').innerHTML=q.imageOnly
  ? `<div class="sr-only">${esc(q.stem)}</div>${renderImage(q.image,'question-image question-image-original','IPA公式問題冊子から切り出した問'+q.originalNumber+'。ア〜エの選択肢も画像内にあります。')}`
  : `<div class="q-stem">${esc(q.stem)}</div>${renderImage(q.image,'question-image','問題の図表')}
 ${q.code?`<pre class="q-code">${esc(q.code)}</pre>`:''}
 <div class="q-opt-list">${q.options.map((o,i)=>`<div class="q-opt"><span class="letter">${letters[i]}</span><div>${esc(o)}${renderImage(q.optionImages?.[i],'option-image',letters[i]+'の図表')}</div></div>`).join('')}</div>`;
 $('choices').innerHTML=letters.map((ch,i)=>`<button class="choice ${answers[current]===i?'chosen':''}" aria-pressed="${answers[current]===i}" data-opt="${i}" ${!running?'disabled':''}>${ch}</button>`).join('');
 $('choices').querySelectorAll('[data-opt]').forEach(b=>b.onclick=()=>{if(!running)return;const i=Number(b.dataset.opt);answers[current]=answers[current]===i?null:i;remember();refresh()});
 $('review-check').checked=!!flags[current];$('review-check').disabled=!running;
 $('answer-pane').classList.toggle('review-marked',!!flags[current]);
 $('flag-btn').classList.toggle('active',!!flags[current]);$('flag-btn').setAttribute('aria-pressed',String(!!flags[current]));$('flag-btn').disabled=!running;
 $('prev-btn').disabled=current===0;$('next-btn').disabled=current===n-1;
 $('memo-btn').disabled=!running;$('calc-btn').disabled=!running;$('end-btn').disabled=!running;
 $('status-btn').classList.toggle('active',statusOpen);
 $('question-pane').style.display=statusOpen?'none':'flex';$('answer-pane').style.display=statusOpen?'none':'block';$('splitter').style.display=statusOpen?'none':'block';$('status-pane').classList.toggle('open',statusOpen);
 document.body.classList.toggle('exam-running',running);
 renderGrid();$('question-scroll').scrollTop=0;remember();
}
function endExam(auto=false){if(!running)return;running=false;finished=true;clearInterval(timer);
 $('memo-window').classList.remove('visible');$('calc-window').classList.remove('visible');
 const correct=questions.reduce((n,q,i)=>n+Number(answers[i]===q.answer),0);
 results={correct,answered:answers.filter(x=>x!==null).length,elapsedSeconds:Math.max(0,Math.round((Date.now()-startedAt)/1000)),auto:!!auto,completedAt:new Date().toISOString()};
 $('remaining').textContent='00:00:00';remember();refresh();showResults();
}
function showResults(){if(!results)return;const r=results,n=questions.length,pct=Math.round(r.correct/n*10000)/100;
 modal(`<h1>${r.auto?'制限時間終了':'試験終了'}・採点結果</h1><div class="score-card"><strong>${r.correct} / ${n}</strong><p>得点率：${pct}%　（${n}問中${r.correct}問正解）</p></div>
 <p>詳細な正誤・模範解答・解説は<strong>この画面には表示しません</strong>。以下から問題・模範解答・自分の解答をセットで出力できます。</p>
 <div class="result-actions"><button id="export-all-json" class="btn">全問データをJSON保存</button><button id="export-all-md" class="btn light">全問データをMarkdown保存</button><button id="export-wrong-md" class="btn light">誤答・未解答のみMarkdown保存</button><button id="copy-wrong" class="btn light">LLMへの復習依頼をコピー</button></div>
 <div id="export-status" class="status-message" style="margin-top:10px"></div><p class="setup-prompt">全問データには選択肢の並び替え結果と元の選択肢番号も含みます。原文・出典・改変情報も保存されます。</p>
 <div class="actionrow"><button class="btn" id="new-exam">新しい試験</button></div>`, 'results');
 $('export-all-json').onclick=()=>downloadJSON(resultData(),`ap_cbt_result_${stamp()}.json`);
 $('export-all-md').onclick=()=>downloadText(markdownReport(false),`ap_cbt_result_all_${stamp()}.md`);
 $('export-wrong-md').onclick=()=>downloadText(markdownReport(true),`ap_cbt_result_review_${stamp()}.md`);
 $('copy-wrong').onclick=async()=>{try{await navigator.clipboard.writeText(markdownReport(true));$('export-status').textContent='復習依頼文をコピーしました。ChatGPTなどに貼り付けてください。'}catch(e){$('export-status').textContent='クリップボードへのコピーに失敗しました。Markdownを保存して利用してください。'}};
 $('new-exam').onclick=reset;
}
function stamp(){const d=new Date();return `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}_${String(d.getHours()).padStart(2,'0')}${String(d.getMinutes()).padStart(2,'0')}`}
function resultData(){if(!finished||!results)throw Error('試験はまだ終了していません。');
 return {schemaVersion:'ap-cbt-result-v1',generatedAt:new Date().toISOString(),mode:'AP 科目A（非公式練習）',
 settings:config,summary:{score:results.correct,total:questions.length,percentage:Math.round(results.correct/questions.length*10000)/100,
 answered:results.answered,unanswered:questions.length-results.answered,elapsedSeconds:results.elapsedSeconds,autoEnded:results.auto},
 questions:questions.map((q,i)=>{
  const a=answers[i],orig=a===null?null:q.optionOrder[a];
  return {sequence:i+1,id:q.uid,sourceSetId:q.setId,sourceSetTitle:q.setTitle,originalNumber:q.originalNumber,topic:q.topic,
   source:q.source,modified:q.modified,question:q.stem,code:q.code,image:q.image?new URL(q.image,location.href).href:'',imageOnly:q.imageOnly,
   displayedOptions:q.options.map((text,k)=>({label:letters[k],text,image:q.optionImages?.[k]||'',originalLabel:letters[q.optionOrder[k]]})),
   originalOptions:q.originalOptions.map((text,k)=>({label:letters[k],text})),
   correctAnswer:{displayedLabel:letters[q.answer],originalLabel:letters[q.originalAnswer],text:q.options[q.answer]},
   userAnswer:a===null?null:{displayedLabel:letters[a],originalLabel:letters[orig],text:q.options[a]},
   isCorrect:a===q.answer,flagged:!!flags[i],explanation:q.explanation||''};
 })};
}
function markdownReport(wrongOnly){const data=resultData(),qs=wrongOnly?data.questions.filter(q=>!q.isCorrect):data.questions;
 const out=[`# 応用情報技術者試験 CBT 練習結果${wrongOnly?'（誤答・未解答）':'（全問）'}`,
 ``, `- 得点: ${data.summary.score} / ${data.summary.total} (${data.summary.percentage}%)`,
 `- 対象セット: ${data.settings.sourceSetTitles.join('、')}`,`- 出題順: ${data.settings.questionOrder} ／ 選択肢順: ${data.settings.choiceOrder}`,
 `- 出力対象: ${qs.length}問`, ``, `## LLMへの依頼`,
 `以下の問題と、模範解答・私の解答を照合してください。誤答・未解答の原因を推測し、全選択肢を一つずつ解説し、計算量やSQL等で必要な前提知識を基礎から説明してください。分野別の弱点・次の復習優先順位を提示し、最後に理解確認の類題を出してください。正解だった問題については、必要に応じて理解が曖昧になりそうな論点を補足してください。出典や正解データに疑義があれば指摘してください。`,``, `---`];
 if(!qs.length){out.push('全問正解のため、誤答・未解答はありません。');return out.join('\n')}
 for(const q of qs){out.push(``,`### 問${q.sequence} ／ ${q.sourceSetTitle}・元の問${q.originalNumber} ／ ${q.topic}`,
 `- 出典: ${q.source}${q.modified?'（一部改変あり）':''}`,
 `- 問題:`,q.question);
  if(q.code)out.push('```text',q.code,'```');if(q.image)out.push(`- IPA問題画像（数式・表・図・選択肢の原本表示。原文確認はこちらが優先）: ${q.image}`);
  for(const o of q.displayedOptions){out.push(`- ${o.label}: ${o.text}${o.image?' [画像: '+o.image+']':''} （元の${o.originalLabel}）`)}
  out.push(`- 私の解答: ${q.userAnswer?q.userAnswer.displayedLabel+'：'+q.userAnswer.text:'未解答'}`,
  `- 模範解答: ${q.correctAnswer.displayedLabel}：${q.correctAnswer.text}`,
  `- 判定: ${q.isCorrect?'正解':q.userAnswer?'不正解':'未解答'}`);
  if(q.explanation)out.push(`- 収録解説: ${q.explanation}`);
  out.push('');
 }
 return out.join('\n');
}
function confirmEnd(){if(!running)return;const a=answers.filter(v=>v!==null).length;
 modal(`<h1>試験を終了しますか？</h1><p>${a} / ${questions.length} 問解答済み。未解答は ${questions.length-a} 問です。終了後は解答の変更ができません。</p>
 <div class="actionrow"><button class="btn light" id="cancel-end">試験に戻る</button><button class="btn danger" id="confirm-end">試験終了</button></div>`);
 $('cancel-end').onclick=closeModal;$('confirm-end').onclick=()=>endExam(false);
}
function reference(){modal(`<h1>操作方法・データについて</h1><div class="hint">
 <b>解答：</b>右側からア・イ・ウ・エを選択。再クリックで選択解除。<br>
 <b>問題移動：</b>前後ボタン／解答状況一覧。見直しフラグ対応。<br>
 <b>メモと電卓：</b>操作練習用。表示幅調整・拡大・白黒反転にも対応。<br>
 <b>出題：</b>単一回の問番号順・ランダム、複数回混合、選択肢シャッフル。<br>
 <b>終了後：</b>点数だけを表示。全問・誤答だけの復習用データを出力。<br>
 <b>途中保存：</b>このブラウザのローカルストレージに保存（容量制限あり）。<br>
 <b>図表：</b>JSONのimage/optionImagesに画像パス・data URIを設定可能。<br>
 <b>公開過去問：</b>出典と改変情報を必ず設定してください。</div>
 <p><small>非公式の練習画面です。CBT本番と完全一致するものではありません。IPAが公開していない現行CBT問題を収録・共有しないでください。</small></p>
 <div class="actionrow"><button id="close-ref" class="btn">閉じる</button></div>`);$('close-ref').onclick=closeModal}
// CBT controls
$('status-btn').onclick=()=>{if(!running&&!finished)return;statusOpen=!statusOpen;refresh()};
$('prev-btn').onclick=()=>{if(current>0){current--;refresh()}};
$('next-btn').onclick=()=>{if(current<questions.length-1){current++;refresh()}};
$('flag-btn').onclick=()=>{if(!running)return;flags[current]=!flags[current];refresh()};
$('review-check').onchange=e=>{if(!running)return;flags[current]=e.target.checked;refresh()};
$('end-btn').onclick=confirmEnd;$('ref-btn').onclick=reference;
$('memo-btn').onclick=()=>toggleFloat('memo-window');$('calc-btn').onclick=()=>toggleFloat('calc-window');
$('invert-toggle').onclick=e=>{const on=document.body.classList.toggle('dark');e.currentTarget.classList.toggle('on',on);e.currentTarget.setAttribute('aria-pressed',String(on))};
$('zoom').oninput=e=>{$('zoom-number').textContent=e.target.value+' %';$('question-body').style.setProperty('--qsize',(16*Number(e.target.value)/100)+'px')};
// メモの保存内容は許可タグ・マーカーだけに正規化。クリップボード貼付は試験中禁止。
function sanitizeMemoHtml(input){
 const source=document.createElement('div');source.innerHTML=String(input||'').slice(0,60000);
 function clean(node){if(node.nodeType===Node.TEXT_NODE)return esc(node.textContent);if(node.nodeType!==Node.ELEMENT_NODE)return '';
  if(node.tagName==='BR')return '<br>';
  const children=[...node.childNodes].map(clean).join('');
  if(node.classList.contains('memo-mark-red'))return `<span class="memo-mark-red">${children}</span>`;
  if(node.classList.contains('memo-mark-blue'))return `<span class="memo-mark-blue">${children}</span>`;
  if(node.classList.contains('memo-mark-yellow'))return `<span class="memo-mark-yellow">${children}</span>`;
  if(['DIV','P'].includes(node.tagName))return children+'<br>';
  return children;
 }
 return [...source.childNodes].map(clean).join('');
}
function updateMemoCount(){const n=($('memo-input').innerText||'').length;$('memo-count').textContent=`${n.toLocaleString('ja-JP')} / 10,000 文字`;}
function persistMemo(){memoHtml=sanitizeMemoHtml($('memo-input').innerHTML);memoText=$('memo-input').innerText.slice(0,10000);updateMemoCount();remember();}
$('memo-input').addEventListener('input',()=>{persistMemo()});
function setMemoImeMode(mode){memoImeMode=mode==='kana'?'kana':'romaji';$('memo-romaji').classList.toggle('is-active',memoImeMode==='romaji');$('memo-kana').classList.toggle('is-active',memoImeMode==='kana');
  $('memo-romaji').setAttribute('aria-pressed',String(memoImeMode==='romaji'));$('memo-kana').setAttribute('aria-pressed',String(memoImeMode==='kana'));
  $('memo-input').lang='ja';$('memo-input').inputMode='text';$('memo-input-note').textContent=memoImeMode==='romaji'?'ローマ字入力：OSのIMEをローマ字入力に設定':'かな入力：OSのIMEをかな入力に設定';
}
$('memo-romaji').onclick=()=>{setMemoImeMode('romaji');persistMemo();$('memo-input').focus()};
$('memo-kana').onclick=()=>{setMemoImeMode('kana');persistMemo();$('memo-input').focus()};
let memoInternalClipboard='';
let memoSavedRange=null;
let memoSearchResults=[],memoSearchIndex=-1;
function memoValidRange(range){return !!range&&$('memo-input').contains(range.commonAncestorContainer)}
function memoActiveRange(requireSelected=false){
 const sel=window.getSelection();
 if(sel&&sel.rangeCount){const currentRange=sel.getRangeAt(0);if(memoValidRange(currentRange)&&(!requireSelected||!currentRange.collapsed))return currentRange;}
 if(memoValidRange(memoSavedRange)&&(!requireSelected||!memoSavedRange.collapsed))return memoSavedRange.cloneRange();
 return null;
}
function saveMemoSelection(){const sel=window.getSelection();if(sel&&sel.rangeCount&&memoValidRange(sel.getRangeAt(0)))memoSavedRange=sel.getRangeAt(0).cloneRange();}
$('memo-input').addEventListener('mouseup',saveMemoSelection);
$('memo-input').addEventListener('keyup',saveMemoSelection);
// メモツールバー操作中の選択解除を防ぐ。
document.querySelectorAll('#memo-window .memo-tools button').forEach(b=>b.addEventListener('mousedown',e=>{saveMemoSelection();e.preventDefault()}));
function clearSearchHighlights(){
 $('memo-input').querySelectorAll('.memo-search-hit').forEach(s=>s.replaceWith(...s.childNodes));$('memo-input').normalize();memoSearchResults=[];memoSearchIndex=-1;
}
function gotoMemoSearch(index){if(!memoSearchResults.length)return;
 memoSearchIndex=(index+memoSearchResults.length)%memoSearchResults.length;
 memoSearchResults.forEach((el,i)=>el.classList.toggle('current-hit',i===memoSearchIndex));
 $('memo-hits').textContent=`${memoSearchIndex+1}/${memoSearchResults.length}`;
 memoSearchResults[memoSearchIndex].scrollIntoView({block:'nearest'});
}
function searchMemo(){clearSearchHighlights();const needle=$('memo-search').value.trim();if(!needle){$('memo-hits').textContent='0/0';return}
 const walker=document.createTreeWalker($('memo-input'),NodeFilter.SHOW_TEXT);const textNodes=[];while(walker.nextNode())textNodes.push(walker.currentNode);
 const hits=[];for(const node of textNodes){let cur=node;let pos=0;const lower=cur.textContent.toLocaleLowerCase('ja'),query=needle.toLocaleLowerCase('ja');const idxs=[];
  while((pos=lower.indexOf(query,pos))!==-1){idxs.push(pos);pos+=query.length;if(idxs.length>=100)break}
  for(let k=idxs.length-1;k>=0;k--){const ix=idxs[k],tail=cur.splitText(ix);tail.splitText(needle.length);const mark=document.createElement('span');mark.className='memo-search-hit';tail.replaceWith(mark);mark.append(tail);hits.unshift(mark)}
 }
 memoSearchResults=[...$('memo-input').querySelectorAll('.memo-search-hit')];$('memo-hits').textContent=`0/${memoSearchResults.length}`;
 if(memoSearchResults.length)gotoMemoSearch(0);
}
$('memo-search-toggle').onclick=()=>{$('memo-searchbar').hidden=!$('memo-searchbar').hidden;if(!$('memo-searchbar').hidden)$('memo-search').focus();else clearSearchHighlights()};
$('memo-search-close').onclick=()=>{$('memo-searchbar').hidden=true;clearSearchHighlights();$('memo-input').focus()};
$('memo-search').addEventListener('input',searchMemo);
$('memo-search').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();gotoMemoSearch(memoSearchIndex+(e.shiftKey?-1:1))}});
$('memo-find-prev').onclick=()=>gotoMemoSearch(memoSearchIndex-1);
$('memo-find-next').onclick=()=>gotoMemoSearch(memoSearchIndex+1);
function markMemo(color){clearSearchHighlights();const range=memoActiveRange(true);if(!range)return;
 const selected=range.toString();if(!selected.trim()||selected.length>10000)return;
 const contents=range.extractContents();const wrapper=document.createElement('span');if(color!=='none')wrapper.className='memo-mark-'+color;wrapper.append(contents);
 if(color==='none'){range.insertNode(wrapper);wrapper.replaceWith(...wrapper.childNodes)}else range.insertNode(wrapper);
 window.getSelection()?.removeAllRanges();memoSavedRange=null;persistMemo();}
document.querySelectorAll('[data-marker]').forEach(b=>b.onclick=()=>markMemo(b.dataset.marker));
function memoInternalAction(mode){
 clearSearchHighlights();const range=memoActiveRange(mode!=='paste');
 if(mode==='copy'||mode==='cut'){
  if(!range||range.collapsed)return;
  memoInternalClipboard=range.toString();
  if(mode==='cut'){range.deleteContents();memoSavedRange=null;persistMemo()}
  window.getSelection()?.removeAllRanges();return;
 }
 if(!memoInternalClipboard)return;
 const target=range||document.createRange();
 if(!range){target.selectNodeContents($('memo-input'));target.collapse(false)}
 target.deleteContents();const text=document.createTextNode(memoInternalClipboard.slice(0,10000-($('memo-input').innerText||'').length));
 target.insertNode(text);target.setStartAfter(text);target.collapse(true);
 const sel=window.getSelection();sel.removeAllRanges();sel.addRange(target);memoSavedRange=target.cloneRange();persistMemo();$('memo-input').focus();
}
$('memo-cut').onclick=()=>memoInternalAction('cut');
$('memo-copy').onclick=()=>memoInternalAction('copy');
$('memo-paste').onclick=()=>memoInternalAction('paste');
$('memo-close').onclick=()=>$('memo-window').classList.remove('visible');
$('memo-transparent').onchange=e=>{$('memo-window').style.opacity=e.target.checked?'0.77':'1'};
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).classList.remove('visible'));
function toggleFloat(id){if(!running)return;$(id).classList.toggle('visible')}
for(const box of document.querySelectorAll('.floating')){const title=box.querySelector('.floattitle');let start=null;title.addEventListener('pointerdown',e=>{if(e.target.closest('button,label,input'))return;const b=box.getBoundingClientRect();start={x:e.clientX,y:e.clientY,left:b.left,top:b.top};if(box.id==='memo-window'){box.style.transform='none';box.style.left=b.left+'px';box.style.top=b.top+'px'}title.setPointerCapture(e.pointerId)});title.addEventListener('pointermove',e=>{if(!start)return;box.style.left=Math.max(0,Math.min(window.innerWidth-100,start.left+e.clientX-start.x))+'px';box.style.top=Math.max(0,Math.min(window.innerHeight-80,start.top+e.clientY-start.y))+'px';box.style.right='auto'});title.addEventListener('pointerup',()=>start=null);title.addEventListener('pointercancel',()=>start=null)}
let drag=null;$('splitter').onpointerdown=e=>{const w=$('workspace');drag={x:e.clientX,left:$('question-pane').getBoundingClientRect().width,total:w.getBoundingClientRect().width};$('splitter').setPointerCapture(e.pointerId)};
$('splitter').onpointermove=e=>{if(!drag||window.innerWidth<600)return;const px=clamp(drag.left+e.clientX-drag.x,250,drag.total-190);document.documentElement.style.setProperty('--left',px+'px')};
$('splitter').onpointerup=()=>drag=null;$('splitter').onpointercancel=()=>drag=null;

// ベストエフォートの試験中の操作制限。開発者ツール・画面撮影の阻止を保証しない。
for(const type of ['copy','cut','paste'])document.addEventListener(type,e=>{if(running){e.preventDefault();e.stopImmediatePropagation()}},true);
document.addEventListener('keydown',e=>{if(!running)return;
 const k=e.key.toLowerCase(),mod=e.ctrlKey||e.metaKey;
 if((mod&&['c','x','v'].includes(k))||(mod&&e.key==='Insert')||(e.shiftKey&&e.key==='Insert')||(e.shiftKey&&e.key==='Delete')){e.preventDefault();e.stopPropagation();return}
 if(mod&&k==='a'&&!e.target.closest('#memo-window')){e.preventDefault();e.stopPropagation();}
},true);
document.addEventListener('contextmenu',e=>{if(running)e.preventDefault()},true);
document.addEventListener('dragstart',e=>{if(running)e.preventDefault()},true);
document.addEventListener('selectstart',e=>{if(running&&e.target.closest('#question-pane,#answer-pane,#status-pane'))e.preventDefault()},true);

// 四則電卓：チュートリアルのキー配列・三段階サイズを再現する。
let display='0',acc=null,operator=null,needsNew=false;
const calcKeys=['±','AC','BS','÷','7','8','9','×','4','5','6','−','1','2','3','+','0','00','.','='];
for(const key of calcKeys){const b=document.createElement('button');b.type='button';b.textContent=key;
 if(['÷','×','−','+'].includes(key))b.className='op';if(key==='=')b.className='equal';
 b.addEventListener('click',()=>calcPress(key));$('calc-grid').appendChild(b)}
document.querySelectorAll('[data-calc-size]').forEach(b=>b.addEventListener('click',()=>{
 $('calc-window').dataset.size=b.dataset.calcSize;document.querySelectorAll('[data-calc-size]').forEach(x=>x.classList.toggle('active',x===b));
}));
function calcReset(){display='0';acc=null;operator=null;needsNew=false}
function calcPress(k){
 if(k==='AC')calcReset();
 else if(k==='BS'){if(needsNew){needsNew=false}display=display.length>1?(display.length===2&&display.startsWith('-')?'0':display.slice(0,-1)):'0'}
 else if(k==='±'){if(display!=='0'&&display!=='エラー')display=display.startsWith('-')?display.slice(1):'-'+display}
 else if((/^[0-9]$/.test(k))||k==='00'||k==='.'){if(display==='エラー')calcReset();if(needsNew){display='0';needsNew=false}
  if(k==='.'&&display.includes('.'))return;
  if(k==='.')display+='.';
  else if(display==='0')display=(k==='00'?'0':k);
  else if(display==='-0')display='-'+k;
  else display+=k;
  if(display.replace(/[^0-9]/g,'').length>13)display=display.slice(0,-k.length);
 }else if(['÷','×','−','+'].includes(k)){if(operator&&acc!==null&&!needsNew)calculate();else acc=Number(display);
   operator=k;needsNew=true;
 }else if(k==='='){if(operator&&acc!==null){calculate();operator=null;acc=null;needsNew=true}}
 $('calc-display').textContent=display;
}
function calculate(){const b=Number(display);let r=acc;if(operator==='+')r+=b;else if(operator==='−')r-=b;else if(operator==='×')r*=b;else if(operator==='÷')r=b===0?NaN:r/b;
 display=Number.isFinite(r)?String(Number(r.toPrecision(12))):'エラー';acc=Number(display)}
// 電卓が開いている間のみ数字キーを処理。メモや設定欄での入力は妨げない。
document.addEventListener('keydown',e=>{if(!running||!$('calc-window').classList.contains('visible')||e.target.closest('input,textarea,[contenteditable]')||e.ctrlKey||e.metaKey||e.altKey||e.isComposing)return;
 const keys={'*':'×','/':'÷','-':'−','Enter':'=','Backspace':'BS','Escape':'AC'};
 const key=keys[e.key]||e.key;if(calcKeys.includes(key)){e.preventDefault();calcPress(key)}},false);
// Initial boot
for(const raw of (window.AP_DEMO_SETS||[]))try{registerSet(raw,'demo')}catch(e){console.error('デモ問題の登録に失敗',e)}
if(restore()&&finished){refresh();showResults()}
else{running=false;finished=false;questions=[];answers=[];flags=[];current=0;refresh();showStart()}