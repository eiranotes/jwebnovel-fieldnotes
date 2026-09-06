const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = value => String(value ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
let state = null;
let writable = false;

function toast(message, error=false) {
  const el = $('#toast');
  el.textContent = message;
  el.hidden = false;
  el.classList.toggle('error', error);
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { el.hidden = true; }, 3200);
}

async function api(path, options={}) {
  const response = await fetch(path, {cache:'no-store', headers:{'Content-Type':'application/json'}, ...options});
  if (!response.ok) {
    let message = `${response.status}`;
    try { message = (await response.json()).error || message; } catch {}
    throw new Error(message);
  }
  return response.json();
}

async function loadState() {
  try {
    state = await api('api/state');
    writable = true;
    $('#console-mode').textContent = 'PRIVATE / WRITABLE';
  } catch {
    writable = false;
    $('#console-mode').textContent = 'PUBLIC / READ ONLY';
    const [profiles, works, queue, logs] = await Promise.all([
      fetch('config/search-profiles.json').then(r=>r.json()),
      fetch('data/work-index.json').then(r=>r.json()),
      fetch('data/full-translation-queue.json').then(r=>r.json()),
      fetch('data/automation-logs.json').then(r=>r.json())
    ]);
    state = {profiles, work_index:works, full_translation:queue, logs, console:{writable:false}};
  }
  renderAll();
}

function valueList(value) { return Array.isArray(value) ? value.join(', ') : (value || ''); }
function splitList(value) { return String(value||'').split(/[,\n]/).map(x=>x.trim()).filter(Boolean); }

function profileCard(profile, selected) {
  const hard = profile.hard_filters || {};
  const soft = profile.soft_preferences || {};
  const out = profile.output || {};
  return `<article class="profile-card" data-id="${esc(profile.profile_id)}">
    <header>
      <label class="profile-select"><input type="checkbox" data-role="selected" ${selected?'checked':''}><span>NEXT SEARCH</span></label>
      <input data-field="name" class="profile-name" value="${esc(profile.name)}">
      <label class="toggle"><input type="checkbox" data-field="enabled" ${profile.enabled?'checked':''}><span>ACTIVE</span></label>
    </header>
    <div class="profile-grid">
      <label><span>PROFILE ID</span><input data-field="profile_id" value="${esc(profile.profile_id)}"></label>
      <label><span>PLATFORMS</span><input data-field="platforms" value="${esc(valueList(hard.platforms || ['Narou','Kakuyomu']))}"></label>
      <label><span>MIN CHARS</span><input data-field="min_chars" type="number" value="${esc(hard.min_chars ?? 300000)}"></label>
      <label><span>SHORTLIST</span><input data-field="shortlist_count" type="number" min="1" value="${esc(out.shortlist_count ?? 10)}"></label>
      <label class="wide"><span>REFERENCE WORKS · title | url</span><textarea data-field="reference_works">${esc((profile.reference_works||[]).map(x=>typeof x==='string'?x:[x.title,x.url].filter(Boolean).join(' | ')).join('\n'))}</textarea></label>
      <label><span>GENRES</span><input data-field="genres" value="${esc(valueList(hard.genres))}"></label>
      <label><span>MUST</span><input data-field="must" value="${esc(valueList(hard.must))}"></label>
      <label><span>MUST NOT</span><input data-field="must_not" value="${esc(valueList(hard.must_not))}"></label>
      <label><span>STATUS PRIORITY</span><input data-field="serialization_priority" value="${esc(valueList(soft.serialization_priority))}" placeholder="ongoing, completed"></label>
      <label><span>VISIBILITY</span><input data-field="visibility" value="${esc(soft.visibility||'')}"></label>
      <label><span>FRESHNESS</span><input data-field="freshness" value="${esc(soft.freshness||'')}"></label>
      <label><span>PROTAGONIST</span><input data-field="protagonist" value="${esc(soft.protagonist||'')}"></label>
      <label><span>POV</span><input data-field="pov" value="${esc(soft.pov||'')}"></label>
      <label><span>ROMANCE</span><input data-field="romance_tolerance" value="${esc(soft.romance_tolerance||'')}"></label>
      <label><span>PUBLICATION</span><select data-field="commercial_publication"><option value="profile_specific" ${hard.commercial_publication==='profile_specific'?'selected':''}>조건별 판단</option><option value="exclude" ${hard.commercial_publication==='exclude'?'selected':''}>출판작 제외</option><option value="allow" ${hard.commercial_publication==='allow'?'selected':''}>허용</option><option value="deprioritize" ${hard.commercial_publication==='deprioritize'?'selected':''}>우선순위 하향</option></select></label>
      <label><span>R18</span><select data-field="adult_r18"><option value="exclude" ${hard.adult_r18!=='allow'?'selected':''}>제외</option><option value="allow" ${hard.adult_r18==='allow'?'selected':''}>허용</option></select></label>
      <label><span>STYLE</span><input data-field="style" value="${esc(valueList(soft.style))}"></label>
      <label><span>PACING</span><input data-field="pacing" value="${esc(valueList(soft.pacing))}"></label>
      <label class="wide"><span>ELEMENT PREFERENCES</span><input data-field="element_preferences" value="${esc(valueList(soft.element_preferences))}"></label>
      <label class="wide"><span>FREEFORM INTENT</span><textarea data-field="intent">${esc(profile.intent||'')}</textarea></label>
    </div>
    <button class="text-button danger" data-action="remove-profile">삭제</button>
  </article>`;
}

function renderProfiles() {
  const config = state.profiles || {};
  const selection = config.selection || {};
  const selected = new Set(selection.selected_profile_ids || []);
  $('#fallback-mode').value = selection.when_none || 'round_robin';
  $('#rotation-batch').value = selection.rotation_batch_size || 1;
  $('#profile-list').innerHTML = (config.profiles||[]).map(p=>profileCard(p,selected.has(p.profile_id))).join('') || '<div class="archive-state">조건 그룹이 없다.</div>';
  $$('#profile-list input, #profile-list textarea, #profile-list button, #fallback-mode, #rotation-batch, #save-selection, #save-profiles, #add-profile').forEach(el=>{ el.disabled=!writable; });
}

function collectProfiles() {
  const original = structuredClone(state.profiles);
  original.profiles = $$('.profile-card').map(card => {
    const get = field => card.querySelector(`[data-field="${field}"]`);
    const refs = get('reference_works').value.split('\n').map(x=>x.trim()).filter(Boolean).map(line=>{
      const [title,url] = line.split('|').map(x=>x.trim());
      return url ? {title,url} : title;
    });
    const old = (state.profiles.profiles||[]).find(x=>x.profile_id===card.dataset.id) || {};
    return {
      ...old,
      profile_id:get('profile_id').value.trim(), name:get('name').value.trim(), enabled:get('enabled').checked,
      intent:get('intent').value.trim(), reference_works:refs,
      hard_filters:{...(old.hard_filters||{}), platforms:splitList(get('platforms').value), min_chars:Number(get('min_chars').value||0), genres:splitList(get('genres').value), must:splitList(get('must').value), must_not:splitList(get('must_not').value), commercial_publication:get('commercial_publication').value, adult_r18:get('adult_r18').value},
      soft_preferences:{...(old.soft_preferences||{}), serialization_priority:splitList(get('serialization_priority').value), visibility:get('visibility').value.trim()||null, freshness:get('freshness').value.trim()||null, protagonist:get('protagonist').value.trim()||null, pov:get('pov').value.trim()||null, romance_tolerance:get('romance_tolerance').value.trim()||null, style:splitList(get('style').value), pacing:splitList(get('pacing').value), element_preferences:splitList(get('element_preferences').value)},
      output:{...(old.output||{}), shortlist_count:Number(get('shortlist_count').value||10)}
    };
  });
  return original;
}

function renderWorks() {
  const works = state.work_index?.works || [];
  const query = ($('#work-filter')?.value||'').toLowerCase();
  const filtered = works.filter(w=>!query || [w.title,w.author,w.platform,w.url,w.canonical_key].join(' ').toLowerCase().includes(query));
  $('#work-count').textContent = `${filtered.length} / ${works.length} works`;
  $('#work-index-list').innerHTML = filtered.map(w=>{
    const ft = w.full_translation || {};
    const badge = ft.status ? `<span class="status-badge">FULL · ${esc(ft.status)}</span>` : '';
    const disabled = !writable || ['queued','acquiring','translation_pending','complete'].includes(ft.status);
    return `<article class="work-index-row"><div><small>${esc(w.platform||'UNKNOWN')} · SEEN ${esc(w.seen_count||1)}×</small><h3>${w.url?`<a href="${esc(w.url)}">${esc(w.title)}</a>`:esc(w.title)}</h3><p>${esc(w.author||'')} · ${Number(w.length_chars||0).toLocaleString()}자 · first ${esc(w.first_seen_entry)} / last ${esc(w.last_seen_entry)}</p></div><div class="work-actions">${badge}<button class="control-button compact" data-full-key="${esc(w.canonical_key)}" ${disabled?'disabled':''}>전체 번역</button></div></article>`;
  }).join('') || '<div class="archive-state">해당 작품이 없다.</div>';
}

function renderFullQueue() {
  const requests = [...(state.full_translation?.requests||[])].reverse();
  $('#full-queue-list').innerHTML = requests.map(r=>`<article class="queue-row"><div><small>${esc(r.request_id)}</small><h3>${esc(r.title)}</h3><p>${esc(r.platform||'')} · ${esc(r.status)} · ${esc(r.acquired_episodes||0)}/${esc(r.available_episodes||'?')}화</p></div><div class="queue-progress"><b>${esc(r.chunks_done||0)} / ${esc(r.chunks_total||0)}</b><span>CHUNKS</span></div></article>`).join('') || '<div class="archive-state">전체 번역 요청이 없다.</div>';
  $('#run-next-full').disabled=!writable || !requests.some(r=>['queued','acquisition_error'].includes(r.status));
}

function renderLogs() {
  const query = ($('#log-filter')?.value||'').toLowerCase();
  const entries = [...(state.logs?.entries||[])].reverse().filter(x=>!query||JSON.stringify(x).toLowerCase().includes(query));
  $('#console-log-list').innerHTML = entries.map(x=>`<article class="log-row ${esc(x.status)}"><time>${esc((x.timestamp||'').replace('T',' ').slice(0,19))}</time><b>${esc(x.task)} · ${esc(x.action)}</b><span>${esc(x.status)}</span><p>${esc(x.message||'')}</p><small>${esc(x.run_id)}</small></article>`).join('') || '<div class="archive-state">로그가 없다.</div>';
}

function renderArtifacts() {
  const rows = state.artifacts || [];
  $('#artifact-list').innerHTML = rows.map(row=>`<article class="artifact-row"><div><small>${esc(row.kind)}</small><h3>${esc(row.title||row.work_id||'artifact')}</h3><p>${Number(row.size||0).toLocaleString()} bytes</p></div><div class="artifact-links">${writable?`<a href="api/download?path=${encodeURIComponent(row.path)}">${esc(row.filename)}</a>`:`<span>${esc(row.filename)}</span>`}</div></article>`).join('') || '<div class="archive-state">받을 수 있는 로컬 작업물이 아직 없다.</div>';
}

function renderAll(){ renderProfiles(); renderWorks(); renderFullQueue(); renderLogs(); renderArtifacts(); }

function activateTab(name){
  $$('.control-tabs button').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));
  $$('.control-section').forEach(p=>p.classList.toggle('active',p.dataset.panel===name));
  history.replaceState(null,'',`#${name}`);
}

$$('.control-tabs button').forEach(b=>b.addEventListener('click',()=>activateTab(b.dataset.tab)));
activateTab(location.hash.slice(1)||'profiles');

$('#add-profile').addEventListener('click',()=>{
  const id=`profile-${Date.now().toString(36)}`;
  state.profiles.profiles.push({profile_id:id,name:'새 탐색 조건',enabled:true,reference_works:[],hard_filters:{platforms:['Narou','Kakuyomu'],min_chars:300000,genres:[],must:[],must_not:[],commercial_publication:'profile_specific',adult_r18:'exclude'},soft_preferences:{serialization_priority:[],freshness:null,visibility:null,protagonist:null,pov:null,style:[],pacing:[],romance_tolerance:null,element_preferences:[]},output:{shortlist_count:10,source_pipeline_top_n:5,length_exception_max:2,when_candidates_are_insufficient:'output_fewer_and_report_gap'},translation:{enqueue_top_n:true,priority:'oldest_pending_first'}});
  renderProfiles();
});

$('#profile-list').addEventListener('click',event=>{
  if(event.target.dataset.action==='remove-profile'){
    const card=event.target.closest('.profile-card');
    state.profiles.profiles=state.profiles.profiles.filter(p=>p.profile_id!==card.dataset.id);
    renderProfiles();
  }
});

$('#save-profiles').addEventListener('click',async()=>{
  try{ state.profiles=await api('api/profiles',{method:'POST',body:JSON.stringify(collectProfiles())}); renderProfiles(); toast('탐색 조건 저장됨'); }
  catch(error){ toast(error.message,true); }
});

$('#save-selection').addEventListener('click',async()=>{
  try{
    const config=collectProfiles();
    state.profiles=await api('api/profiles',{method:'POST',body:JSON.stringify(config)});
    const selected=$$('.profile-card').filter(c=>c.querySelector('[data-role="selected"]').checked).map(c=>c.querySelector('[data-field="profile_id"]').value.trim());
    await api('api/selection',{method:'POST',body:JSON.stringify({selected_profile_ids:selected,when_none:$('#fallback-mode').value,rotation_batch_size:Number($('#rotation-batch').value||1)})});
    toast(`다음 탐색 선택 저장: ${selected.length?selected.length+'개':'fallback'}`);
    await loadState();
  } catch(error){ toast(error.message,true); }
});

$('#work-filter').addEventListener('input',renderWorks);
$('#log-filter').addEventListener('input',renderLogs);

$('#work-index-list').addEventListener('click',async event=>{
  const key=event.target.dataset.fullKey;
  if(!key) return;
  try{
    await api('api/full-translation/request',{method:'POST',body:JSON.stringify({canonical_key:key})});
    toast('전체 번역 큐에 등록됨');
    await loadState();
    activateTab('full');
  }catch(error){toast(error.message,true);}
});

$('#run-next-full').addEventListener('click',async()=>{
  try{
    toast('전체 원문 준비 작업을 시작함');
    await api('api/full-translation/run-next',{method:'POST',body:'{}'});
    $('#run-next-full').disabled=true;
    setTimeout(()=>loadState().catch(()=>{}),1800);
  }catch(error){toast(error.message,true);}
});

loadState().catch(error=>toast(error.message,true));
