const archiveRoot = document.querySelector('#archive');
const queryInput = document.querySelector('#archive-filter');
const dateSelect = document.querySelector('#date-filter');

let entries = [];

const esc = value => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;');

function searchable(entry) {
  return [
    entry.entry_id,
    entry.date,
    entry.title,
    entry.summary,
    ...(entry.reference_works || []),
    ...(entry.criteria_terms || []),
    ...(entry.platforms || []),
    ...(entry.genres || [])
  ].join(' ').toLowerCase();
}

function lengthLabel(entry) {
  if (!entry.min_chars) return 'length open';
  const base = `${Number(entry.min_chars).toLocaleString()}자+`;
  return entry.length_policy === 'default_with_high_fit_exception' ? `${base} · EXC` : base;
}

function render() {
  const q = queryInput.value.trim().toLowerCase();
  const selectedDate = dateSelect.value;
  const filtered = entries.filter(entry => {
    const matchesDate = !selectedDate || entry.date === selectedDate;
    const matchesQuery = !q || searchable(entry).includes(q);
    return matchesDate && matchesQuery;
  });

  if (!filtered.length) {
    archiveRoot.innerHTML = '<div class="archive-state">해당 조건의 조사 기록이 없다.</div>';
    return;
  }

  const groups = filtered.reduce((acc, entry) => {
    (acc[entry.date] ||= []).push(entry);
    return acc;
  }, {});

  archiveRoot.innerHTML = Object.keys(groups)
    .sort((a, b) => b.localeCompare(a))
    .map(date => {
      const dayEntries = groups[date].sort((a, b) => a.sequence - b.sequence);
      const dayNav = dayEntries.map(entry => `
        <a href="${esc(entry.page)}" title="${esc(entry.title)}">
          <b>${esc(String(entry.sequence).padStart(2, '0'))}</b><span>${esc(entry.title)}</span>
        </a>
      `).join('');
      const rows = [...dayEntries]
        .sort((a, b) => b.sequence - a.sequence)
        .map(entry => `
          <article class="archive-entry">
            <div class="entry-id"><span>ENTRY</span>${esc(String(entry.sequence).padStart(2, '0'))}</div>
            <div class="entry-main">
              <h3><a href="${esc(entry.page)}">${esc(entry.title)}</a></h3>
              <p>${esc(entry.summary)}</p>
              <div class="entry-reference"><span>REFERENCE</span>${esc((entry.reference_works || []).join(' / ') || 'none')}</div>
            </div>
            <div class="entry-meta">
              <span>${esc((entry.platforms || []).join(' / '))}</span>
              <span>${esc((entry.genres || []).join(' / '))}</span>
              <span>${esc(lengthLabel(entry))}</span>
            </div>
            <div class="entry-count">
              <b>${esc(entry.shortlist_count)}</b>
              <span>SHORTLIST</span>
              <a href="${esc(entry.doc)}">MD</a>
            </div>
          </article>
        `).join('');
      return `
        <section class="archive-day" data-date="${esc(date)}">
          <header class="archive-day-head">
            <div class="day-date"><time datetime="${esc(date)}">${esc(date.replaceAll('-', '.'))}</time><span>${groups[date].length} RESEARCH ${groups[date].length === 1 ? 'ENTRY' : 'ENTRIES'}</span></div>
            <nav class="day-entry-nav" aria-label="${esc(date)} research entries">${dayNav}</nav>
          </header>
          ${rows}
        </section>
      `;
    }).join('');
}

fetch('data/research-index.json', { cache: 'no-store' })
  .then(response => {
    if (!response.ok) throw new Error(`index ${response.status}`);
    return response.json();
  })
  .then(data => {
    entries = data.sort((a, b) => b.entry_id.localeCompare(a.entry_id));
    [...new Set(entries.map(entry => entry.date))]
      .sort((a, b) => b.localeCompare(a))
      .forEach(date => {
        const option = document.createElement('option');
        const count = entries.filter(entry => entry.date === date).length;
        option.value = date;
        option.textContent = `${date} · ${count} ${count === 1 ? 'entry' : 'entries'}`;
        dateSelect.append(option);
      });

    const params = new URLSearchParams(location.search);
    const requestedDate = params.get('date');
    if (requestedDate && entries.some(entry => entry.date === requestedDate)) {
      dateSelect.value = requestedDate;
    }
    render();
  })
  .catch(error => {
    console.error(error);
    archiveRoot.innerHTML = '<div class="archive-state error">조사 인덱스를 읽지 못했다. data/research-index.json을 확인할 것.</div>';
  });

queryInput.addEventListener('input', render);
dateSelect.addEventListener('change', render);
