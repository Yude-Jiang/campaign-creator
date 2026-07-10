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

  /** Switch language */
  setLanguage(lang) {
    this.current.language = lang;
    this.save();
    // Redirect to same page with updated lang param
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

/* ── API Helpers ── */
async function apiFetch(url, options = {}) {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || `API error ${resp.status}`);
  }
  return resp.json();
}
