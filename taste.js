const $ = s => document.querySelector(s);
const esc = value => String(value ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
let deck = null;
let selectedKey = null;
let sampleState = new Map();

const ratingToVerdict = {1:'exclude',2:'dislike',3:'neutral',4:'like',5:'love'};
const verdictToRating = {exclude:1,dislike:2,neutral:3,like:4,love:5};

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

function atomChip(atom) {
  const positive = Number(atom?.polarity || 0) > 0;
  return `<span class="preference-atom ${positive?'positive':'negative'}" title="${esc(atom?.evidence||'')}">${esc(atom?.label || atom?.key || '')}<b>${positive?'+':'−'}</b></span>`;
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
  return (deck?.items || []).find(x => x.review_key === selectedKey) || null;
}

function renderDateOptions() {
  const select = $('#taste-date');
  select.innerHTML = (deck.available_dates || []).map(date => `<option value="${esc(date)}" ${date===deck.date?'selected':''}>${esc(date)}</option>`).join('');
  select.disabled = !(deck.available_dates || []).length;
}

function renderTransferLinks() {
  if (!deck?.date) return;
  const base = `api/taste/bundle?date=${encodeURIComponent(deck.date)}`;
  $('#taste-txt').href = `${base}&format=txt`;
  $('#taste-zip').href = `${base}&format=zip`;
  const root = `${location.origin}${location.pathname.includes('/fieldnotes/') ? '/fieldnotes' : ''}`;
  $('#taste-webdav-url').value = `${root}/dav/`;
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
    const active = item.review_key === selectedKey;
    return `<button class="taste-queue-item ${active?'active':''} ${response?'answered':''}" data-key="${esc(item.review_key)}">
      <span>${String(index+1).padStart(2,'0')}</span>
      <div><small>${esc(item.rank || item.platform || '')}</small><b>${esc(item.title)}</b><em>${esc(item.author || '')}</em></div>
      <i>${response ? esc(response.verdict).toUpperCase() : 'READ'}</i>
    </button>`;
  }).join('');
}

function sampleView(item) {
  const state = sampleState.get(item.review_key);
  if (!item.sample_available) {
    return `<div class="taste-sample-unavailable"><b>교차 번역 준비 중</b><p>번역 완료 뒤 이 목록에 표시된다.</p></div>`;
  }
  if (!state) return '<div class="taste-sample-loading">샘플을 불러오는 중.</div>';
  const alternatingHtml = text => String(text || '').trim().split(/\n\s*\n+/).filter(Boolean).map((block, index) => {
    const lines = block.split('\n').map(x=>x.trimEnd()).filter(x=>x.trim());
    if (!lines.length) return '';
    const ja = lines[0];
    const ko = lines.slice(1).join('\n');
    return `<section class="taste-pair" data-pair="${index+1}">
      <p class="taste-pair-ja" lang="ja">${esc(ja)}</p>
      ${ko?`<p class="taste-pair-ko" lang="ko">${esc(ko)}</p>`:''}
    </section>`;
  }).join('');
  const body = state.reading_mode === 'alternating'
    ? `<div class="taste-text-alternating" data-reading="alternating">${alternatingHtml(state.text)}</div>`
    : `<div class="taste-text-ja" data-reading="ja"><pre>${esc(state.ja_text || '')}</pre></div>`;
  return `<div class="taste-reading-toolbar">
      <span>${state.reading_mode === 'alternating' ? '원문 · 번역 교차본' : '일본어 원문 샘플'}</span>
      <b>${Number(state.end || 0).toLocaleString()} / ${Number(state.total || 0).toLocaleString()} chars</b>
    </div>${body}${state.has_more?'<button class="taste-more" data-action="more">다음 부분 더 읽기</button>':''}`;
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
  const rating = verdictToRating[response.verdict] || 0;
  const selectedReasons = new Set(response.reasons || []);
  const atoms = response.atoms || [];
  $('#taste-answer').innerHTML = `<div class="taste-answer-sticky">
    <header><span>YOUR ANSWER</span><b>${esc(item.title)}</b></header>
    <div class="taste-star-rating" data-rating="${rating}"><span>탐색 적중도</span><div role="radiogroup" aria-label="${esc(item.title)} 별점">${[1,2,3,4,5].map(value=>`<button type="button" data-taste-rating="${value}" class="${value<=rating?'selected':''}" aria-label="${value}점" aria-pressed="${value===rating?'true':'false'}">★</button>`).join('')}</div><small>1 다시 추천하지 않음 · 3 애매 · 5 정확히 맞음</small></div>
    <label class="taste-note"><span>자유 메모 · 핵심 학습 입력</span><textarea id="taste-note" placeholder="예: 빠르고 다음 화가 궁금함. 캐릭터는 경파해서 좋음 / 묘사는 그럴듯한데 주인공 설득력이 약함">${esc(response.note || '')}</textarea></label>
    ${atoms.length?`<div class="taste-atom-preview"><span>현재 학습됨</span><div>${atoms.map(atomChip).join('')}</div></div>`:''}
    <details class="taste-optional-feedback"><summary>세부 이유 / 직접 태그 · 선택</summary><fieldset class="taste-reason-grid"><legend>어떤 점 때문인가</legend>${reasons.map(([value,label])=>`<label><input type="checkbox" value="${value}" ${selectedReasons.has(value)?'checked':''}><span>${label}</span></label>`).join('')}</fieldset><label class="taste-tags"><span>직접 태그</span><input id="taste-tags" value="${esc((response.tags || []).join(', '))}" placeholder="건조한 문체, 여성 주인공"></label></details>
    <button class="control-button taste-save" id="taste-save">${hasResponse?'답변 수정':'답변 저장 · 다음 작품'}</button>
    <p class="taste-answer-note">별점은 작품 보상, 메모는 세부 취향 신호로 저장된다. 같은 조사 안의 별점 차이는 pairwise 학습에 추가된다.</p>
  </div>`;
}

async function loadSample(key, append=false) {
  const current = sampleState.get(key);
  const start = append && current ? current.end : 0;
  const data = await api(`api/taste/read?date=${encodeURIComponent(deck.date)}&key=${encodeURIComponent(key)}&start=${start}`);
  if (append && current) {
    if (data.reading_mode === 'alternating') data.text = [current.text, data.text].filter(Boolean).join('\n\n');
    else data.ja_text = [current.ja_text, data.ja_text].filter(Boolean).join('\n\n');
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
  const start = Math.max(0, items.findIndex(x=>x.review_key===afterKey));
  for (let offset=1; offset<=items.length; offset++) {
    const item = items[(start + offset) % items.length];
    if (!item.response) return item.review_key;
  }
  return afterKey;
}

async function saveAnswer() {
  const item = currentItem();
  const rating = Number(document.querySelector('.taste-star-rating')?.dataset.rating || 0);
  const verdict = ratingToVerdict[rating];
  if (!verdict) return toast('먼저 별점을 골라야 한다.', true);
  const checked = [...document.querySelectorAll('.taste-reason-grid input:checked')].map(x=>x.value);
  const tags = String($('#taste-tags')?.value || '').split(',').map(x=>x.trim()).filter(Boolean);
  const sample = sampleState.get(item.review_key);
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
  renderTransferLinks();
  renderProgress();
  if (autoSelect || !deck.items.some(x=>x.review_key===selectedKey)) {
    selectedKey = (deck.items.find(x=>!x.response) || deck.items[0] || {}).review_key || null;
  }
  renderQueue(); renderReader(); renderAnswer();
  if (selectedKey) {
    const item=currentItem();
    if (item?.sample_available && !sampleState.has(selectedKey)) loadSample(selectedKey).catch(error=>toast(error.message,true));
  }
}

async function shareToday() {
  if (!deck?.date) return toast('오늘 추천이 없다.', true);
  const url = `api/taste/bundle?date=${encodeURIComponent(deck.date)}&format=txt`;
  const response = await fetch(url, {cache:'no-store'});
  if (!response.ok) throw new Error(`TXT 생성 실패: ${response.status}`);
  const blob = await response.blob();
  const file = new File([blob], `fieldnotes-${deck.date}-daily-taste.txt`, {type:'text/plain'});
  if (navigator.share && (!navigator.canShare || navigator.canShare({files:[file]}))) {
    await navigator.share({title:`Field Notes ${deck.date}`, text:'오늘의 추천 소설 모음', files:[file]});
    return;
  }
  location.href = url;
  toast('공유 시트를 지원하지 않아 TXT 다운로드로 전환함');
}

$('#taste-queue-list').addEventListener('click', event=>{
  const button = event.target.closest('[data-key]');
  if (button) selectWork(button.dataset.key);
});
$('#taste-date').addEventListener('change', event=>{ sampleState.clear(); selectedKey=null; loadDeck(event.target.value).catch(error=>toast(error.message,true)); });
$('#taste-reader').addEventListener('click', event=>{ if (event.target.dataset.action==='more') loadSample(selectedKey,true).catch(error=>toast(error.message,true)); });
$('#taste-answer').addEventListener('click', event=>{
  const star = event.target.closest('[data-taste-rating]');
  if (star) {
    const rating = Number(star.dataset.tasteRating || 0);
    const box = star.closest('.taste-star-rating');
    box.dataset.rating = String(rating);
    box.querySelectorAll('[data-taste-rating]').forEach(button=>{
      const value = Number(button.dataset.tasteRating || 0);
      button.classList.toggle('selected', value <= rating);
      button.setAttribute('aria-pressed', value === rating ? 'true' : 'false');
    });
    return;
  }
  if (event.target.id==='taste-save') saveAnswer().catch(error=>toast(error.message,true));
});
$('#taste-share').addEventListener('click', ()=>shareToday().catch(error=>{
  if (error?.name !== 'AbortError') toast(error.message,true);
}));
$('#taste-copy-webdav').addEventListener('click', async ()=>{
  try {
    await navigator.clipboard.writeText($('#taste-webdav-url').value);
    toast('WebDAV 주소 복사됨');
  } catch {
    $('#taste-webdav-url').select();
    document.execCommand('copy');
    toast('WebDAV 주소 복사됨');
  }
});

loadDeck().catch(error=>{
  $('#taste-reader').innerHTML = `<div class="archive-state error">PRIVATE RUNTIME ONLY · ${esc(error.message)}</div>`;
  $('#taste-answer').innerHTML = '<div class="taste-answer-empty">Tailscale private console에서 열어야 추천 원문과 피드백 API를 사용할 수 있다.</div>';
});
