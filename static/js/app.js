/* ============================================================
   Campaign Factory — Global State & Tab Navigation
   ============================================================ */

const CampaignState = {
  current: {
    campaignId: null,
    language: 'zh',
    brief: {},
    personas: [],
    questions: [],
    diagnoses: {},
    plan: null,
  },

  /** Load from localStorage */
  load(campaignId) {
    const key = `campaign_${campaignId}`;
    const raw = localStorage.getItem(key);
    if (raw) {
      try {
        this.current = JSON.parse(raw);
        this.current.campaignId = campaignId;
        return true;
      } catch (e) {
        console.warn('Failed to parse saved state:', e);
      }
    }
    return false;
  },

  /** Save to localStorage */
  save() {
    if (!this.current.campaignId) return;
    const key = `campaign_${this.current.campaignId}`;
    localStorage.setItem(key, JSON.stringify(this.current));
    this.updateSaveIndicator(true);
  },

  /** Create fresh state for a new campaign */
  init(campaignId, brief) {
    this.current = {
      campaignId,
      language: this.current.language,
      brief,
      personas: [],
      questions: [],
      diagnoses: {},
      plan: null,
    };
    this.save();
  },

  /** Switch language.
   *
   * On a campaign page the language is a property of the campaign — it selects
   * the prompt set for every later generation step — so it must be persisted
   * server-side, not just tacked onto the URL. Off a campaign page (the
   * landing form) the ?lang= param is all there is.
   */
  async setLanguage(lang) {
    if (lang === this.current.language && !_campaignId) return;
    this.current.language = lang;
    this.save();

    if (_campaignId) {
      try {
        await apiFetch(`/api/campaigns/${_campaignId}/language`, {
          method: 'PUT',
          body: JSON.stringify({ language: lang }),
        });
      } catch (err) {
        alert('Failed to switch language: ' + err.message);
        return;
      }
      window.location.href = `/campaigns/${_campaignId}`;
      return;
    }

    const url = new URL(window.location.href);
    url.searchParams.set('lang', lang);
    window.location.href = url.toString();
  },

  updateSaveIndicator(saved) {
    const el = document.getElementById('save-indicator');
    if (!el) return;
    if (saved) {
      el.innerHTML = '<span class="dot"></span> Saved';
      setTimeout(() => { if (el) el.innerHTML = '<span class="dot"></span> All changes saved'; }, 1500);
    }
  },

  /** Check which questions still need diagnosis uploads */
  getMissingDiagnoses() {
    return this.current.questions.filter(q => !this.current.diagnoses[q.id]);
  },
};

/* ── Tab Navigation ── */

const _campaignId = document.body.dataset.campaignId || null;

/** Navigate to a tab by index, updating server state if on a campaign page. */
async function navigateToTab(tabIndex) {
  if (_campaignId) {
    // Server-rendered mode: update current_tab then reload
    await apiFetch(`/api/campaigns/${_campaignId}/tab?tab=${tabIndex}`, { method: 'PUT' });
    const lang = CampaignState.current.language || 'zh';
    window.location.href = `/campaigns/${_campaignId}?lang=${lang}`;
  } else {
    // Homepage mode: CSS-only switch (only Tab 0 is active)
    switchTabCSS(tabIndex);
  }
}

/** CSS-only tab switching — used on homepage where all tabs exist in one page. */
function switchTabCSS(tabIndex) {
  document.querySelectorAll('.tab-btn').forEach((btn, i) => {
    btn.classList.toggle('active', i === tabIndex);
  });
  document.querySelectorAll('.tab-panel').forEach((panel, i) => {
    panel.classList.toggle('active', i === tabIndex);
  });
  // Footer always visible — Tab 0 has the submit button
}

/** Legacy alias — used by old code paths. */
function switchTab(tabIndex) {
  if (_campaignId) {
    navigateToTab(tabIndex);
  } else {
    switchTabCSS(tabIndex);
  }
}

/* Initialize tabs */
document.addEventListener('DOMContentLoaded', () => {
  const tabButtons = document.querySelectorAll('.tab-btn');
  tabButtons.forEach((btn, i) => {
    btn.addEventListener('click', () => {
      if (!btn.classList.contains('disabled')) {
        navigateToTab(i);
      }
    });
  });

  // Start on first non-disabled or active tab
  const activeTab = [...tabButtons].findIndex(b => b.classList.contains('active'));
  const startTab = activeTab >= 0 ? activeTab : [...tabButtons].findIndex(b => !b.classList.contains('disabled'));
  if (startTab >= 0 && !_campaignId) switchTabCSS(startTab);
});

/* ── Safe DOM Helpers ──
   Everything the LLM produces (generated content, risk-scan messages,
   channel-fit warnings, error details) can echo text from an uploaded
   diagnosis file, so it is untrusted markup. These helpers build nodes and
   set textContent instead of assigning innerHTML. */

const NOTICE_STYLE = 'padding:8px 12px;background:#fffbeb;border:1px solid #fde68a;' +
  'border-radius:6px;font-size:12px;color:#92400e;';
const ERROR_STYLE = 'margin-top:8px;padding:12px;background:#fef2f2;border-radius:8px;' +
  'border:1px solid #fecaca;color:#dc2626;font-size:14px;';

/** Create an element, setting its text via textContent (never innerHTML). */
function el(tag, { text = '', style = '', className = '' } = {}) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (style) node.setAttribute('style', style);
  if (className) node.className = className;
  return node;
}

/** Replace a container's children with a single node. */
function replaceChildren(container, node) {
  container.textContent = '';
  if (node) container.appendChild(node);
}

/** Render an LLM generation result (content + warnings) into `container`. */
function renderGeneratedContent(container, resp, generatedLabel) {
  container.textContent = '';

  if (resp.truncation_warning) {
    container.appendChild(el('div', {
      text: '⚠ ' + resp.truncation_warning,
      style: 'margin-top:8px;padding:8px 12px;background:#FEF2F2;border:1px solid #FCA5A5;' +
             'border-radius:6px;font-size:12px;color:#991B1B;',
    }));
  }

  if (resp.risk_scan && resp.risk_scan.message) {
    container.appendChild(el('div', {
      text: '⚠ ' + resp.risk_scan.message,
      style: 'margin-top:8px;' + NOTICE_STYLE,
    }));
  }

  const card = el('div', {
    style: 'margin-top:8px;padding:16px;background:var(--paper);' +
           'border-radius:8px;border:1px solid var(--blue);',
  });

  if (resp.channel_fit_warning) {
    card.appendChild(el('div', {
      text: '⚠ ' + resp.channel_fit_warning,
      style: 'margin-bottom:8px;' + NOTICE_STYLE,
    }));
  }

  const meta = el('div', {
    style: 'font-size:11px;color:var(--slate);margin-bottom:8px;' +
           'display:flex;justify-content:space-between;',
  });
  meta.appendChild(el('span', { text: generatedLabel + ' — ' + (resp.model || 'AI') }));
  meta.appendChild(el('span', { text: new Date().toISOString().slice(0, 16) }));
  card.appendChild(meta);

  card.appendChild(el('div', {
    text: resp.content || '',
    style: 'white-space:pre-wrap;font-size:14px;max-height:600px;overflow-y:auto;',
  }));

  container.appendChild(card);
  container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/** Render a failure message into `container`. */
function renderGenerationError(container, prefix, message) {
  replaceChildren(container, el('div', { text: prefix + message, style: ERROR_STYLE }));
}

/* ── API Helpers ── */
async function apiFetch(url, options = {}) {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    const detail = body && body.detail;
    // `detail` may be a structured object (e.g. an unresolved content format
    // carrying the list of valid channels). Keep it on the error so callers
    // can act on it instead of showing "[object Object]".
    const message = (detail && typeof detail === 'object')
      ? (detail.message || `API error ${resp.status}`)
      : (detail || `API error ${resp.status}`);
    const error = new Error(message);
    error.status = resp.status;
    error.detail = detail;
    throw error;
  }
  return resp.json();
}
