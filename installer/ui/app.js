'use strict';

const API = 'http://localhost:7315';

// ── Canvas particles ──────────────────────────────────────────
(function initCanvas() {
  const canvas = document.getElementById('bg-canvas');
  const ctx = canvas.getContext('2d');
  const pts = [];
  function resize() { canvas.width = innerWidth; canvas.height = innerHeight; }
  window.addEventListener('resize', resize); resize();
  for (let i = 0; i < 55; i++) pts.push({
    x: Math.random() * canvas.width, y: Math.random() * canvas.height,
    vx: (Math.random() - .5) * .25,  vy: (Math.random() - .5) * .25,
    r: Math.random() * 1.4 + .3,     o: Math.random() * .25 + .04,
  });
  (function tick() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    pts.forEach(p => {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0) p.x = canvas.width;  if (p.x > canvas.width)  p.x = 0;
      if (p.y < 0) p.y = canvas.height; if (p.y > canvas.height) p.y = 0;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(0,212,255,${p.o})`; ctx.fill();
    });
    for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) {
      const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d < 85) {
        ctx.beginPath(); ctx.moveTo(pts[i].x, pts[i].y); ctx.lineTo(pts[j].x, pts[j].y);
        ctx.strokeStyle = `rgba(59,130,246,${.05 * (1 - d / 85)})`; ctx.lineWidth = .5; ctx.stroke();
      }
    }
    requestAnimationFrame(tick);
  })();
})();

// ── Steps ─────────────────────────────────────────────────────
const STEPS = ['splash', 'hardware', 'deps', 'install', 'launch', 'ready'];

function showStep(id) {
  STEPS.forEach(s => {
    const el = document.getElementById('step-' + s);
    if (!el) return;
    if (s === id) { el.classList.remove('exit'); el.classList.add('active'); }
    else if (el.classList.contains('active')) {
      el.classList.add('exit'); el.classList.remove('active');
      setTimeout(() => el.classList.remove('exit'), 500);
    }
  });
}

// ── Helpers ───────────────────────────────────────────────────
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const sleep = ms => new Promise(r => setTimeout(r, ms));

function setBadge(elId, textId, status, text) {
  const el = document.getElementById(elId);
  const tx = document.getElementById(textId);
  el.className = 'overall-badge ' + status;
  const sp = el.querySelector('.badge-spinner'); if (sp) sp.remove();
  tx.textContent = text;
}

function renderError(container, title, detail) {
  container.innerHTML = `
    <div class="error-banner">
      <div class="error-banner-icon">⚠</div>
      <div class="error-banner-body">
        <div class="error-banner-title">${esc(title)}</div>
        <div class="error-banner-msg">${esc(detail)}</div>
      </div>
    </div>`;
}

// ── Splash ────────────────────────────────────────────────────
async function runSplash() {
  const progress = document.getElementById('splash-progress');
  const label    = document.getElementById('splash-label');
  const msgs = [
    [0,   'Initialisation du diagnostic système…'],
    [20,  'Chargement des modules de vérification…'],
    [55,  'Analyse du matériel en cours…'],
    [85,  'Préparation de l\'interface…'],
    [100, 'Prêt !'],
  ];
  for (const [pct, msg] of msgs) {
    await sleep(pct === 0 ? 150 : 480);
    progress.style.width = pct + '%';
    label.textContent = msg;
  }
  await sleep(350);
  showStep('hardware');
  loadHardware();
}

// ── Hardware ──────────────────────────────────────────────────
let hwData = null;

async function loadHardware() {
  const grid     = document.getElementById('hw-checks');
  const tierCard = document.getElementById('gpu-tier-card');
  const nextBtn  = document.getElementById('hw-next');
  grid.innerHTML = '';
  tierCard.style.display = 'none';
  nextBtn.disabled = true;
  setBadge('hw-overall-badge', 'hw-overall-text', '', 'Analyse du matériel en cours…');
  document.getElementById('hw-overall-badge').innerHTML =
    '<div class="badge-spinner"></div><span id="hw-overall-text">Analyse du matériel en cours…</span>';

  try {
    const res = await fetch(API + '/api/hardware');
    if (!res.ok) throw new Error(`HTTP ${res.status} — ${res.statusText}`);
    hwData = await res.json();
    renderHwChecks(hwData, grid, tierCard, nextBtn);
  } catch (e) {
    setBadge('hw-overall-badge', 'hw-overall-text', 'fail', '✗ Erreur de connexion au serveur d\'installation');
    renderError(grid,
      'Impossible de contacter le serveur d\'installation',
      e.message + '\n\nAssurez-vous que setup.bat tourne et réessayez.'
    );
  }
}

function renderHwChecks(data, grid, tierCard, nextBtn) {
  const overall = data.overall || 'fail';
  const icon    = { pass: '✓ ', warn: '⚠ ', fail: '✗ ' }[overall] || '';
  setBadge('hw-overall-badge', 'hw-overall-text', overall, icon + (data.summary || 'Analyse terminée'));

  // GPU tier
  const t = data.gpu_tier;
  if (t && t.tier) {
    tierCard.style.display = '';
    document.getElementById('tier-name').textContent = t.label || t.tier;
    const specs = [
      { val: t.max_cameras,              key: 'Caméras max' },
      { val: t.yolo_model || '—',        key: 'Modèle YOLO' },
      { val: t.batch_size || '—',        key: 'Batch size' },
      { val: (t.target_fps || '?')+' FPS', key: 'FPS cible' },
    ];
    document.getElementById('tier-specs').innerHTML = specs.map(s =>
      `<div class="tier-spec"><span class="spec-val">${esc(s.val)}</span><span class="spec-key">${esc(s.key)}</span></div>`
    ).join('');
  }

  // Check cards
  (data.checks || []).forEach((c, idx) => {
    const card = document.createElement('div');
    card.className = `check-card ${c.status}`;
    card.style.animationDelay = `${idx * 40}ms`;
    card.innerHTML = `
      <div class="check-icon">${ICON[c.status] || ICON.warn}</div>
      <div class="check-info">
        <div class="check-label">${esc(c.label)}</div>
        <div class="check-value">${esc(c.value)}</div>
        <div class="check-detail">${esc(c.detail)}</div>
        ${c.technical ? `<div class="check-technical">${esc(c.technical)}</div>` : ''}
      </div>`;
    grid.appendChild(card);
  });

  if (overall !== 'fail') nextBtn.disabled = false;
}

// ── Deps ──────────────────────────────────────────────────────
let depsData = null;

async function loadDeps() {
  const list    = document.getElementById('deps-list');
  const nextBtn = document.getElementById('deps-next');
  list.innerHTML = '';
  nextBtn.disabled = true;
  document.getElementById('deps-overall-badge').innerHTML =
    '<div class="badge-spinner"></div><span id="deps-overall-text">Vérification en cours…</span>';

  try {
    const res = await fetch(API + '/api/deps');
    if (!res.ok) throw new Error(`HTTP ${res.status} — ${res.statusText}`);
    depsData = await res.json();
    renderDeps(depsData, list, nextBtn);
  } catch (e) {
    setBadge('deps-overall-badge', 'deps-overall-text', 'fail', '✗ Erreur de connexion');
    renderError(list, 'Impossible de vérifier les dépendances', e.message);
  }
}

const DEP_LABEL = { ok: 'OK', missing: 'Absent', outdated: 'Obsolète', error: 'Erreur', installing: 'Installation...' };
const DEP_SVG = {
  ok:   `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  missing: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  outdated:`<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#eab308" stroke-width="2" stroke-linecap="round"><path d="M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>`,
  error:   `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#f97316" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
  installing:`<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>`,
};

function renderDeps(data, list, nextBtn) {
  const fails = (data.deps || []).filter(d => d.status === 'missing' || d.status === 'error');
  const ready = data.ready !== false && fails.filter(d => d.critical).length === 0;

  if (ready) {
    setBadge('deps-overall-badge', 'deps-overall-text', 'pass', '✓ Toutes les dépendances critiques sont présentes');
  } else if (fails.length > 0) {
    setBadge('deps-overall-badge', 'deps-overall-text', 'warn',
      `⚠ ${fails.length} dépendance(s) manquante(s) — l'installation les configurera automatiquement`);
  } else {
    setBadge('deps-overall-badge', 'deps-overall-text', 'warn', '⚠ Vérification partielle');
  }

  for (const d of (data.deps || [])) {
    const item = document.createElement('div');
    item.className = `dep-item ${d.status}`;
    item.innerHTML = `
      <div class="dep-icon">${DEP_SVG[d.status] || DEP_SVG.error}</div>
      <div class="dep-info">
        <div class="dep-name">${esc(d.name)}</div>
        ${d.version ? `<div class="dep-ver">${esc(d.version)}</div>` : ''}
        ${d.note    ? `<div class="dep-note">${esc(d.note)}</div>` : ''}
        ${d.install_cmd ? `<div class="dep-note" style="color:#93c5fd;margin-top:4px">↳ ${esc(d.install_cmd)}</div>` : ''}
      </div>
      <span class="dep-badge">${DEP_LABEL[d.status] || d.status}</span>`;
    list.appendChild(item);
  }

  nextBtn.disabled = false;
  // If everything is already installed, offer fast-path to launch
  const skipBtn = document.getElementById('deps-skip');
  if (skipBtn && fails.length === 0) {
    skipBtn.style.display = '';
  }
}

// ── SVG icon helpers ──────────────────────────────────────────
const ICON = {
  ok:   `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  warn: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#eab308" stroke-width="2" stroke-linecap="round"><path d="M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>`,
  fail: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  pass: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>`,
};

// ── Install ───────────────────────────────────────────────────
function resetInstallStep() {
  const panel = document.getElementById('service-mode-panel');
  const area  = document.getElementById('install-progress-area');
  const log   = document.getElementById('install-log');
  const fill  = document.getElementById('install-fill');
  const pct   = document.getElementById('install-pct');
  const step  = document.getElementById('install-current-step');
  if (panel) panel.style.display = '';
  if (area)  area.style.display = 'none';
  if (log)   log.innerHTML = '';
  if (fill)  fill.style.width = '0%';
  if (pct)   pct.textContent = '0%';
  if (step)  step.textContent = 'Démarrage…';
}

function bindServiceModeSelector() {
  document.querySelectorAll('.mode-opt').forEach(el => {
    el.onclick = () => {
      document.querySelectorAll('.mode-opt').forEach(o => o.classList.remove('selected'));
      el.classList.add('selected');
      const radio = el.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;
    };
  });
}

function startInstall() {
  const mode = document.querySelector('.mode-opt.selected')?.dataset.value || 'auto';
  const panel = document.getElementById('service-mode-panel');
  const area  = document.getElementById('install-progress-area');
  if (panel) panel.style.display = 'none';
  if (area)  area.style.display = '';

  const log   = document.getElementById('install-log');
  const fill  = document.getElementById('install-fill');
  const pct   = document.getElementById('install-pct');
  const step  = document.getElementById('install-current-step');
  const btn   = document.getElementById('install-next');
  log.innerHTML = ''; let progress = 0;
  let hbEl = null; // heartbeat element — reused in place

  function appendLog(text, cls = '') {
    const line = document.createElement('div');
    line.className = 'log-line' + (cls ? ' ' + cls : '');
    line.textContent = text;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
    return line;
  }

  // Animate progress bar slowly while waiting (gives sense of motion)
  let progressTimer = setInterval(() => {
    if (progress < 85) {
      progress += 0.15;
      fill.style.width = progress.toFixed(1) + '%';
      pct.textContent = Math.floor(progress) + '%';
    }
  }, 400);

  try {
    const es = new EventSource(API + '/api/install?start_mode=' + encodeURIComponent(mode));
    es.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        const text = (msg.message || '').trim();
        if (!text) return;

        if (msg.event === 'heartbeat') {
          // Update the heartbeat row in-place (no new line each time)
          if (!hbEl) {
            hbEl = document.createElement('div');
            hbEl.className = 'heartbeat-row';
            hbEl.innerHTML = `<div class="hb-dots"><div class="hb-dot"></div><div class="hb-dot"></div><div class="hb-dot"></div></div><span id="hb-txt"></span>`;
            log.appendChild(hbEl);
          }
          document.getElementById('hb-txt').textContent = text;
          step.textContent = text;
          log.scrollTop = log.scrollHeight;
          return;
        }

        // Any real event removes the heartbeat placeholder
        if (hbEl) { hbEl.remove(); hbEl = null; }

        if (msg.event === 'step' || msg.event === 'start') {
          appendLog('  ' + text, 'step');
          step.textContent = text;
          progress = Math.min(progress + 8, 88);
          fill.style.width = progress.toFixed(1) + '%';
          pct.textContent = Math.floor(progress) + '%';
        } else if (msg.event === 'ok') {
          appendLog('  ' + text, 'ok');
        } else if (msg.event === 'warn') {
          appendLog('  ' + text, 'warn');
        } else if (msg.event === 'fix') {
          appendLog('  ' + text, 'fix');
          step.textContent = text;
        } else if (msg.event === 'error') {
          appendLog('  ' + text, 'error');
        } else if (msg.event === 'info' || msg.event === 'log') {
          appendLog('  ' + text, 'info');
        } else if (msg.event === 'done') {
          clearInterval(progressTimer);
          fill.style.width = '100%'; pct.textContent = '100%';
          step.textContent = 'Installation terminée';
          appendLog('  ' + text, 'ok');
          es.close();
          // Auto-transition to launch step
          setTimeout(() => { showStep('launch'); startLaunch(); }, 800);
        } else {
          appendLog('  ' + text);
        }
      } catch {
        appendLog(e.data);
      }
    };
    es.onerror = () => {
      clearInterval(progressTimer);
      appendLog('  Connexion interrompue — vérifiez la fenêtre setup.bat', 'error');
      es.close();
    };
  } catch (e) {
    clearInterval(progressTimer);
    appendLog('  ' + e.message, 'error');
  }
}

// ── Launch ────────────────────────────────────────────────────
function startLaunch() {
  const log      = document.getElementById('launch-log');
  const fill     = document.getElementById('launch-fill');
  const pct      = document.getElementById('launch-pct');
  const step     = document.getElementById('launch-current-step');
  const btn      = document.getElementById('launch-open-btn');
  const btnArea  = btn.parentNode;
  log.innerHTML  = '';
  let progress   = 0;
  let hbEl       = null;
  let aiOk       = false;
  let aiFailed   = false;
  let launchReady = false;
  let appUrl     = 'http://localhost:5174';
  let bannerEl   = null;
  let waitingEl  = null;

  function appendLog(text, cls = '') {
    const line = document.createElement('div');
    line.className = 'log-line' + (cls ? ' ' + cls : '');
    line.textContent = text;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
  }

  function removeBanner() {
    if (bannerEl) { bannerEl.remove(); bannerEl = null; }
  }

  function showBanner(msg, type /* 'warn' | 'fail' */) {
    removeBanner();
    bannerEl = document.createElement('div');
    bannerEl.className = type === 'fail' ? 'ai-fail-banner' : 'ai-warn-banner';
    const icon = type === 'fail'
      ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`
      : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
    bannerEl.innerHTML = icon + `<span>${msg}</span>`;
    const logParent = log.parentNode;
    if (logParent) logParent.insertBefore(bannerEl, log);
  }

  function showAiWaiting() {
    if (waitingEl) return;
    waitingEl = document.createElement('div');
    waitingEl.className = 'ai-waiting-indicator';
    waitingEl.innerHTML =
      `<div class="ai-waiting-dots"><div></div><div></div><div></div></div>` +
      `<span id="ai-waiting-txt">Initialisation de l'IA en cours…</span>`;
    btnArea.insertBefore(waitingEl, btn);
  }

  function removeAiWaiting() {
    if (waitingEl) { waitingEl.remove(); waitingEl = null; }
  }

  let serviceRegEl = null;

  function removeServiceWaiting() {
    if (serviceRegEl) { serviceRegEl.remove(); serviceRegEl = null; }
  }

  function showServiceWaiting() {
    removeServiceWaiting();
    serviceRegEl = document.createElement('div');
    serviceRegEl.className = 'ai-waiting-indicator';
    serviceRegEl.innerHTML =
      `<div class="ai-waiting-dots"><div></div><div></div><div></div></div>` +
      `<span>Enregistrement du service système…</span>`;
    btnArea.insertBefore(serviceRegEl, btn);
  }

  async function openCiteVision(url) {
    btn.disabled = true;
    showServiceWaiting();
    step.textContent = 'Enregistrement du service CitéVision…';
    try {
      const res = await fetch(API + '/api/register-service');
      // Guard: server may return non-JSON (404, plain text) if older version running
      const text = await res.text();
      let data = null;
      try { data = JSON.parse(text); } catch (_) { /* ignore */ }
      removeServiceWaiting();
      if (data && data.ok) {
        appendLog('  ' + (data.message || 'Service enregistré'), data.skipped ? 'warn' : 'ok');
        step.textContent = data.skipped ? 'Application prête' : 'Service enregistré — ouverture…';
      } else if (data && !data.ok) {
        appendLog('  ' + (data.message || 'Service non enregistré — ouverture directe'), 'warn');
        step.textContent = 'Ouverture de l\'application…';
      } else {
        appendLog('  Service non disponible — ouverture directe', 'warn');
        step.textContent = 'Ouverture de l\'application…';
      }
      window.open(url, '_blank');
      btn.disabled = false;
    } catch (err) {
      removeServiceWaiting();
      appendLog('  Ouverture directe (service non joignable)', 'warn');
      step.textContent = 'Ouverture de l\'application…';
      window.open(url, '_blank');
      btn.disabled = false;
    }
  }

  const timer = setInterval(() => {
    if (progress < 90) { progress += 0.2; fill.style.width = progress.toFixed(1) + '%'; pct.textContent = Math.floor(progress) + '%'; }
  }, 500);

  const es = new EventSource(API + '/api/launch');
  es.onmessage = (e) => {
    try {
      const msg  = JSON.parse(e.data);
      const text = (msg.message || '').trim();
      if (!text) return;

      // ── Heartbeat ────────────────────────────────────────────
      if (msg.event === 'heartbeat') {
        if (!hbEl) {
          hbEl = document.createElement('div');
          hbEl.className = 'heartbeat-row';
          hbEl.innerHTML = `<div class="hb-dots"><div class="hb-dot"></div><div class="hb-dot"></div><div class="hb-dot"></div></div><span id="hb-launch-txt"></span>`;
          log.appendChild(hbEl);
        }
        document.getElementById('hb-launch-txt').textContent = text;
        step.textContent = text;
        log.scrollTop = log.scrollHeight;
        return;
      }
      if (hbEl) { hbEl.remove(); hbEl = null; }

      // ── AI prête ─────────────────────────────────────────────
      // ai_ready arrive toujours avant launch_ready dans le flux SSE.
      // On mémorise aiOk=true ; c'est launch_ready qui activera le bouton.
      if (msg.event === 'ai_ready') {
        aiOk = true;
        removeBanner();
        removeAiWaiting();
        appendLog('  ' + text, 'ok');
        step.textContent = 'IA active — prête à détecter';
        if (launchReady) {
          fill.style.width = '100%'; pct.textContent = '100%';
          btn.disabled = false;
          btn.onclick = () => openCiteVision(appUrl);
        }
        return;
      }

      // ── AI échouée ───────────────────────────────────────────
      if (msg.event === 'ai_fail') {
        aiFailed = true;
        removeAiWaiting();
        appendLog('  ' + text, 'error');
        showBanner(text, 'fail');
        step.textContent = 'Correction IA en cours ou échec — voir logs';
        return;
      }

      if (msg.event === 'fix') {
        removeBanner();
        appendLog('  ' + text, 'fix');
        step.textContent = text;
        return;
      }

      // ── Interface prête (5174) ────────────────────────────────
      if (msg.event === 'launch_ready') {
        clearInterval(timer);
        if (aiOk) {
          fill.style.width = '100%'; pct.textContent = '100%';
        }
        appUrl = text || appUrl;
        launchReady = true;
        appendLog('  Interface CitéVision accessible', 'ok');

        if (aiOk) {
          step.textContent = 'Application prête — IA active';
          removeBanner();
          removeAiWaiting();
          btn.disabled = false;
          btn.onclick = () => openCiteVision(appUrl);
        } else if (aiFailed) {
          step.textContent = 'Interface prête — gate IA non validée';
          showBanner('Les corrections automatiques n\'ont pas abouti — consultez les logs', 'fail');
        } else {
          step.textContent = 'Interface prête — finalisation IA…';
          showAiWaiting();
          showBanner('Correction automatique de l\'IA en cours…', 'warn');
        }
        es.close();
        return;
      }

      // ── Autres événements ────────────────────────────────────
      if (msg.event === 'step') {
        appendLog('  ' + text, 'step');
        step.textContent = text;
        progress = Math.min(progress + 6, 88);
        fill.style.width = progress.toFixed(1) + '%'; pct.textContent = Math.floor(progress) + '%';
      } else if (msg.event === 'ok')    { appendLog('  ' + text, 'ok'); }
      else if (msg.event === 'fix')     { appendLog('  ' + text, 'fix'); step.textContent = text; }
      else if (msg.event === 'warn')    { appendLog('  ' + text, 'warn'); }
      else if (msg.event === 'error')   { appendLog('  ' + text, 'error'); clearInterval(timer); }
      else if (msg.event === 'info')    { appendLog('  ' + text, 'info'); }
      else                              { appendLog('  ' + text); }
    } catch { appendLog(e.data); }
  };
  es.onerror = () => { clearInterval(timer); appendLog('  Connexion interrompue', 'error'); es.close(); };
}

// ── Navigation ────────────────────────────────────────────────
function goToHardware() { showStep('hardware'); loadHardware(); }
function goToDeps()     { showStep('deps');     loadDeps(); }
function goToInstall()  { showStep('install'); resetInstallStep(); bindServiceModeSelector(); }
function goToLaunch()   { showStep('launch');   startLaunch(); }
function goToReady()    { showStep('ready'); }

window.app = { loadHardware, goToHardware, loadDeps, goToDeps, goToInstall, goToLaunch, goToReady, startInstall, startLaunch, resetInstallStep };

async function loadVersionBanner() {
  const el = document.getElementById('install-version');
  if (!el) return;
  try {
    const res = await fetch(API + '/api/version');
    const data = await res.json();
    if (data.commit && data.commit !== 'unknown') {
      el.textContent = `Build ${data.commit}`;
    }
  } catch { /* optional footer */ }
}

// ── Boot ──────────────────────────────────────────────────────
loadVersionBanner();
runSplash();
