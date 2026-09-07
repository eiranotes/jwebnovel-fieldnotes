const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = value => String(value ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
let state = null;
let writable = false;
let feedbackTargetKey = null;
let feedbackScope = '__global__';

const feedbackReasons = [
  ['premise','소재'],['tone','톤'],['prose','문체'],['pacing','전개'],['protagonist','주인공'],
  ['characters','캐릭터'],['relationships','관계성'],['romance','로맨스'],['worldbuilding','세계관'],
  ['system_rules','룰/시스템'],['strategy','전략/추론'],['comedy','개그'],['darkness','어두움'],
  ['slice_of_life','일상'],['length','분량'],['freshness','신선도'],['ending','결말'],['genre_mix','장르혼합']
];
const ratingToVerdict = {1:'exclude', 2:'dislike', 3:'neutral', 4:'like', 5:'love'};
const verdictToRating = {exclude:1, dislike:2, neutral:3, like:4, love:5};

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
    state = {profiles, work_index:works, full_translation:queue, logs, preference_feedback:{events:[]}, preference_model:{profiles:{}}, console:{writable:false}};
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
      <label class="profile-select"><input type="checkbox" data-role="selected" ${selected?'checked':''}><span>다음 탐색</span></label>
      <input data-field="name" class="profile-name" value="${esc(profile.name)}">
      <label class="toggle"><input type="checkbox" data-field="enabled" ${profile.enabled?'checked':''}><span>활성</span></label>
    </header>
    <div class="profile-grid">
      <label><span>플랫폼</span><input data-field="platforms" value="${esc(valueList(hard.platforms || ['Narou','Kakuyomu']))}"></label>
      <label><span>최소 분량 · 글자 수</span><input data-field="min_chars" type="number" value="${esc(hard.min_chars ?? 300000)}"></label>
      <label><span>추천 수</span><input data-field="shortlist_count" type="number" min="1" value="${esc(out.shortlist_count ?? 10)}"></label>
      <label><span>주인공</span><input data-field="protagonist" value="${esc(soft.protagonist||'')}" placeholder="예: 여성 주인공"></label>
      <label class="wide"><span>기준 작품 · 제목 | URL</span><textarea data-field="reference_works">${esc((profile.reference_works||[]).map(x=>typeof x==='string'?x:[x.title,x.url].filter(Boolean).join(' | ')).join('\n'))}</textarea></label>
      <label><span>장르</span><input data-field="genres" value="${esc(valueList(hard.genres))}"></label>
      <label><span>반드시 포함</span><input data-field="must" value="${esc(valueList(hard.must))}"></label>
      <label><span>제외 조건</span><input data-field="must_not" value="${esc(valueList(hard.must_not))}"></label>
      <label class="wide"><span>자유 조건</span><textarea data-field="intent" placeholder="작품 탐색 의도를 자연어로 적기">${esc(profile.intent||'')}</textarea></label>
      <div class="profile-preserved-fields" hidden>
        <input data-field="profile_id" value="${esc(profile.profile_id)}">
        <input data-field="serialization_priority" value="${esc(valueList(soft.serialization_priority))}">
        <input data-field="visibility" value="${esc(soft.visibility||'')}">
        <input data-field="freshness" value="${esc(soft.freshness||'')}">
        <input data-field="pov" value="${esc(soft.pov||'')}">
        <input data-field="romance_tolerance" value="${esc(soft.romance_tolerance||'')}">
        <input data-field="commercial_publication" value="${esc(hard.commercial_publication||'profile_specific')}">
        <input data-field="adult_r18" value="${esc(hard.adult_r18||'exclude')}">
        <input data-field="style" value="${esc(valueList(soft.style))}">
        <input data-field="pacing" value="${esc(valueList(soft.pacing))}">
        <input data-field="element_preferences" value="${esc(valueList(soft.element_preferences))}">
      </div>
    </div>
    <button class="text-button danger" data-action="remove-profile">삭제</button>
  </article>`;
}

function renderProfiles() {
  const config = state.profiles || {};
  const selection = config.selection || {};
  const selected = new Set(selection.selected_profile_ids || []);
  $('#fallback-mode').value = selection.when_none || 'round_robin';
  $('#explicit-mode').value = selection.explicit_selection_mode || 'once';
  $('#rotation-batch').value = selection.rotation_batch_size || 1;
  $('#profile-list').innerHTML = (config.profiles||[]).map(p=>profileCard(p,selected.has(p.profile_id))).join('') || '<div class="archive-state">조건 그룹이 없다.</div>';
  $$('#profile-list input, #profile-list textarea, #profile-list button, #fallback-mode, #explicit-mode, #rotation-batch, #save-selection, #save-profiles, #add-profile').forEach(el=>{ el.disabled=!writable; });
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
  const latestByKey = new Map();
  for (const event of state.preference_feedback?.events || []) latestByKey.set(event.canonical_key, event);
  $('#work-count').textContent = `${filtered.length} / ${works.length} works`;
  $('#work-index-list').innerHTML = filtered.map(w=>{
    const ft = w.full_translation || {};
    const badge = ft.status ? `<span class="status-badge">FULL · ${esc(ft.status)}</span>` : '';
    const feedback = latestByKey.get(w.canonical_key);
    const feedbackBadge = feedback ? `<span class="status-badge">TASTE · ${esc(feedback.verdict)}</span>` : '';
    const disabled = !writable || ['queued','acquiring','translation_pending','complete'].includes(ft.status);
    return `<article class="work-index-row"><div><small>${esc(w.platform||'UNKNOWN')} · SEEN ${esc(w.seen_count||1)}×</small><h3>${w.url?`<a href="${esc(w.url)}">${esc(w.title)}</a>`:esc(w.title)}</h3><p>${esc(w.author||'')} · ${Number(w.length_chars||0).toLocaleString()}자 · first ${esc(w.first_seen_entry)} / last ${esc(w.last_seen_entry)}</p></div><div class="work-actions">${feedbackBadge}${badge}<button class="control-button secondary compact" data-feedback-key="${esc(w.canonical_key)}">평가</button><button class="control-button compact" data-full-key="${esc(w.canonical_key)}" ${disabled?'disabled':''}>전체 번역</button></div></article>`;
  }).join('') || '<div class="archive-state">해당 작품이 없다.</div>';
}

function renderFeedback() {
  const events = state.preference_feedback?.events || [];
  const feedbackKeys = new Set(events.map(event=>event.canonical_key));
  const works = (state.work_index?.works || []).filter(work =>
    feedbackKeys.has(work.canonical_key) || (work.classifications || []).some(item=>['shortlist','length_exceptions'].includes(item.bucket))
  );
  const profiles = state.profiles?.profiles || [];
  const profileSelect = $('#feedback-profile');
  profileSelect.innerHTML = `<option value="__global__">전체 취향</option>` + profiles.map(p=>`<option value="${esc(p.profile_id)}" ${p.profile_id===feedbackScope?'selected':''}>${esc(p.name)}</option>`).join('');
  if (![...profileSelect.options].some(o=>o.value===feedbackScope)) feedbackScope='__global__';
  profileSelect.value = feedbackScope;

  const latestFeedback = key => events
    .filter(event => event.canonical_key === key && (feedbackScope === '__global__' ? !event.profile_id : event.profile_id === feedbackScope))
    .sort((a,b)=>String(b.timestamp||'').localeCompare(String(a.timestamp||'')))[0] || null;
  const dateFor = work => {
    const value = String(work.last_seen_entry || work.first_seen_entry || '');
    return value.match(/^\d{4}-\d{2}-\d{2}/)?.[0] || '날짜 미상';
  };
  const groups = new Map();
  for (const work of works) {
    const date = dateFor(work);
    if (!groups.has(date)) groups.set(date, []);
    groups.get(date).push(work);
  }
  const dates = [...groups.keys()].sort((a,b)=>{
    if (a === '날짜 미상') return 1;
    if (b === '날짜 미상') return -1;
    return b.localeCompare(a);
  });
  const targetDate = feedbackTargetKey ? dateFor(works.find(w=>w.canonical_key===feedbackTargetKey) || {}) : null;
  $('#feedback-list').innerHTML = dates.map((date, dateIndex) => {
    const rows = groups.get(date).sort((a,b)=>String(a.title||'').localeCompare(String(b.title||''), 'ja'));
    const open = targetDate ? date === targetDate : dateIndex === 0;
    return `<details class="feedback-day" ${open?'open':''}>
      <summary><span>${esc(date)}</span><b>${rows.length}편</b></summary>
      <div class="feedback-day-works">${rows.map(work=>{
        const response = latestFeedback(work.canonical_key);
        const rating = verdictToRating[response?.verdict] || 0;
        const selectedReasons = new Set(response?.reasons || []);
        const focused = work.canonical_key === feedbackTargetKey;
        return `<article class="feedback-work-card ${focused?'focused':''}" data-feedback-key="${esc(work.canonical_key)}" data-rating="${rating}">
          <header>
            <div class="feedback-work-title"><small>${esc(work.platform||'플랫폼 미상')}${work.author?` · ${esc(work.author)}`:''}</small><h3>${esc(work.title)}</h3></div>
            <div class="feedback-stars" role="radiogroup" aria-label="${esc(work.title)} 별점">${[1,2,3,4,5].map(value=>`<button type="button" data-feedback-rating="${value}" class="${value<=rating?'selected':''}" aria-label="${value}점" aria-pressed="${value===rating?'true':'false'}" ${!writable?'disabled':''}>★</button>`).join('')}</div>
          </header>
          <fieldset class="feedback-card-reasons"><legend>좋았거나 싫었던 이유</legend>${feedbackReasons.map(([value,label])=>`<label><input type="checkbox" data-feedback-reason value="${value}" ${selectedReasons.has(value)?'checked':''} ${!writable?'disabled':''}><span>${label}</span></label>`).join('')}</fieldset>
          <div class="feedback-card-foot">
            <label><span>자유 메모</span><textarea data-feedback-note placeholder="왜 좋았는지/싫었는지 자유롭게 메모" ${!writable?'disabled':''}>${esc(response?.note||'')}</textarea></label>
            <button type="button" class="control-button compact" data-save-feedback ${!writable?'disabled':''}>${response?'평가 수정':'평가 저장'}</button>
          </div>
        </article>`;
      }).join('')}</div>
    </details>`;
  }).join('') || '<div class="archive-state">평가할 작품이 없다.</div>';

  const model = state.preference_model?.profiles?.[feedbackScope] || {event_count:0,signals:[],suggestions:[],positive_examples:[],negative_examples:[]};
  $('#learning-scope-title').textContent = `${feedbackScope==='__global__'?'전체 취향':profileSelect.selectedOptions[0]?.textContent || feedbackScope} · ${model.event_count||0}개 평가`;
  $('#learning-signals').innerHTML = (model.signals||[]).map(x=>`<article class="signal-row"><b>${esc(x.reason)}</b><span>${Number(x.score||0)>0?'+':''}${esc(x.score||0)}</span><small>${esc(x.count||0)}회 · 신뢰도 ${Math.round(Number(x.confidence||0)*100)}%</small></article>`).join('') || '<div class="archive-state">아직 학습 신호가 없다.</div>';
  if (feedbackScope === '__global__') {
    $('#learning-suggestions').innerHTML = '<div class="archive-state">조건 반영은 특정 프로필을 선택하면 표시된다. 전체 취향 신호는 모든 프로필 랭킹에 기본 반영된다.</div>';
  } else {
    $('#learning-suggestions').innerHTML = (model.suggestions||[]).map(x=>`<article class="suggestion-row"><div><small>조건 반영 제안 · ${esc(x.direction)}</small><b>${esc(x.reason)}</b><p>${esc(x.evidence_count)}개 근거 · 평균 ${esc(x.average_score)} · 신뢰도 ${Math.round(Number(x.confidence||0)*100)}%</p></div><button class="control-button secondary compact" data-apply-signal="${esc(x.reason)}" data-direction="${esc(x.direction)}" ${!writable?'disabled':''}>조건에 반영</button></article>`).join('') || '<div class="archive-state">승인 대기 변경안이 없다.</div>';
  }
  profileSelect.disabled = !writable;
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
  const rows = (state.artifacts || []).filter(row=>String(row.filename||'').endsWith(' - 번역본.txt'));
  $('#artifact-list').innerHTML = rows.map(row=>`<article class="artifact-row"><div><small>교차 번역</small><h3>${esc(row.title||row.work_id||'artifact')}</h3><p>${Number(row.size||0).toLocaleString()} bytes</p></div><div class="artifact-links">${writable?`<a href="api/download?path=${encodeURIComponent(row.path)}">${esc(row.filename)}</a>`:`<span>${esc(row.filename)}</span>`}</div></article>`).join('') || '<div class="archive-state">완료된 교차 번역본이 아직 없다.</div>';
}

function renderAll(){ renderProfiles(); renderFeedback(); renderWorks(); renderFullQueue(); renderLogs(); renderArtifacts(); }

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
    await api('api/selection',{method:'POST',body:JSON.stringify({selected_profile_ids:selected,explicit_selection_mode:$('#explicit-mode').value,when_none:$('#fallback-mode').value,rotation_batch_size:Number($('#rotation-batch').value||1)})});
    toast(`다음 탐색 선택 저장: ${selected.length?selected.length+'개':'fallback'}`);
    await loadState();
  } catch(error){ toast(error.message,true); }
});

$('#work-filter').addEventListener('input',renderWorks);
$('#log-filter').addEventListener('input',renderLogs);

$('#work-index-list').addEventListener('click',async event=>{
  const feedbackKey=event.target.dataset.feedbackKey;
  if(feedbackKey){
    feedbackTargetKey=feedbackKey;
    renderFeedback();
    activateTab('feedback');
    return;
  }
  const key=event.target.dataset.fullKey;
  if(!key) return;
  try{
    await api('api/full-translation/request',{method:'POST',body:JSON.stringify({canonical_key:key})});
    toast('전체 번역 큐에 등록됨');
    await loadState();
    activateTab('full');
  }catch(error){toast(error.message,true);}
});

$('#feedback-profile').addEventListener('change',event=>{ feedbackScope=event.target.value; renderFeedback(); });

$('#feedback-list').addEventListener('click',async event=>{
  const card = event.target.closest('.feedback-work-card');
  if (!card) return;
  const ratingButton = event.target.closest('[data-feedback-rating]');
  if (ratingButton) {
    const rating = Number(ratingButton.dataset.feedbackRating || 0);
    card.dataset.rating = String(rating);
    card.querySelectorAll('[data-feedback-rating]').forEach(button=>{
      const value = Number(button.dataset.feedbackRating || 0);
      button.classList.toggle('selected', value <= rating);
      button.setAttribute('aria-pressed', value === rating ? 'true' : 'false');
    });
    return;
  }
  const saveButton = event.target.closest('[data-save-feedback]');
  if (!saveButton) return;
  const rating = Number(card.dataset.rating || 0);
  if (!ratingToVerdict[rating]) return toast('별점을 먼저 선택해 주세요.', true);
  try {
    saveButton.disabled = true;
    const reasons = [...card.querySelectorAll('[data-feedback-reason]:checked')].map(x=>x.value);
    const note = card.querySelector('[data-feedback-note]')?.value || '';
    feedbackTargetKey = card.dataset.feedbackKey;
    await api('api/feedback',{method:'POST',body:JSON.stringify({
      canonical_key:feedbackTargetKey,
      profile_id:feedbackScope==='__global__'?null:feedbackScope,
      verdict:ratingToVerdict[rating], reasons, tags:[], note
    })});
    toast(`${rating}점 평가 저장됨`);
    await loadState();
    activateTab('feedback');
  } catch(error) {
    saveButton.disabled = false;
    toast(error.message,true);
  }
});

$('#learning-suggestions').addEventListener('click',async event=>{
  const signal=event.target.dataset.applySignal;
  if(!signal) return;
  try{
    await api('api/feedback/apply',{method:'POST',body:JSON.stringify({profile_id:feedbackScope,signal,direction:event.target.dataset.direction})});
    toast('학습 제안을 탐색 조건에 반영함');
    await loadState();
    activateTab('feedback');
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
