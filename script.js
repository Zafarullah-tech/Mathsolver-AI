/* ════════════════════════════════════════════════════════════
   MathSolver AI  —  script.js   (fixed sidebar + theme)
   ════════════════════════════════════════════════════════════ */

let history  = [];
let busy     = false;
let tipTimer = null;

// Track sidebar state explicitly
let sidebarOpen = true;

const TIPS = [
  'Applying math rules...',
  'Computing symbolically...',
  'Simplifying result...',
  'Verifying answer...',
  'Almost done...',
];

// ── BOOT ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadHistory();
  renderWelcome();
  initTheme();
  updateMenuIcon();
});

// ── THEME ─────────────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem('ms_theme') || 'dark';
  applyTheme(saved);
}

function applyTheme(mode) {
  const body = document.body;
  const btn  = document.getElementById('themeBtn');
  if (mode === 'light') {
    body.classList.add('light-mode');
    if (btn) btn.textContent = '☀️';
    if (btn) btn.title = 'Switch to Dark Mode';
  } else {
    body.classList.remove('light-mode');
    if (btn) btn.textContent = '🌙';
    if (btn) btn.title = 'Switch to Light Mode';
  }
  localStorage.setItem('ms_theme', mode);
}

function toggleTheme() {
  const isDark = !document.body.classList.contains('light-mode');
  applyTheme(isDark ? 'light' : 'dark');
}

// ── SIDEBAR ───────────────────────────────────────────────────
function toggleSidebar() {
  const sb   = document.getElementById('sidebar');
  const isMobile = window.innerWidth <= 768;

  if (isMobile) {
    // On mobile: toggle mobile-open class
    sb.classList.toggle('mobile-open');
  } else {
    // On desktop: toggle open/collapsed state
    sidebarOpen = !sidebarOpen;
    if (sidebarOpen) {
      sb.classList.remove('collapsed');
    } else {
      sb.classList.add('collapsed');
    }
  }
  updateMenuIcon();
}

function updateMenuIcon() {
  const btn = document.getElementById('menuToggleBtn');
  if (!btn) return;
  const isMobile = window.innerWidth <= 768;
  if (isMobile) {
    btn.textContent = '☰';
    btn.title = 'Toggle menu';
  } else {
    btn.textContent = sidebarOpen ? '◀' : '▶';
    btn.title = sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar';
  }
}

// Update icon on resize
window.addEventListener('resize', updateMenuIcon);

// ── WELCOME ───────────────────────────────────────────────────
function renderWelcome() {
  const pane = document.getElementById('messagesContainer');
  pane.innerHTML = `
    <div class="welcome-screen">
      <div class="welcome-logo">∑</div>
      <h2>MathSolver AI</h2>
      <p>Symbolic math engine — step-by-step solutions</p>

      <div class="caps-grid">
        <div class="cap-card"><span class="cap-sym">∂</span><span class="cap-name">Derivatives</span></div>
        <div class="cap-card"><span class="cap-sym">∫</span><span class="cap-name">Integrals</span></div>
        <div class="cap-card"><span class="cap-sym">lim</span><span class="cap-name">Limits</span></div>
        <div class="cap-card"><span class="cap-sym">Σ</span><span class="cap-name">Series</span></div>
        <div class="cap-card"><span class="cap-sym">=</span><span class="cap-name">Equations</span></div>
        <div class="cap-card"><span class="cap-sym">≈</span><span class="cap-name">Simplify</span></div>
      </div>

      <p class="try-label">Try an example:</p>
      <div class="examples">
        <button class="ex-pill" onclick="useEx('derivative of ln(1 + x^2)')">d/dx [ln(1+x²)]</button>
        <button class="ex-pill" onclick="useEx('integrate x^2 * sin(x)')">∫ x² sin(x) dx</button>
        <button class="ex-pill" onclick="useEx('solve 2*x^2 - 4*x - 6 = 0')">2x² − 4x − 6 = 0</button>
        <button class="ex-pill" onclick="useEx('limit of sin(x)/x as x approaches 0')">lim sin(x)/x</button>
        <button class="ex-pill" onclick="useEx('taylor series of exp(x) 5 terms')">Taylor eˣ (5 terms)</button>
        <button class="ex-pill" onclick="useEx('factor x^2 - 5*x + 6')">factor x²−5x+6</button>
      </div>
    </div>
  `;
}

// ── SEND ──────────────────────────────────────────────────────
async function sendMessage() {
  if (busy) return;

  const input = document.getElementById('userInput');
  const text  = input.value.trim();
  if (!text) return;
  if (text.length > 500) { alert('Message too long (max 500 chars)'); return; }

  const welcome = document.querySelector('.welcome-screen');
  if (welcome) welcome.remove();

  addUserBubble(text);
  input.value = '';
  autoResize(input);
  updateCounter();

  startLoading();
  busy = true;

  try {
    const res  = await fetch('/chat', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ message: text }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    addBotBubble(data);
  } catch (err) {
    addErrorBubble('Network error: ' + err.message);
  } finally {
    stopLoading();
    busy = false;
  }
}

// ── USER BUBBLE ───────────────────────────────────────────────
function addUserBubble(text) {
  const pane = document.getElementById('messagesContainer');
  const el   = document.createElement('div');
  el.className = 'msg user';
  el.innerHTML = `
    <div class="msg-avatar">U</div>
    <div class="msg-body">
      <div class="msg-meta">${ts()}</div>
      <div class="msg-bubble">${esc(text)}</div>
    </div>
  `;
  pane.appendChild(el);
  scrollDown();
  history.push({ role:'user', text, time:ts() });
  saveHistory();
}

// ── BOT BUBBLE ────────────────────────────────────────────────
function addBotBubble(data) {
  const pane = document.getElementById('messagesContainer');
  const el   = document.createElement('div');
  el.className = 'msg bot';

  let inner = '';

  if (data.conversational) {
    inner += `<div class="conv-bubble">${esc(data.answer || '')}</div>`;
    if (data.steps) {
      inner += `<div class="steps-wrap" style="margin-top:12px;">${data.steps}</div>`;
    }
  } else {
    if (data.operation) {
      inner += `<div class="op-badge">${esc(data.operation)}</div>`;
    }
    if (data.success && data.answer) {
      inner += `
        <div class="answer-strip">
          <span class="ans-label">ANSWER</span>
          <span class="ans-value">${esc(data.answer)}</span>
        </div>
      `;
    }
    if (data.steps) {
      inner += `<div class="steps-wrap">${data.steps}</div>`;
    }
    if (!data.success && !data.steps) {
      inner += `<div class="error-note">⚠️ Could not solve. Check your input format.</div>`;
    }
  }

  el.innerHTML = `
    <div class="msg-avatar">∑</div>
    <div class="msg-body">
      <div class="msg-meta">${ts()}</div>
      <div class="msg-bubble">${inner}</div>
    </div>
  `;
  pane.appendChild(el);
  scrollDown();
  history.push({ role:'bot', answer: data.answer, time:ts() });
  saveHistory();
}

// ── ERROR BUBBLE ──────────────────────────────────────────────
function addErrorBubble(msg) {
  const pane = document.getElementById('messagesContainer');
  const el   = document.createElement('div');
  el.className = 'msg bot';
  el.innerHTML = `
    <div class="msg-avatar">∑</div>
    <div class="msg-body">
      <div class="msg-meta">${ts()}</div>
      <div class="msg-bubble">
        <div class="error-note">⚠️ ${esc(msg)}</div>
      </div>
    </div>
  `;
  pane.appendChild(el);
  scrollDown();
}

// ── LOADING ───────────────────────────────────────────────────
function startLoading() {
  const shield = document.getElementById('loadingShield');
  const txt    = document.getElementById('loadingText');
  shield.classList.add('on');
  let i = 0;
  txt.textContent = TIPS[0];
  tipTimer = setInterval(() => {
    i = (i + 1) % TIPS.length;
    txt.textContent = TIPS[i];
  }, 1400);
}

function stopLoading() {
  document.getElementById('loadingShield').classList.remove('on');
  clearInterval(tipTimer);
}

// ── NEW / CLEAR ───────────────────────────────────────────────
function newChat() {
  history = [];
  saveHistory();
  renderWelcome();
  document.getElementById('chatHistory').innerHTML = '<p class="empty-history">No history yet</p>';
}

function clearChat() {
  if (confirm('Clear all messages?')) newChat();
}

// ── EXPORT ────────────────────────────────────────────────────
function exportChat() {
  if (!history.length) { alert('Nothing to export yet.'); return; }
  let out = `MathSolver AI — Export\n${'='.repeat(44)}\n\n`;
  history.forEach(m => {
    out += `[${m.role.toUpperCase()}] ${m.time}\n`;
    out += (m.text || m.answer || '') + '\n\n' + '-'.repeat(30) + '\n\n';
  });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([out], { type:'text/plain' }));
  a.download = `math-export-${new Date().toISOString().slice(0,10)}.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── TEXTAREA ──────────────────────────────────────────────────
function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = el.scrollHeight + 'px';
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

function updateCounter() {
  const n = document.getElementById('userInput').value.length;
  const c = document.getElementById('charCounter');
  c.textContent = `${n} / 500`;
  c.style.color  = n > 450 ? 'var(--red)' : '';
}

function clearInput() {
  const el = document.getElementById('userInput');
  el.value = '';
  autoResize(el);
  updateCounter();
}

// ── EXAMPLES / QUICK INSERT ───────────────────────────────────
function useEx(text) {
  const el = document.getElementById('userInput');
  el.value = text;
  autoResize(el);
  updateCounter();
  sendMessage();
}

function insertExample(type) {
  const map = {
    derivative : 'derivative of x^3 + 2*x^2 - 5*x + 3',
    integral   : 'integrate exp(x) * sin(x)',
    equation   : 'solve 2*x^2 - 4*x - 6 = 0',
    limit      : 'limit of sin(x)/x as x approaches 0',
    series     : 'taylor series of sin(x) 6 terms',
    simplify   : 'simplify (x^2 - 1) / (x - 1)',
  };
  const el = document.getElementById('userInput');
  el.value = map[type] || '';
  autoResize(el);
  updateCounter();
  el.focus();
}

// ── SYMBOL PICKER ─────────────────────────────────────────────
function openSymbols()  { document.getElementById('symbolModal').classList.add('open');  }
function closeSymbols() { document.getElementById('symbolModal').classList.remove('open'); }

function ins(sym) {
  const el = document.getElementById('userInput');
  const s  = el.selectionStart, e2 = el.selectionEnd;
  el.value = el.value.slice(0, s) + sym + el.value.slice(e2);
  el.selectionStart = el.selectionEnd = s + sym.length;
  el.focus();
  updateCounter();
  autoResize(el);
  closeSymbols();
}

// ── HISTORY ───────────────────────────────────────────────────
function saveHistory() {
  try {
    localStorage.setItem('ms_history', JSON.stringify(history.slice(-60)));
    renderHistoryList();
  } catch (_) {}
}

function loadHistory() {
  try {
    const saved = localStorage.getItem('ms_history');
    if (saved) { history = JSON.parse(saved); renderHistoryList(); }
  } catch (_) {}
}

function renderHistoryList() {
  const el = document.getElementById('chatHistory');
  if (!el) return;
  const user_msgs = history.filter(m => m.role === 'user').slice(-6).reverse();
  if (!user_msgs.length) {
    el.innerHTML = '<p class="empty-history">No history yet</p>';
    return;
  }
  el.innerHTML = user_msgs.map(m => {
    const t = m.text || '';
    const preview = t.length > 38 ? t.slice(0,38) + '…' : t;
    return `<div class="hist-item" onclick="restoreQ(${JSON.stringify(t)})" title="${esc(t)}">${esc(preview)}</div>`;
  }).join('');
}

function restoreQ(text) {
  const el = document.getElementById('userInput');
  el.value = text;
  autoResize(el);
  updateCounter();
  el.focus();
}

// ── UTILS ─────────────────────────────────────────────────────
function esc(str) {
  const d = document.createElement('div');
  d.textContent = String(str || '');
  return d.innerHTML;
}

function ts() {
  return new Date().toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit', hour12:true });
}

function scrollDown() {
  const pane = document.getElementById('messagesContainer');
  pane.scrollTop = pane.scrollHeight;
}