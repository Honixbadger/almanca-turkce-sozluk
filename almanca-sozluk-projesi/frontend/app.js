/* ================================================================
   Almanca–Türkçe Sözlük — app.js
   New design (design1-v2 layout) with full feature set.
================================================================ */

'use strict';

// ── Constants ──────────────────────────────────────────────────
const LIST_PAGE = 200;
const THEME_KEY = 'at-theme';
const ADMIN_KEY  = 'at-admin';
const EXAMPLES_KEY = 'at-examples';
const AI_KEY_STORAGE = 'at-gemini-key';

// ── State ───────────────────────────────────────────────────────
const state = {
  entries:      [],   // all entries (base + user)
  filtered:     [],   // after all filters
  selectedIdx:  -1,   // index in filtered
  query:        '',
  pos:          '',
  alpha:        '',
  source:       '',
  category:     '',
  noteOnly:     false,
  showExamples: true,
  adminMode:    false,
  isDark:       false,
  toolsOpen:    false,
  wotd:         null,
  summary:      null,
};

// ── DOM refs ────────────────────────────────────────────────────
const qInput         = document.getElementById('q');
const clearBtn       = document.getElementById('clear-btn');
const posPills       = document.getElementById('pos-pills');
const visCount       = document.getElementById('vis-count');
const totCount       = document.getElementById('tot-count');
const themeBtn       = document.getElementById('theme-btn');
const toolsBtn       = document.getElementById('tools-btn');
const toolsPanel     = document.getElementById('tools-panel');
const toolsOverlay   = document.getElementById('tools-overlay');
const toolsClose     = document.getElementById('tools-close');
const alphaBar       = document.getElementById('alpha-bar');
const listCount      = document.getElementById('list-count');
const listItems      = document.getElementById('list-items');
const wotdBox        = document.getElementById('wotd-box');
const detailWrap     = document.getElementById('detail-wrap');
const rightPanel     = document.getElementById('right-panel');
const sourceFilter   = document.getElementById('source-filter');
const categoryFilter = document.getElementById('category-filter');
const noteOnly       = document.getElementById('note-only');
const examplesToggle = document.getElementById('examples-toggle');
const adminToggle    = document.getElementById('admin-mode-toggle');
const sourceChips    = document.getElementById('source-chips');
const entryForm      = document.getElementById('entry-form');
const entryPos       = document.getElementById('entry-pos');
const entryArticle   = document.getElementById('entry-article');
const entryGerman    = document.getElementById('entry-german');
const entryTurkish   = document.getElementById('entry-turkish');
const entryDesc      = document.getElementById('entry-description');
const entryNote      = document.getElementById('entry-note');
const entryCatPrev   = document.getElementById('entry-category-preview');
const entryMsg       = document.getElementById('entry-form-message');
const entrySubmit    = document.getElementById('entry-submit');

// ── Quiz DOM refs ────────────────────────────────────────────────
const quizBtn       = document.getElementById('quiz-btn');
const quizOverlay   = document.getElementById('quiz-overlay');
const quizModal     = document.getElementById('quiz-modal');
const quizCloseBtnEl= document.getElementById('quiz-close-btn');
const quizScoreEl   = document.getElementById('quiz-score');
const quizMetaEl    = document.getElementById('quiz-meta');
const quizWordEl    = document.getElementById('quiz-word');
const quizHintEl    = document.getElementById('quiz-hint');
const quizInput     = document.getElementById('quiz-input');
const quizResultEl  = document.getElementById('quiz-result');
const quizExamplesEl= document.getElementById('quiz-examples');
const quizCheckBtnEl= document.getElementById('quiz-check-btn');
const quizNextBtnEl = document.getElementById('quiz-next-btn');

// ── Utilities ───────────────────────────────────────────────────
function escHtml(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function hl(text, needle) {
  const src = String(text || '');
  const ndl = String(needle || '').trim();
  if (!ndl || ndl.length < 1) return escHtml(src);
  const re = new RegExp('(' + ndl.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
  return escHtml(src).replace(re, '<mark>$1</mark>');
}

function norm(s) {
  return String(s || '')
    .toLocaleLowerCase('tr')
    .replace(/ı/g, 'i')   // ı (dotless) ≡ i — büyük I içeren kelimelerde kritik
    .replace(/ß/g, 'ss');  // "ss" araması ß'yi de bulsun
}

function unique(arr) {
  return [...new Set((arr || []).filter(Boolean))];
}

function artikelBadgeCls(a) {
  if (a === 'der') return 'badge-artikel-der';
  if (a === 'die') return 'badge-artikel-die';
  if (a === 'das') return 'badge-artikel-das';
  return '';
}

function liArtCls(a) {
  if (a === 'der') return 'li-artikel-der';
  if (a === 'die') return 'li-artikel-die';
  if (a === 'das') return 'li-artikel-das';
  return '';
}

// ── Theme ───────────────────────────────────────────────────────
function applyTheme(dark) {
  state.isDark = dark;
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  themeBtn.textContent = dark ? '☀️' : '🌙';
  try { localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light'); } catch (e) {}
}

function toggleTheme() {
  applyTheme(!state.isDark);
}

// ── Tools panel ─────────────────────────────────────────────────
function openTools() {
  state.toolsOpen = true;
  toolsPanel.classList.add('open');
  toolsOverlay.classList.add('visible');
}

function closeTools() {
  state.toolsOpen = false;
  toolsPanel.classList.remove('open');
  toolsOverlay.classList.remove('visible');
}

function toggleTools() {
  state.toolsOpen ? closeTools() : openTools();
}

// ── Alpha bar ───────────────────────────────────────────────────
function buildAlphaBar() {
  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('').concat(['Ä','Ö','Ü']);
  alphaBar.innerHTML = letters.map(l =>
    `<button class="alpha-btn" data-letter="${l}" title="${l}">${l}</button>`
  ).join('');
}

function setAlpha(letter) {
  if (state.alpha === letter) {
    state.alpha = '';
  } else {
    state.alpha = letter;
  }
  alphaBar.querySelectorAll('.alpha-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.letter === state.alpha);
  });
  applyFilters();
}

// ── Word of the Day ─────────────────────────────────────────────
function buildWotd() {
  if (!state.entries.length) return;
  if (!state.wotd) {
    state.wotd = state.entries[Math.floor(Math.random() * state.entries.length)];
  }
  const e = state.wotd;
  const ex = Array.isArray(e.ornekler) && e.ornekler[0];
  wotdBox.innerHTML = `
    <div class="wotd-label">⭐ Günün Kelimesi</div>
    <div class="wotd-word">${escHtml(e.almanca)}</div>
    <div class="wotd-tr">${escHtml(e.turkce)}</div>
    ${ex ? `<div class="wotd-ex">"${escHtml(ex.almanca)}"</div>` : ''}
  `;
}

// ── List rendering ───────────────────────────────────────────────
function renderList() {
  const q = state.query;
  const total = state.filtered.length;
  listCount.textContent = String(total);
  visCount.textContent  = String(total);
  totCount.textContent  = String(state.entries.length);

  const slice = state.filtered.slice(0, LIST_PAGE);

  if (!total) {
    listItems.innerHTML = `<div class="empty-state">
      <div class="empty-icon">🔍</div>
      <div class="empty-text">Sonuç bulunamadı</div>
    </div>`;
    return;
  }

  let html = '';
  for (let i = 0; i < slice.length; i++) {
    const e = slice[i];
    const active = state.selectedIdx === i ? ' active' : '';
    html += `<div class="list-item${active}" data-idx="${i}">
      <div class="li-word">${hl(e.almanca, q)}</div>
      <div class="li-meta">
        <span class="li-pos">${escHtml(e.tur || '')}</span>
        ${e.artikel ? `<span class="li-artikel ${liArtCls(e.artikel)}">${escHtml(e.artikel)}</span>` : ''}
      </div>
      <div class="li-tr">${escHtml((e.turkce || '').split(/[,;]/)[0].trim())}</div>
    </div>`;
  }

  if (total > LIST_PAGE) {
    html += `<div class="list-item-more">… ve ${total - LIST_PAGE} kelime daha — aramayı daraltın</div>`;
  }

  listItems.innerHTML = html;
}

// ── Select entry ─────────────────────────────────────────────────
function selectEntry(idx) {
  state.selectedIdx = idx;
  // Update active class in list without full re-render
  listItems.querySelectorAll('.list-item').forEach((el, i) => {
    el.classList.toggle('active', i === idx);
  });
  renderDetail(state.filtered[idx]);
  rightPanel.scrollTop = 0;
}

// ── Detail rendering ─────────────────────────────────────────────
function renderDetail(e) {
  if (!e) {
    detailWrap.innerHTML = `<div class="empty-state">
      <div class="empty-icon">📖</div>
      <div class="empty-text">Listeden bir kelime seçin</div>
      <div class="empty-sub">ya da yukarıdaki arama kutusunu kullanın</div>
    </div>`;
    return;
  }

  const q = state.query;

  // ── Badges ──
  let badges = `<span class="badge badge-pos">${escHtml(e.tur || '')}</span>`;
  if (e.artikel) {
    badges += `<span class="badge ${artikelBadgeCls(e.artikel)}">${escHtml(e.artikel)}</span>`;
  }
  if (Array.isArray(e.kategoriler)) {
    e.kategoriler.forEach(k => {
      badges += `<span class="badge badge-cat">${escHtml(k)}</span>`;
    });
  }
  if (e.kaynak) {
    badges += `<span class="badge badge-src">${escHtml(e.kaynak)}</span>`;
  }
  if (e.seviye) {
    badges += `<span class="badge badge-level">${escHtml(e.seviye)}</span>`;
  }

  // ── Morph line ──
  const morphParts = [];
  if (e.cogul)      morphParts.push(`<span class="d-morph-item">çoğul: <strong>${escHtml(e.cogul)}</strong></span>`);
  if (e.genitiv_endung) morphParts.push(`<span class="d-morph-item">genitiv: <strong>-${escHtml(e.genitiv_endung)}</strong></span>`);
  if (e.partizip2)  morphParts.push(`<span class="d-morph-item">Partizip II: <strong>${escHtml(e.partizip2)}</strong></span>`);
  if (e.hilfsverb)  morphParts.push(`<span class="d-morph-item">yardımcı: <strong>${escHtml(e.hilfsverb)}</strong></span>`);
  if (e.stammvokal) morphParts.push(`<span class="d-morph-item">kök: <strong>${escHtml(e.stammvokal)}</strong></span>`);
  if (e.komparativ) morphParts.push(`<span class="d-morph-item">karş: <strong>${escHtml(e.komparativ)}</strong></span>`);
  if (e.superlativ) morphParts.push(`<span class="d-morph-item">en: <strong>${escHtml(e.superlativ)}</strong></span>`);

  // ── Translation block ──
  const trDesc = e.aciklama_turkce
    ? `<div class="d-tr-desc">${escHtml(e.aciklama_turkce)}</div>`
    : '';

  // ── Tanim almanca ──
  const tanimAlmanca = e.tanim_almanca
    ? `<div class="d-tanim-almanca">${escHtml(e.tanim_almanca)}</div>`
    : '';

  // ── Senses ──
  let sensesHtml = '';
  if (Array.isArray(e.anlamlar) && e.anlamlar.length > 1) {
    sensesHtml = `<div class="d-senses">
      <div class="sec-title">Anlamlar</div>
      ${e.anlamlar.map((a, i) => `<div class="sense-item">
        <span class="sense-num">${i + 1}.</span>
        <div class="sense-body">
          ${a.label ? `<span class="sense-label">${escHtml(a.label)}</span>` : ''}
          <strong>${escHtml(a.tr || a.turkce || '')}</strong>${a.tanim ? ` — <em style="color:var(--muted);font-size:0.85em">${escHtml(a.tanim)}</em>` : ''}
        </div>
      </div>`).join('')}
    </div>`;
  }

  // ── Examples ──
  let exHtml = '';
  if (state.showExamples && Array.isArray(e.ornekler) && e.ornekler.length) {
    exHtml = `<div class="d-examples">
      <div class="sec-title">Örnek Cümleler</div>
      ${e.ornekler.map(ex => `<div class="ex-item">
        <div class="ex-de">${hl(ex.almanca || '', e.almanca)}</div>
        <div class="ex-tr">${escHtml(ex.turkce || '')}</div>
        ${ex.kaynak && state.adminMode ? `<div class="ex-src">${escHtml(ex.kaynak)}</div>` : ''}
      </div>`).join('')}
    </div>`;
  }

  // ── Conjugation ──
  let konjHtml = '';
  if (Array.isArray(e.konjugation) && e.konjugation.length) {
    konjHtml = `<div class="sec-title">Çekim Tablosu</div>
    <div class="d-table-wrap">
      <table class="d-table">
        <thead><tr><th>Kişi</th><th>Präsens</th><th>Präteritum</th></tr></thead>
        <tbody>${e.konjugation.map(r => `<tr>
          <td>${escHtml(r.kisi)}</td>
          <td>${escHtml(r.prasens)}</td>
          <td>${escHtml(r.prateritum)}</td>
        </tr>`).join('')}</tbody>
      </table>
    </div>`;
  } else if (e.cekimler) {
    // Support new-style cekimler object
    const c = e.cekimler;
    const summaryRows = [
      ['Präteritum', c['präteritum'] || c.prateritum],
      ['Perfekt', c.perfekt],
      ['Imperativ', c.imperativ],
    ].filter(([, v]) => v);
    if (summaryRows.length) {
      konjHtml = `<div class="sec-title">Çekim Tablosu</div>
      <div class="d-table-wrap">
        <table class="d-table">
          <thead><tr><th>Form</th><th>Değer</th></tr></thead>
          <tbody>${summaryRows.map(([l, v]) => `<tr><td>${escHtml(l)}</td><td>${escHtml(v)}</td></tr>`).join('')}</tbody>
        </table>
      </div>`;
    }
    if (c['präsens'] && typeof c['präsens'] === 'object') {
      const pronouns = ['ich', 'du', 'er/sie/es', 'wir', 'ihr', 'sie/Sie'];
      const rows = pronouns.filter(p => c['präsens'][p]).map(p =>
        `<tr><td>${escHtml(p)}</td><td>${escHtml(c['präsens'][p])}</td></tr>`
      ).join('');
      if (rows) {
        konjHtml += `<div class="sec-title" style="margin-top:12px">Präsens</div>
        <div class="d-table-wrap">
          <table class="d-table">
            <thead><tr><th>Kişi</th><th>Präsens</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`;
      }
    }
  }

  // ── Reference links ──
  let refHtml = '';
  if (e.referans_linkler) {
    const rl = e.referans_linkler;
    const links = [
      rl.duden        ? `<a class="d-ref-link" href="${escHtml(rl.duden)}" target="_blank" rel="noreferrer">Duden</a>` : '',
      rl.dwds         ? `<a class="d-ref-link" href="${escHtml(rl.dwds)}" target="_blank" rel="noreferrer">DWDS</a>` : '',
      rl.wiktionary_de? `<a class="d-ref-link" href="${escHtml(rl.wiktionary_de)}" target="_blank" rel="noreferrer">Wiktionary DE</a>` : '',
      rl.tdk          ? `<a class="d-ref-link" href="${escHtml(rl.tdk)}" target="_blank" rel="noreferrer">TDK</a>` : '',
    ].filter(Boolean);
    if (links.length) {
      refHtml = `<div class="d-ref-links">${links.join('')}</div>`;
    }
  }

  // ── Admin section ──
  let adminHtml = '';
  if (state.adminMode) {
    const rows = [];
    if (e.ceviri_durumu)       rows.push(`<div class="d-admin-row"><strong>Çeviri durumu:</strong> ${escHtml(e.ceviri_durumu)}</div>`);
    if (e.ceviri_inceleme_notu) rows.push(`<div class="d-admin-row"><strong>İnceleme notu:</strong> ${escHtml(e.ceviri_inceleme_notu)}</div>`);
    if (e.kaynak_url)          rows.push(`<div class="d-admin-row"><strong>Kaynak URL:</strong> <a href="${escHtml(e.kaynak_url)}" target="_blank" rel="noreferrer">${escHtml(e.kaynak_url)}</a></div>`);
    if (e.not)                 rows.push(`<div class="d-admin-row"><strong>Not:</strong> ${escHtml(e.not)}</div>`);
    if (rows.length) {
      adminHtml = `<div class="d-admin-section">
        <div class="d-admin-label">Yönetici Bilgisi</div>
        ${rows.join('')}
      </div>`;
    }
  }

  // ── Sidebar: grammar ──
  const gramRows = [];
  if (e.artikel)       gramRows.push(['Artikel', e.artikel]);
  if (e.cogul)         gramRows.push(['Çoğul', e.cogul]);
  if (e.genitiv_endung) gramRows.push(['Genitiv', '-' + e.genitiv_endung]);
  if (e.partizip2)     gramRows.push(['Partizip II', e.partizip2]);
  if (e.hilfsverb)     gramRows.push(['Yardımcı fiil', e.hilfsverb]);
  if (e.komparativ)    gramRows.push(['Karşılaştırma', e.komparativ]);
  if (e.superlativ)    gramRows.push(['Üstünlük', e.superlativ]);
  const gramHtml = gramRows.length ? `
    <div class="side-card">
      <div class="side-card-head">Dilbilgisi</div>
      <div class="side-card-body">
        <div class="gram-rows">
          ${gramRows.map(([l, v]) => `<div class="gram-row">
            <span class="gram-lbl">${escHtml(l)}</span>
            <span class="gram-val">${escHtml(v)}</span>
          </div>`).join('')}
        </div>
      </div>
    </div>` : '';

  // ── Sidebar: synonyms ──
  const esanlamlilar = Array.isArray(e.esanlamlilar) ? e.esanlamlilar : [];
  const synHtml = esanlamlilar.length ? `
    <div class="side-card">
      <div class="side-card-head">Eş Anlamlılar</div>
      <div class="side-card-body">
        <div class="chip-cloud">
          ${esanlamlilar.map(s => `<button class="word-chip" data-search="${escHtml(s)}">${escHtml(s)}</button>`).join('')}
        </div>
      </div>
    </div>` : '';

  // ── Sidebar: antonyms ──
  const zitanlamlilar = Array.isArray(e.zit_anlamlilar) ? e.zit_anlamlilar : [];
  const antHtml = zitanlamlilar.length ? `
    <div class="side-card">
      <div class="side-card-head">Zıt Anlamlılar</div>
      <div class="side-card-body">
        <div class="chip-cloud">
          ${zitanlamlilar.map(s => `<button class="word-chip ant" data-search="${escHtml(s)}">${escHtml(s)}</button>`).join('')}
        </div>
      </div>
    </div>` : '';

  // ── Sidebar: word family ──
  const kelimeAilesi = Array.isArray(e.kelime_ailesi) ? e.kelime_ailesi : [];
  const famHtml = kelimeAilesi.length ? `
    <div class="side-card">
      <div class="side-card-head">Kelime Ailesi</div>
      <div class="side-card-body">
        ${kelimeAilesi.map(w => `<div class="family-item">
          <span class="family-word" data-search="${escHtml(w)}">${escHtml(w)}</span>
        </div>`).join('')}
      </div>
    </div>` : '';

  // ── Sidebar: related ──
  const ilgiliKayitlar = Array.isArray(e.ilgili_kayitlar) ? e.ilgili_kayitlar : [];
  const relHtml = ilgiliKayitlar.length ? `
    <div class="side-card">
      <div class="side-card-head">İlgili Kayıtlar</div>
      <div class="side-card-body">
        ${ilgiliKayitlar.map(w => `<div class="ilgili-item" data-search="${escHtml(w)}">${escHtml(w)}</div>`).join('')}
      </div>
    </div>` : '';

  // ── Assemble ──
  detailWrap.innerHTML = `
    <div class="d-head">
      <div class="d-badges">${badges}</div>
      <div class="d-lemma">${escHtml(e.almanca)}</div>
      ${morphParts.length ? `<div class="d-morph-line">${morphParts.join('')}</div>` : ''}
    </div>

    <div class="d-body">
      <div class="d-main">
        <div class="d-translation">
          <div class="d-tr-word">${escHtml(e.turkce || '')}</div>
          ${trDesc}
        </div>
        ${tanimAlmanca}
        ${sensesHtml}
        ${exHtml}
        ${konjHtml}
        ${refHtml}
        ${adminHtml}
      </div>
      <div class="d-sidebar">
        ${gramHtml}
        ${synHtml}
        ${antHtml}
        ${famHtml}
        ${relHtml}
      </div>
    </div>
  `;

  // Bind chip clicks in detail
  detailWrap.querySelectorAll('[data-search]').forEach(el => {
    el.addEventListener('click', () => searchWord(el.dataset.search));
  });
}

function searchWord(w) {
  qInput.value = w;
  state.query = w;
  clearBtn.classList.add('visible');
  applyFilters();
}

// ── Filters ──────────────────────────────────────────────────────
function applyFilters() {
  const q     = norm(state.query);
  const pos   = state.pos;
  const alpha = state.alpha;
  const src   = state.source;
  const cat   = state.category;
  const noteF = state.noteOnly;

  state.filtered = state.entries.filter(e => {
    if (pos && (e.tur || '') !== pos) return false;
    if (alpha && !norm(e.almanca || '').startsWith(norm(alpha))) return false;
    // DÜZELTME: kaynak alanı noktalı virgülle ayrılmış — tam eşleşme değil, segment içinde ara
    if (src) {
      const segs = String(e.kaynak || '').split(';').map(s => s.trim());
      if (!segs.includes(src)) return false;
    }
    if (cat && !(e.kategoriler || []).includes(cat)) return false;
    if (noteF && !(e.not || '')) return false;
    if (!q) return true;
    // Genişletilmiş arama alanları
    if (norm(e.almanca         || '').includes(q)) return true;
    if (norm(e.turkce          || '').includes(q)) return true;
    if (norm(e.aciklama_turkce || '').includes(q)) return true;
    if (norm(e.tanim_almanca   || '').includes(q)) return true;
    if (norm(e.not             || '').includes(q)) return true;
    if ((e.esanlamlilar  || []).some(s => norm(s).includes(q))) return true;
    if ((e.kelime_ailesi || []).some(s => norm(s).includes(q))) return true;
    return false;
  });

  // Sıralama: tam eşleşme → başlangıç eşleşmesi → içeride geçiyor → alfabetik
  state.filtered.sort((a, b) => {
    if (q) {
      const an = norm(a.almanca || ''), bn = norm(b.almanca || '');
      const rank = x => x === q ? 0 : x.startsWith(q) ? 1 : 2;
      const d = rank(an) - rank(bn);
      if (d !== 0) return d;
    }
    return (a.almanca || '').localeCompare(b.almanca || '', 'de');
  });

  state.selectedIdx = -1;
  renderList();
  if (state.filtered.length > 0) {
    selectEntry(0);
  } else {
    renderDetail(null);
  }
}

// ── Filter population ────────────────────────────────────────────
function populateFilters() {
  // Source
  const sources = unique(state.entries.flatMap(e =>
    String(e.kaynak || '').split(';').map(s => s.trim()).filter(Boolean)
  )).sort((a, b) => a.localeCompare(b, 'tr'));

  const curSrc = sourceFilter.value;
  sourceFilter.innerHTML = `<option value="">Tüm kaynaklar</option>` +
    sources.map(s => `<option value="${escHtml(s)}">${escHtml(s)}</option>`).join('');
  if (sources.includes(curSrc)) sourceFilter.value = curSrc;

  // Category
  const cats = unique(state.entries.flatMap(e => e.kategoriler || [])).sort((a, b) => a.localeCompare(b, 'tr'));
  const curCat = categoryFilter.value;
  categoryFilter.innerHTML = `<option value="">Tüm kategoriler</option>` +
    cats.map(c => `<option value="${escHtml(c)}">${escHtml(c)}</option>`).join('');
  if (cats.includes(curCat)) categoryFilter.value = curCat;
}

// ── Source chips ─────────────────────────────────────────────────
function renderSourceChips() {
  if (!state.summary?.sources) {
    sourceChips.innerHTML = '<span style="font-size:0.78rem;color:var(--muted)">Kaynak bilgisi yok.</span>';
    return;
  }
  const entries = Object.entries(state.summary.sources).sort((a, b) => b[1] - a[1]);
  sourceChips.innerHTML = entries.map(([src, cnt]) =>
    `<span class="chip">${escHtml(src)} (${cnt})</span>`
  ).join('');
}

// ── Data loading ─────────────────────────────────────────────────
async function loadJson(path) {
  const r = await fetch(path, { cache: 'no-store' });
  if (!r.ok) throw new Error(`${path} yüklenemedi (${r.status})`);
  return r.json();
}

async function loadUserEntries() {
  try {
    const r = await fetch('/api/user-entries', { cache: 'no-store' });
    if (!r.ok) return [];
    const payload = await r.json();
    return payload.entries || [];
  } catch { return []; }
}

// ── Entry form ───────────────────────────────────────────────────
let previewTimer = null;

function syncArticleState() {
  const isNoun = entryPos.value === 'isim';
  entryArticle.disabled = !isNoun;
  if (!isNoun) entryArticle.value = '';
}

function entryPayload() {
  return {
    almanca:       entryGerman.value.trim(),
    artikel:       entryArticle.value,
    turkce:        entryTurkish.value.trim(),
    tur:           entryPos.value,
    aciklama_turkce: entryDesc.value.trim(),
    not:           entryNote.value.trim(),
  };
}

function setEntryMsg(text, tone) {
  entryMsg.textContent   = text || '';
  entryMsg.dataset.tone  = tone || '';
}

async function fetchCatPreview() {
  const p = entryPayload();
  if (!p.almanca || !p.turkce || !p.tur) {
    entryCatPrev.textContent = 'Algılanan kategori: -';
    return;
  }
  try {
    const r = await fetch('/api/categorize-preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify(p),
    });
    const res = await r.json();
    if (r.ok && res.status === 'ok') {
      entryCatPrev.textContent = `Algılanan kategori: ${(res.categories || ['genel']).join(', ')}`;
    }
  } catch {
    entryCatPrev.textContent = 'Algılanan kategori: -';
  }
}

function queueCatPreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => {
    fetchCatPreview().catch(() => {
      entryCatPrev.textContent = 'Algılanan kategori: -';
    });
  }, 350);
}

async function handleEntrySubmit(ev) {
  ev.preventDefault();
  const p = entryPayload();
  entrySubmit.disabled = true;
  setEntryMsg('Kelime kaydediliyor…');

  try {
    const r = await fetch('/api/add-entry', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify(p),
    });
    const res = await r.json();
    if (!r.ok || res.status !== 'ok') throw new Error(res.note || 'Kelime kaydedilemedi.');

    const saved = res.entry;
    const dupIdx = state.entries.findIndex(item =>
      norm(item.almanca) === norm(saved.almanca) &&
      norm(item.turkce)  === norm(saved.turkce) &&
      norm(item.tur)     === norm(saved.tur)
    );
    if (dupIdx >= 0) {
      state.entries.splice(dupIdx, 1, saved);
    } else {
      state.entries.push(saved);
    }
    // Update summary
    if (state.summary) {
      state.summary.sources = state.summary.sources || {};
      if (!dupIdx || dupIdx < 0) {
        state.summary.sources['kullanici-ekleme'] = (state.summary.sources['kullanici-ekleme'] || 0) + 1;
      }
    }

    populateFilters();
    renderSourceChips();
    applyFilters();
    entryForm.reset();
    entryPos.value = 'isim';
    syncArticleState();
    entryCatPrev.textContent = `Algılanan kategori: ${(saved.kategoriler || ['genel']).join(', ')}`;
    setEntryMsg(`Kaydedildi. Kategori: ${(saved.kategoriler || ['genel']).join(', ')}`, 'success');
  } catch (err) {
    setEntryMsg(err.message, 'error');
  } finally {
    entrySubmit.disabled = false;
  }
}

// ── AI Import ────────────────────────────────────────────────────
const aiState = {
  scanning: false,
  saving:   false,
  candidates: [],
};

function getAiEls() {
  return {
    apiKeyInput: document.getElementById('ai-api-key'),
    urlInput:    document.getElementById('ai-import-url'),
    scanBtn:     document.getElementById('ai-import-scan'),
    statusNode:  document.getElementById('ai-import-status'),
    resultsWrap: document.getElementById('ai-import-results'),
    summaryNode: document.getElementById('ai-import-summary'),
    selectAll:   document.getElementById('ai-import-select-all'),
    tbody:       document.getElementById('ai-import-tbody'),
    saveBtn:     document.getElementById('ai-import-save'),
    saveStatus:  document.getElementById('ai-import-save-status'),
  };
}

function setAiStatus(node, text, tone) {
  node.textContent   = text;
  node.dataset.tone  = tone || '';
}

function renderAiCandidates() {
  const el = getAiEls();
  el.tbody.replaceChildren();
  if (!aiState.candidates.length) {
    el.resultsWrap.hidden = true;
    return;
  }
  el.resultsWrap.hidden = false;
  el.summaryNode.textContent = `${aiState.candidates.length} kelime bulundu. Eklemek istediklerinizi seçin.`;

  for (let i = 0; i < aiState.candidates.length; i++) {
    const c = aiState.candidates[i];
    const tr = document.createElement('tr');

    const tdCheck = document.createElement('td');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = c._selected !== false;
    cb.dataset.idx = String(i);
    cb.addEventListener('change', () => {
      aiState.candidates[i]._selected = cb.checked;
      updateAiSelectAll();
    });
    tdCheck.append(cb);

    const tdWord = document.createElement('td');
    tdWord.textContent = [c.artikel, c.almanca].filter(Boolean).join(' ');
    tdWord.className = 'ai-cell-word';

    const tdTr  = document.createElement('td'); tdTr.textContent  = c.turkce || '-';
    const tdPos = document.createElement('td'); tdPos.textContent = c.tur    || 'belirsiz';
    const tdArt = document.createElement('td'); tdArt.textContent = c.artikel || '-';

    tr.append(tdCheck, tdWord, tdTr, tdPos, tdArt);
    el.tbody.append(tr);
  }
}

function updateAiSelectAll() {
  const el = getAiEls();
  el.selectAll.checked = aiState.candidates.every(c => c._selected !== false);
}

function toggleAiSelectAll(checked) {
  aiState.candidates.forEach(c => { c._selected = checked; });
  renderAiCandidates();
}

async function handleAiScan() {
  const el = getAiEls();
  if (aiState.scanning) return;

  const apiKey = el.apiKeyInput.value.trim();
  const url    = el.urlInput.value.trim();
  if (!apiKey) { setAiStatus(el.statusNode, 'Lütfen Gemini API Key girin.', 'error'); return; }
  if (!url)    { setAiStatus(el.statusNode, 'Lütfen bir URL girin.', 'error'); return; }

  try { localStorage.setItem(AI_KEY_STORAGE, apiKey); } catch (e) {}
  aiState.scanning = true;
  aiState.candidates = [];
  renderAiCandidates();
  el.scanBtn.disabled = true;
  setAiStatus(el.statusNode, 'URL taranıyor ve Gemini AI analiz ediyor… Bu işlem 10-30 saniye sürebilir.', '');

  try {
    const r = await fetch('/api/ai-import/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ url, api_key: apiKey }),
    });
    const res = await r.json();
    if (res.status !== 'ok') {
      setAiStatus(el.statusNode, res.note || 'Tarama başarısız oldu.', 'error');
      return;
    }
    aiState.candidates = (res.candidates || []).map(c => ({ ...c, _selected: true }));
    setAiStatus(el.statusNode, res.note || 'Tarama tamamlandı.', 'success');
    renderAiCandidates();
  } catch (err) {
    setAiStatus(el.statusNode, `Hata: ${err.message}`, 'error');
  } finally {
    aiState.scanning = false;
    el.scanBtn.disabled = false;
  }
}

async function handleAiSave() {
  const el = getAiEls();
  if (aiState.saving) return;

  const selected = aiState.candidates.filter(c => c._selected !== false);
  if (!selected.length) { setAiStatus(el.saveStatus, 'Hiç kelime seçilmedi.', 'error'); return; }

  const entries = selected.map(({ _selected, ...entry }) => entry);
  aiState.saving = true;
  el.saveBtn.disabled = true;
  setAiStatus(el.saveStatus, 'Kaydediliyor…', '');

  try {
    const r = await fetch('/api/ai-import/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ entries }),
    });
    const res = await r.json();
    if (res.status !== 'ok') {
      setAiStatus(el.saveStatus, res.note || 'Kaydetme başarısız oldu.', 'error');
      return;
    }
    setAiStatus(el.saveStatus, res.note || 'Kaydedildi!', 'success');

    // Refresh
    const [freshEntries, freshUser] = await Promise.all([
      loadJson('../output/dictionary.json'),
      loadUserEntries(),
    ]);
    state.entries = [...freshEntries, ...freshUser];
    state.entries.sort((a, b) => (a.almanca || '').localeCompare(b.almanca || '', 'de'));
    populateFilters();
    renderSourceChips();
    applyFilters();
    aiState.candidates = [];
    renderAiCandidates();
  } catch (err) {
    setAiStatus(el.saveStatus, `Hata: ${err.message}`, 'error');
  } finally {
    aiState.saving = false;
    el.saveBtn.disabled = false;
  }
}

function initAiImport() {
  const el = getAiEls();
  if (!el.scanBtn) return;

  const savedKey = (() => { try { return localStorage.getItem(AI_KEY_STORAGE) || ''; } catch { return ''; } })();
  if (savedKey) el.apiKeyInput.value = savedKey;

  el.apiKeyInput.addEventListener('change', () => {
    try { localStorage.setItem(AI_KEY_STORAGE, el.apiKeyInput.value.trim()); } catch (e) {}
  });
  el.scanBtn.addEventListener('click', handleAiScan);
  el.saveBtn.addEventListener('click', handleAiSave);
  el.selectAll.addEventListener('change', () => toggleAiSelectAll(el.selectAll.checked));
  el.urlInput.addEventListener('keydown', ev => {
    if (ev.key === 'Enter') { ev.preventDefault(); handleAiScan(); }
  });
}

// ── Keyboard shortcuts ───────────────────────────────────────────
function handleKeydown(ev) {
  // Ctrl+F: focus search
  if ((ev.ctrlKey || ev.metaKey) && ev.key === 'f') {
    ev.preventDefault();
    qInput.focus();
    qInput.select();
    return;
  }

  // Escape: close tools or clear search
  if (ev.key === 'Escape') {
    if (state.toolsOpen) { closeTools(); return; }
    if (state.query) { clearSearch(); return; }
  }

  // Arrow navigation in list
  if (ev.key === 'ArrowDown' && !ev.ctrlKey) {
    ev.preventDefault();
    const next = Math.min(state.selectedIdx + 1, Math.min(state.filtered.length, LIST_PAGE) - 1);
    if (next !== state.selectedIdx) selectEntry(next);
    return;
  }
  if (ev.key === 'ArrowUp' && !ev.ctrlKey) {
    ev.preventDefault();
    const prev = Math.max(state.selectedIdx - 1, 0);
    if (prev !== state.selectedIdx) selectEntry(prev);
    return;
  }

  // Ctrl+K: synonym / related search (focus search)
  if ((ev.ctrlKey || ev.metaKey) && ev.key === 'k') {
    ev.preventDefault();
    qInput.focus();
    qInput.select();
    return;
  }
}

// ── Search ───────────────────────────────────────────────────────
function onSearch(v) {
  state.query = v;
  clearBtn.classList.toggle('visible', !!v);
  applyFilters();
}

function clearSearch() {
  qInput.value = '';
  onSearch('');
}

// ── Init ─────────────────────────────────────────────────────────
async function init() {
  // Theme
  const savedTheme = (() => { try { return localStorage.getItem(THEME_KEY); } catch { return null; } })();
  applyTheme(savedTheme === 'dark');

  // Admin / examples state
  const savedAdmin = (() => { try { return localStorage.getItem(ADMIN_KEY) === 'on'; } catch { return false; } })();
  const savedExamples = (() => {
    try {
      const v = localStorage.getItem(EXAMPLES_KEY);
      return v === null ? true : v === 'on';
    } catch { return true; }
  })();
  state.adminMode    = savedAdmin;
  state.showExamples = savedExamples;
  adminToggle.checked    = savedAdmin;
  examplesToggle.checked = savedExamples;

  // Build alpha bar
  buildAlphaBar();

  // Load data
  listItems.innerHTML = '<div class="loading-state">Veri yükleniyor…</div>';
  try {
    const [baseEntries, summary, userEntries] = await Promise.all([
      loadJson('../output/dictionary.json'),
      loadJson('../output/source_summary.json').catch(() => null),
      loadUserEntries(),
    ]);

    state.entries = [...baseEntries, ...userEntries];
    state.entries.sort((a, b) => (a.almanca || '').localeCompare(b.almanca || '', 'de'));
    state.summary = summary;

    if (userEntries.length && state.summary) {
      state.summary.sources = state.summary.sources || {};
      state.summary.sources['kullanici-ekleme'] = userEntries.length;
    }

    populateFilters();
    renderSourceChips();
    buildWotd();
    applyFilters();
  } catch (err) {
    listItems.innerHTML = `<div class="empty-state">
      <div class="empty-icon">⚠️</div>
      <div class="empty-text">Veri yüklenemedi</div>
      <div class="empty-sub">${escHtml(err.message)}</div>
    </div>`;
  }

  // ── Event listeners ──

  // Search
  qInput.addEventListener('input', () => onSearch(qInput.value));
  clearBtn.addEventListener('click', clearSearch);

  // POS pills
  posPills.addEventListener('click', ev => {
    const btn = ev.target.closest('.pos-pill');
    if (!btn) return;
    posPills.querySelectorAll('.pos-pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.pos = btn.dataset.pos || '';
    applyFilters();
  });

  // Alpha bar
  alphaBar.addEventListener('click', ev => {
    const btn = ev.target.closest('.alpha-btn');
    if (btn) setAlpha(btn.dataset.letter);
  });

  // List click
  listItems.addEventListener('click', ev => {
    const item = ev.target.closest('.list-item');
    if (item) {
      const idx = parseInt(item.dataset.idx, 10);
      if (!isNaN(idx)) selectEntry(idx);
    }
  });

  // Theme
  themeBtn.addEventListener('click', toggleTheme);

  // Tools
  toolsBtn.addEventListener('click', toggleTools);
  toolsClose.addEventListener('click', closeTools);
  toolsOverlay.addEventListener('click', closeTools);

  // Filters in tools panel
  sourceFilter.addEventListener('change', () => {
    state.source = sourceFilter.value;
    applyFilters();
  });
  categoryFilter.addEventListener('change', () => {
    state.category = categoryFilter.value;
    applyFilters();
  });
  noteOnly.addEventListener('change', () => {
    state.noteOnly = noteOnly.checked;
    applyFilters();
  });
  examplesToggle.addEventListener('change', () => {
    state.showExamples = examplesToggle.checked;
    try { localStorage.setItem(EXAMPLES_KEY, state.showExamples ? 'on' : 'off'); } catch (e) {}
    // Re-render current detail
    if (state.selectedIdx >= 0) renderDetail(state.filtered[state.selectedIdx]);
  });
  adminToggle.addEventListener('change', () => {
    state.adminMode = adminToggle.checked;
    try { localStorage.setItem(ADMIN_KEY, state.adminMode ? 'on' : 'off'); } catch (e) {}
    if (state.selectedIdx >= 0) renderDetail(state.filtered[state.selectedIdx]);
  });

  // Entry form
  entryPos.addEventListener('change', () => { syncArticleState(); queueCatPreview(); });
  entryGerman.addEventListener('input', queueCatPreview);
  entryTurkish.addEventListener('input', queueCatPreview);
  entryDesc.addEventListener('input', queueCatPreview);
  entryArticle.addEventListener('change', queueCatPreview);
  entryNote.addEventListener('input', queueCatPreview);
  entryForm.addEventListener('submit', handleEntrySubmit);
  syncArticleState();

  // AI import
  initAiImport();

  // Keyboard
  document.addEventListener('keydown', handleKeydown);

  // ── Quiz event listeners ────────────────────────────────────────
  quizBtn.addEventListener('click', openQuiz);
  quizCloseBtnEl.addEventListener('click', closeQuiz);
  quizOverlay.addEventListener('click', closeQuiz);
  quizCheckBtnEl.addEventListener('click', checkQuiz);
  quizNextBtnEl.addEventListener('click', nextQuiz);
  quizInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); quiz.answered ? nextQuiz() : checkQuiz(); }
    if (e.key === 'Escape') closeQuiz();
  });
}

init();

// ════════════════════════════════════════════════════════════════
// MINI QUIZ
// ════════════════════════════════════════════════════════════════
const quiz = {
  entry:    null,
  answered: false,
  correct:  0,
  wrong:    0,
  streak:   0,
};

function openQuiz() {
  quizOverlay.classList.add('visible');
  quizModal.classList.add('visible');
  // Skor sıfırla her açılışta DEĞİL — oturum boyunca biriksin
  nextQuiz();
}

function closeQuiz() {
  quizOverlay.classList.remove('visible');
  quizModal.classList.remove('visible');
}

function _quizPool() {
  // Aktif filtre varsa onları kullan, yoksa tüm liste
  const filtered = state.filtered;
  const all      = state.entries;
  return (filtered.length > 0 && filtered.length < all.length) ? filtered : all;
}

function nextQuiz() {
  const pool = _quizPool();
  if (!pool.length) {
    quizWordEl.textContent = 'Önce sözlüğe veri yükleyin.';
    return;
  }
  quiz.entry    = pool[Math.floor(Math.random() * pool.length)];
  quiz.answered = false;

  const e = quiz.entry;

  // Meta (tür + seviye)
  quizMetaEl.innerHTML = [
    e.tur    ? `<span class="quiz-pos-tag">${escHtml(e.tur)}</span>`    : '',
    e.seviye ? `<span class="quiz-level">${escHtml(e.seviye)}</span>`   : '',
  ].join('');

  // Kelime (artikel renkli)
  const artHtml = e.artikel
    ? `<span class="quiz-artikel quiz-artikel-${e.artikel}">${escHtml(e.artikel)}</span>`
    : '';
  quizWordEl.innerHTML = artHtml + escHtml(e.almanca);

  // Çoklu çeviri varsa ipucu
  const ansCount = (e.turkce || '').split(',').filter(s => s.trim()).length;
  quizHintEl.textContent = ansCount > 1
    ? `Bu kelimenin ${ansCount} kabul edilen çevirisi var`
    : '';

  // Arayüz sıfırla
  quizResultEl.className  = 'quiz-result quiz-result-hidden';
  quizResultEl.innerHTML  = '';
  quizExamplesEl.innerHTML= '';
  quizInput.value         = '';
  quizInput.disabled      = false;
  quizCheckBtnEl.style.display = '';
  quizNextBtnEl.style.display  = 'none';

  _renderQuizScore();
  quizInput.focus();
}

function checkQuiz() {
  if (quiz.answered) return;
  const userRaw = quizInput.value.trim();
  if (!userRaw) { quizInput.focus(); return; }

  const e       = quiz.entry;
  const userNorm= norm(userRaw);
  const answers = (e.turkce || '').split(',')
    .map(a => norm(a.trim())).filter(Boolean);
  const ok      = answers.some(a => a === userNorm);

  quiz.answered = true;
  if (ok) { quiz.correct++; quiz.streak++; }
  else    { quiz.wrong++;   quiz.streak = 0; }

  // Sonuç kutusu
  quizResultEl.className = `quiz-result ${ok ? 'quiz-result-ok' : 'quiz-result-bad'}`;
  let html = `<span class="quiz-verdict">${ok ? '✓ Doğru!' : '✗ Yanlış'}</span>`;
  if (!ok) {
    html += `<span class="quiz-correct-ans">Doğru: <strong>${escHtml(e.turkce || '')}</strong></span>`;
  }
  if (e.aciklama_turkce) {
    html += `<div class="quiz-aciklama">${escHtml(e.aciklama_turkce)}</div>`;
  }
  quizResultEl.innerHTML = html;

  // Örnek cümleler
  const ornekler = Array.isArray(e.ornekler) ? e.ornekler : [];
  if (ornekler.length) {
    quizExamplesEl.innerHTML =
      `<div class="quiz-ex-title">Örnek Cümleler</div>` +
      ornekler.slice(0, 2).map(ex =>
        `<div class="quiz-ex-item">
          <div class="quiz-ex-de">${escHtml(ex.almanca || '')}</div>
          <div class="quiz-ex-tr">${escHtml(ex.turkce  || '')}</div>
        </div>`
      ).join('');
  }

  quizInput.disabled           = true;
  quizCheckBtnEl.style.display = 'none';
  quizNextBtnEl.style.display  = '';
  _renderQuizScore();
  quizNextBtnEl.focus();
}

function _renderQuizScore() {
  const total = quiz.correct + quiz.wrong;
  const pct   = total ? Math.round(quiz.correct / total * 100) : null;
  quizScoreEl.innerHTML = [
    `<span class="quiz-sc-ok">✓ ${quiz.correct}</span>`,
    `<span class="quiz-sc-bad">✗ ${quiz.wrong}</span>`,
    quiz.streak >= 2 ? `<span class="quiz-streak">🔥 ${quiz.streak}</span>` : '',
    pct !== null ? `<span class="quiz-pct">${pct}%</span>` : '',
  ].join('');
}
