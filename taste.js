const $ = s => document.querySelector(s);
const esc = value => String(value ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
let deck = null;
let selectedKey = null;
let sampleState = new Map();

const verdicts = [
  ['love','훨씬 더 보고 싶음','+3'],
  ['like','좋음','+1'],
  ['neutral','애매함','0'],
  ['dislike','별로','−1'],
  ['exclude','다시 추천하지 마','−3']
];

const reasons = [
  ['premise','소재'],['tone','톤'],['prose','문체'],['pacing','전개'],['protagonist','주인공'],
  ['characters','캐릭터'],['relationships','관계성'],['worldbuilding','세계관'],['system_rules','룰/시스템'],
  ['strategy','전략/추론'],['romance','로맨스'],['comedy','개그'],['darkness','어두움'],['slice_of_life','일상'],
  ['length','분량'],['freshness','신선도'],['ending','결말'],['genre_mix','장르혼합']
];

function toast(message, error=false) {
  const el = $('#toast');
  el.textContent = message;
  el.hidden = false;
  el.classList.toggle('error', error);
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { el.hidden = true; }, 2600);
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

function currentItem() {
  return (deck?.items || []).find(x => x.canonical_key === selectedKey) || null;
}

function renderDateOptions() {
  const select = $('#taste-date');
  select.innerHTML = (deck.available_dates || []).map(date => `<option value="${esc(date)}" ${date===deck.date?'selected':''}>${esc(date)}</option>`).join('');
  select.disabled = !(deck.available_dates || []).length;
}

function renderProgress() {
  const total = deck?.items?.length || 0;
  const done = deck?.completed_count || 0;
  $('#taste-progress-count').textContent = `${done} / ${total}`;
  $('#taste-progress-bar').style.width = total ? `${Math.round(done / total * 100)}%` : '0%';
  $('#taste-pool-count').textContent = `${total} / ${deck?.pool_count || total} works`;
  $('#taste-complete').hidden = !(total > 0 && done === total);
}

function renderQueue() {
  const list = $('#taste-queue-list');
  if (!deck?.items?.length) {
    list.innerHTML = '<div class="archive-state">이 날짜에 준비된 추천이 없다.</div>';
    return;
  }
  list.innerHTML = deck.items.map((item, index) => {
    const response = item.response;
    const active = item.canonical_key === selectedKey;
    return `<button class="taste-queue-item ${active?'active':''} ${response?'answered':''}" data-key="${esc(item.canonical_key)}">
      <span>${String(index+1).padStart(2,'0')}</span>
      <div><small>${esc(item.rank || item.platform || '')}</small><b>${esc(item.title)}</b><em>${esc(item.author || '')}</em></div>
      <i>${response ? esc(response.verdict).toUpperCase() : 'READ'}</i>
    </button>`;
  }).join('');
}

function sampleView(item) {
  const state = sampleState.get(item.canonical_key);
  if (!item.sample_available) {
    return `<div class="taste-sample-unavailable"><b>LOCAL SAMPLE NOT READY</b><p>아직 로컬 샘플이 준비되지 않았다. 원문 페이지에서 먼저 읽고 평가할 수 있다.</p>${item.url?`<a href="${esc(item.url)}" target="_blank" rel="noreferrer">원문에서 읽기 ↗</a>`:''}</div>`;
  }
  if (!state) return '<div class="taste-sample-loading">샘플을 불러오는 중.</div>';
  const ko = state.ko_text ? `<div class="taste-text-ko" data-reading="ko"><pre>${esc(state.ko_text)}</pre></div>` : '';
  const ja = `<div class="taste-text-ja ${state.ko_text?'secondary':''}" data-reading="ja"><pre>${esc(state.ja_text || '')}</pre></div>`;
  return `<div class="taste-reading-toolbar">
      <span>${state.ko_text ? '번역 샘플' : '일본어 원문 샘플'}</span>
      <b>${Number(state.end || 0).toLocaleString()} / ${Number(state.total || 0).toLocaleString()} chars</b>
    </div>${ko}${ja}${state.has_more?'<button class="taste-more" data-action="more">다음 부분 더 읽기</button>':''}`;
}

function renderReader() {
  const item = currentItem();
  if (!item) {
    $('#taste-reader').innerHTML = '<div class="archive-state">추천 작품이 없다.</div>';
    return;
  }
  $('#taste-reader').innerHTML = `<header class="taste-reader-head">
      <div class="taste-rank">${esc(item.rank || 'REC')}</div>
      <div><small>${esc(item.platform || '')} · ${Number(item.length_chars || 0).toLocaleString()}자${item.episodes?` · ${esc(item.episodes)}화`:''}</small><h2>${esc(item.title)}</h2><p>${esc(item.author || '')}</p></div>
      ${item.url?`<a href="${esc(item.url)}" target="_blank" rel="noreferrer">원문 ↗</a>`:''}
    </header>
    <div class="taste-sample" id="taste-sample">${sampleView(item)}</div>
    <details class="taste-rationale"><summary>추천 근거 보기 <span>평가 전에 안 보는 것을 권장</span></summary><div><b>왜 골랐나</b><p>${esc(item.why || '추천 근거가 기록되지 않았다.')}</p><b>기준과 다른 점</b><p>${esc(item.difference || '차이점이 기록되지 않았다.')}</p><small>${esc(item.entry_title || item.entry_id || '')}</small></div></details>`;
}

function renderAnswer() {
  const item = currentItem();
  if (!item) {
    $('#taste-answer').innerHTML = '<div class="taste-answer-empty">작품을 선택하면 답변란이 열린다.</div>';
    return;
  }
  const hasResponse = Boolean(item.response);
  const response = item.response || {};
  const selectedReasons = new Set(response.reasons || []);
  $('#taste-answer').innerHTML = `<div class="taste-answer-sticky">
    <header><span>YOUR ANSWER</span><b>${esc(item.title)}</b></header>
    <fieldset class="taste-verdicts"><legend>읽은 느낌</legend>${verdicts.map(([value,label,score])=>`<label class="verdict-${value}"><input type="radio" name="taste-verdict" value="${value}" ${response.verdict===value?'checked':''}><span><b>${label}</b><small>${score}</small></span></label>`).join('')}</fieldset>
    <fieldset class="taste-reason-grid"><legend>어떤 점 때문인가</legend>${reasons.map(([value,label])=>`<label><input type="checkbox" value="${value}" ${selectedReasons.has(value)?'checked':''}><span>${label}</span></label>`).join('')}</fieldset>
    <label class="taste-note"><span>한 줄 메모 · 선택</span><textarea id="taste-note" placeholder="예: 소재는 좋은데 주인공 말투가 너무 가벼움">${esc(response.note || '')}</textarea></label>
    <label class="taste-tags"><span>직접 태그 · 선택</span><input id="taste-tags" value="${esc((response.tags || []).join(', '))}" placeholder="건조한 문체, 여성 주인공"></label>
    <button class="control-button taste-save" id="taste-save">${hasResponse?'답변 수정':'답변 저장 · 다음 작품'}</button>
    <p class="taste-answer-note">이 답변은 취향 랭킹 신호로 쓰인다. MUST / MUST NOT은 자동 변경하지 않는다.</p>
  </div>`;
}

async function loadSample(key, append=false) {
  const current = sampleState.get(key);
  const start = append && current ? current.end : 0;
  const data = await api(`api/taste/read?date=${encodeURIComponent(deck.date)}&key=${encodeURIComponent(key)}&start=${start}`);
  if (append && current) {
    data.ja_text = [current.ja_text, data.ja_text].filter(Boolean).join('\n\n');
    data.ko_text = [current.ko_text, data.ko_text].filter(Boolean).join('\n\n');
    data.start = 0;
  }
  sampleState.set(key, data);
  if (selectedKey === key) renderReader();
}

function selectWork(key) {
  selectedKey = key;
  renderQueue();
  renderReader();
  renderAnswer();
  const item = currentItem();
  if (item?.sample_available && !sampleState.has(key)) loadSample(key).catch(error=>toast(error.message,true));
  if (window.innerWidth < 900) $('#taste-reader').scrollIntoView({behavior:'smooth', block:'start'});
}

function nextUnanswered(afterKey) {
  const items = deck?.items || [];
  const start = Math.max(0, items.findIndex(x=>x.canonical_key===afterKey));
  for (let offset=1; offset<=items.length; offset++) {
    const item = items[(start + offset) % items.length];
    if (!item.response) return item.canonical_key;
  }
  return afterKey;
}

async function saveAnswer() {
  const item = currentItem();
  const verdict = document.querySelector('input[name="taste-verdict"]:checked')?.value;
  if (!verdict) return toast('먼저 읽은 느낌을 하나 골라야 한다.', true);
  const checked = [...document.querySelectorAll('.taste-reason-grid input:checked')].map(x=>x.value);
  const tags = String($('#taste-tags')?.value || '').split(',').map(x=>x.trim()).filter(Boolean);
  const sample = sampleState.get(item.canonical_key);
  await api('api/taste/respond', {method:'POST', body:JSON.stringify({
    date:deck.date, canonical_key:item.canonical_key, entry_id:item.entry_id, profile_id:item.profile_id || null,
    verdict, reasons:checked, tags, note:$('#taste-note')?.value || '', read_chars:sample?.end || 0
  })});
  const previousKey = selectedKey;
  await loadDeck(deck.date, false);
  toast('답변 저장됨');
  selectWork(nextUnanswered(previousKey));
}

async function loadDeck(date=null, autoSelect=true) {
  const suffix = date ? `?date=${encodeURIComponent(date)}` : '';
  deck = await api(`api/taste/today${suffix}`);
  renderDateOptions();
  renderProgress();
  if (autoSelect || !deck.items.some(x=>x.canonical_key===selectedKey)) {
    selectedKey = (deck.items.find(x=>!x.response) || deck.items[0] || {}).canonical_key || null;
  }
  renderQueue(); renderReader(); renderAnswer();
  if (selectedKey) {
    const item=currentItem();
    if (item?.sample_available && !sampleState.has(selectedKey)) loadSample(selectedKey).catch(error=>toast(error.message,true));
  }
}

$('#taste-queue-list').addEventListener('click', event=>{
  const button = event.target.closest('[data-key]');
  if (button) selectWork(button.dataset.key);
});
$('#taste-date').addEventListener('change', event=>{ sampleState.clear(); selectedKey=null; loadDeck(event.target.value).catch(error=>toast(error.message,true)); });
$('#taste-reader').addEventListener('click', event=>{ if (event.target.dataset.action==='more') loadSample(selectedKey,true).catch(error=>toast(error.message,true)); });
$('#taste-answer').addEventListener('click', event=>{ if (event.target.id==='taste-save') saveAnswer().catch(error=>toast(error.message,true)); });

loadDeck().catch(error=>{
  $('#taste-reader').innerHTML = `<div class="archive-state error">PRIVATE RUNTIME ONLY · ${esc(error.message)}</div>`;
  $('#taste-answer').innerHTML = '<div class="taste-answer-empty">Tailscale private console에서 열어야 추천 원문과 피드백 API를 사용할 수 있다.</div>';
});
