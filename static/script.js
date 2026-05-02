(() => {
  const MAX_BYTES   = 20 * 1024 * 1024;
  const STORAGE_KEY = 'pdfagent_v1';
  const MAX_SESSIONS = 40;
  const MAX_MSGS     = 80;

  const $ = (id) => document.getElementById(id);
  const els = {
    histList:    $('history-list'),
    newChatBtn:  $('new-chat-btn'),
    histBanner:  $('hist-banner'),
    hbTitle:     $('hb-title'),
    hbBackBtn:   $('hb-back-btn'),
    messages:    $('chat-messages'),
    pdfTag:      $('pdf-tag'),
    ptName:      $('pt-name'),
    ptMeta:      $('pt-meta'),
    fileInput:   $('file-input'),
    uploadBtn:   $('upload-btn'),
    form:        $('chat-form'),
    input:       $('user-input'),
    send:        $('send-btn'),
    main:        $('main'),
  };

  // ── state ────────────────────────────────────────
  let pdfLoaded       = false;
  let activeSessionId = null;    // current live session
  let viewingId       = null;    // null = live view, else = history view
  let liveHistory     = [];      // [{role,content}] sent to API

  // ── localStorage sessions ────────────────────────
  // Session: { id, title, pdfFilename, createdAt, msgs: [{role,text,sources,isRefusal,isError}] }
  const loadSessions = () => {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }
    catch { return []; }
  };
  const saveSessions = (sessions) => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions.slice(0, MAX_SESSIONS))); }
    catch {}
  };

  let sessions = loadSessions();

  const getSession  = (id) => sessions.find(s => s.id === id);
  const getActive   = () => getSession(activeSessionId);

  const createSession = (pdfFilename) => {
    const s = { id: Date.now().toString(), title: pdfFilename, pdfFilename, createdAt: Date.now(), msgs: [] };
    sessions.unshift(s);
    saveSessions(sessions);
    return s.id;
  };

  const pushMsg = (sessionId, msg) => {
    const s = getSession(sessionId);
    if (!s) return;
    s.msgs.push(msg);
    if (s.msgs.length > MAX_MSGS) s.msgs = s.msgs.slice(-MAX_MSGS);
    // Use first user message as title after the PDF filename phase
    if (!s.titleSet) {
      const first = s.msgs.find(m => m.role === 'user');
      if (first) { s.title = first.text.slice(0, 48) + (first.text.length > 48 ? '…' : ''); s.titleSet = true; }
    }
    saveSessions(sessions);
    renderHistoryList();
  };

  // ── helpers ──────────────────────────────────────
  const esc = (s) =>
    String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
             .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  const renderText = (text) => {
    let h = esc(text);
    h = h.replace(/\[Pages?\s+([0-9,\s]+)\]/gi, (_m, pages) =>
      pages.split(',').map(p => p.trim()).filter(Boolean)
           .map(p => `<span class="citation">p.${p}</span>`).join(' '));
    h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    h = h.replace(/`([^`]+?)`/g, '<code>$1</code>');
    h = h.replace(/\n/g, '<br>');
    return h;
  };

  const sourcesHTML = (sources) => {
    if (!sources || !sources.length) return '';
    const id = 'src-' + Math.random().toString(36).slice(2, 7);
    const items = sources.map(s => `
      <div class="source-item">
        <span class="source-page">Page ${s.page ?? '?'}</span>
        <span class="source-score">${s.score?.toFixed?.(2) ?? s.score}</span>
        <span class="source-preview">${esc(s.preview || '')}</span>
      </div>`).join('');
    return `<div class="sources">
      <button class="sources-toggle" onclick="this.classList.toggle('open');document.getElementById('${id}').classList.toggle('visible')">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
        Sources <span class="src-count">${sources.length}</span>
      </button>
      <div id="${id}" class="sources-body">${items}</div>
    </div>`;
  };

  const scrollBottom = () =>
    requestAnimationFrame(() => { els.messages.scrollTop = els.messages.scrollHeight; });

  const clearEmpty = () => {
    const e = els.messages.querySelector('.empty-state');
    if (e) e.remove();
  };

  const setComposer = (enabled) => {
    els.input.disabled = !enabled;
    els.send.disabled  = !enabled;
    if (enabled) els.input.focus();
  };

  const relativeTime = (ts) => {
    const diff = Date.now() - ts;
    const min = Math.floor(diff / 60000);
    if (min < 1)   return 'Just now';
    if (min < 60)  return `${min}m ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24)   return `${hr}h ago`;
    const d = Math.floor(hr / 24);
    if (d === 1)   return 'Yesterday';
    if (d < 7)     return `${d} days ago`;
    return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };

  // ── render history sidebar ────────────────────────
  const renderHistoryList = () => {
    if (!sessions.length) {
      els.histList.innerHTML = '<p class="history-empty">No conversations yet</p>';
      return;
    }
    els.histList.innerHTML = sessions.map(s => {
      const active = s.id === (viewingId ?? activeSessionId);
      return `<div class="history-item${active ? ' active' : ''}" data-id="${s.id}">
        <span class="hi-title">${esc(s.pdfFilename || s.title)}</span>
        <span class="hi-meta">${relativeTime(s.createdAt)} &nbsp;&middot;&nbsp; ${s.msgs.length} msg${s.msgs.length !== 1 ? 's' : ''}</span>
      </div>`;
    }).join('');
  };

  // ── render a list of stored messages into the DOM ─
  const BOT_AVT = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;

  const renderMsgsFromStore = (msgs) => {
    els.messages.innerHTML = '';
    msgs.forEach(m => appendMsgDOM(m.role, renderText(m.text) + sourcesHTML(m.sources ?? []), m.isRefusal, m.isError));
  };

  const appendMsgDOM = (role, html, isRefusal, isError) => {
    clearEmpty();
    const row = document.createElement('div');
    row.className = `msg-row ${role}${isRefusal ? ' refusal' : ''}${isError ? ' error' : ''}`;
    const avatar = role === 'user' ? 'You' : BOT_AVT;
    row.innerHTML = `<div class="msg-avatar">${avatar}</div><div class="msg-content"><div class="msg-bubble">${html}</div></div>`;
    els.messages.appendChild(row);
    scrollBottom();
    return row;
  };

  const addTypingIndicator = () => {
    clearEmpty();
    const row = document.createElement('div');
    row.className = 'typing-row';
    row.innerHTML = `<div class="typing-avatar">${BOT_AVT.replace('stroke="currentColor"','stroke="#a5b4fc"')}</div><div class="typing-dots"><span></span><span></span><span></span></div>`;
    els.messages.appendChild(row);
    scrollBottom();
    return row;
  };

  // ── switch to live view ───────────────────────────
  const showLiveView = () => {
    viewingId = null;
    els.histBanner.classList.add('hidden');
    const s = getActive();
    if (s) {
      renderMsgsFromStore(s.msgs);
      els.input.placeholder = `Ask about ${s.pdfFilename}…`;
    } else {
      resetMessages();
      els.input.placeholder = 'Ask about the PDF…';
    }
    setComposer(pdfLoaded);
    renderHistoryList();
  };

  // ── switch to history view ────────────────────────
  const showHistoryView = (id) => {
    const s = getSession(id);
    if (!s) return;
    viewingId = id;
    els.hbTitle.textContent = s.pdfFilename;
    els.histBanner.classList.remove('hidden');
    renderMsgsFromStore(s.msgs);
    setComposer(false);
    els.input.placeholder = 'Viewing past session — return to current chat to ask questions';
    renderHistoryList();
  };

  // ── history list click ────────────────────────────
  els.histList.addEventListener('click', (e) => {
    const item = e.target.closest('.history-item');
    if (!item) return;
    const id = item.dataset.id;
    if (id === activeSessionId && !viewingId) return; // already there
    if (id === activeSessionId) { showLiveView(); return; }
    showHistoryView(id);
  });

  // ── back to current chat ──────────────────────────
  els.hbBackBtn.addEventListener('click', showLiveView);

  // ── new chat ──────────────────────────────────────
  els.newChatBtn.addEventListener('click', async () => {
    try { await fetch('/api/reset', { method: 'POST' }); } catch {}
    pdfLoaded       = false;
    activeSessionId = null;
    viewingId       = null;
    liveHistory     = [];
    els.pdfTag.classList.add('hidden');
    els.histBanner.classList.add('hidden');
    els.input.placeholder = 'Ask about the PDF…';
    resetMessages();
    setComposer(false);
    renderHistoryList();
  });

  const resetMessages = () => {
    els.messages.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
          </svg>
        </div>
        <h2 class="empty-title">Chat with any PDF</h2>
        <p class="empty-sub">Click the <span class="inline-kbd">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
        </span> button below to upload a PDF, or drag &amp; drop anywhere on this page.</p>
        <div class="feature-chips">
          <span class="chip">Strict grounding</span>
          <span class="chip">Page citations</span>
          <span class="chip">Refuses off-topic</span>
          <span class="chip">Multilingual</span>
        </div>
      </div>`;
  };

  // ── upload ────────────────────────────────────────
  const handleFile = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      appendMsgDOM('bot', 'Only PDF files are accepted.', false, true);
      return;
    }
    if (file.size > MAX_BYTES) {
      appendMsgDOM('bot', 'File exceeds the 20 MB limit.', false, true);
      return;
    }

    // Return to live view if browsing history
    if (viewingId) showLiveView();

    els.uploadBtn.disabled = true;
    setComposer(false);

    clearEmpty();
    const uploadStatusRow = appendMsgDOM(
      'bot',
      `Uploading <strong>${esc(file.name)}</strong>…<br><small style="opacity:0.55;font-size:0.8em">First request may take ~30 s while the server wakes up from sleep.</small>`,
      false, false
    );

    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: fd });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Upload failed (${res.status})`);
      }
      const d = await res.json();
      uploadStatusRow.remove();

      pdfLoaded = true;
      liveHistory = [];

      // Update PDF tag
      els.ptName.textContent  = d.filename;
      els.ptName.title        = d.filename;
      els.ptMeta.textContent  = `${d.pages}p · ${d.chunks}c`;
      els.pdfTag.classList.remove('hidden');

      // Create new session
      activeSessionId = createSession(d.filename);
      viewingId = null;
      els.histBanner.classList.add('hidden');

      // Show confirmation message
      els.messages.innerHTML = '';
      const confirmMsg = { role: 'bot', text: `**${d.filename}** ready — ${d.pages} pages, ${d.chunks} chunks. Ask me anything about its contents.`, sources: [], isRefusal: false, isError: false };
      pushMsg(activeSessionId, confirmMsg);
      appendMsgDOM('bot', renderText(confirmMsg.text), false, false);

      els.input.placeholder = `Ask about ${d.filename}…`;
      setComposer(true);
      renderHistoryList();
    } catch (e) {
      uploadStatusRow.remove();
      appendMsgDOM('bot', `Upload failed: ${esc(e.message)}`, false, true);
    } finally {
      els.uploadBtn.disabled = false;
      els.fileInput.value = '';
    }
  };

  els.uploadBtn.addEventListener('click', () => els.fileInput.click());
  els.fileInput.addEventListener('change', (e) => handleFile(e.target.files[0]));

  // Drag & drop on whole main area
  els.main.addEventListener('dragover',  (e) => { e.preventDefault(); els.main.style.outline = '2px dashed var(--accent)'; });
  els.main.addEventListener('dragleave', ()  => { els.main.style.outline = ''; });
  els.main.addEventListener('drop', (e) => {
    e.preventDefault();
    els.main.style.outline = '';
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
  });

  // Ctrl+U shortcut
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'u') { e.preventDefault(); els.fileInput.click(); }
  });

  // ── textarea auto-resize ──────────────────────────
  els.input.addEventListener('input', () => {
    els.input.style.height = 'auto';
    els.input.style.height = Math.min(els.input.scrollHeight, 160) + 'px';
  });

  // Enter sends, Shift+Enter is newline
  els.input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); els.form.requestSubmit(); }
  });

  // ── chat submit ───────────────────────────────────
  els.form.addEventListener('submit', async (e) => {
    e.preventDefault();
    // If viewing history, clicking composer returns to live
    if (viewingId) { showLiveView(); els.input.focus(); return; }

    const message = els.input.value.trim();
    if (!message || !pdfLoaded) return;

    appendMsgDOM('user', esc(message), false, false);
    pushMsg(activeSessionId, { role: 'user', text: message, sources: [], isRefusal: false, isError: false });
    liveHistory.push({ role: 'user', content: message });

    els.input.value = '';
    els.input.style.height = 'auto';
    setComposer(false);
    const typing = addTypingIndicator();

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, history: liveHistory.slice(0, -1) }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Request failed (${res.status})`);
      }
      const d = await res.json();
      typing.remove();

      const html = renderText(d.response) + sourcesHTML(d.sources);
      appendMsgDOM('bot', html, !!d.is_refusal, false);
      pushMsg(activeSessionId, { role: 'bot', text: d.response, sources: d.sources ?? [], isRefusal: !!d.is_refusal, isError: false });

      liveHistory.push({ role: 'assistant', content: d.response });
      if (liveHistory.length > 20) liveHistory = liveHistory.slice(-20);
    } catch (e) {
      typing.remove();
      appendMsgDOM('bot', `Error: ${esc(e.message)}`, false, true);
    } finally {
      setComposer(pdfLoaded);
    }
  });

  // ── init ──────────────────────────────────────────
  renderHistoryList();

  (async () => {
    try {
      const res = await fetch('/api/status');
      const d   = await res.json();
      if (d.pdf_loaded) {
        pdfLoaded = true;
        els.ptName.textContent = d.filename;
        els.ptMeta.textContent = `${d.total_pages}p`;
        els.pdfTag.classList.remove('hidden');
        els.input.placeholder  = `Ask about ${d.filename}…`;
        setComposer(true);
      }
    } catch {}
  })();

  // Ping /api/health every 10 min to keep Render free-tier container warm
  setInterval(() => fetch('/api/health').catch(() => {}), 10 * 60 * 1000);
})();
