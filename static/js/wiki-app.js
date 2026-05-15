import { api } from './api.js';
import { roleLabels, roleUsernames } from './config.js';
import { state } from './state.js';
import {
  renderWikiBrowser,
  loadWikiTree,
  loadWikiPage,
  showWikiEditor,
  saveWikiPage,
  deleteWikiPage,
  submitPageForReview,
  searchWiki,
  searchWikiFromTOC,
  filterWikiTree,
  toggleTreeNode,
  showLinkSearchModal,
  closeLinkSearchModal,
  searchWikiPagesForLink,
  insertWikiLink,
} from './tabs/wiki.js';

// --- Auth ---

async function checkAuth() {
  try {
    const data = await api('/api/auth/me');
    if (data.authenticated) {
      state.role = data.role;
      state.username = data.username;
      state.displayName = data.display_name || data.username;
      return true;
    }
  } catch (e) { /* fall through to login */ }
  return false;
}

async function doLogin(role) {
  const username = roleUsernames[role];
  const data = await api('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role, username }),
  });
  state.role = data.role;
  state.username = data.username;
  state.displayName = data.display_name || data.username;
  if (data.session_id) {
    sessionStorage.setItem('session_id', data.session_id);
  }
}

async function doLogout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
  } catch (e) { /* ignore */ }
  sessionStorage.removeItem('session_id');
  state.role = null;
  renderApp();
}

// --- Render ---

function renderLogin() {
  const app = document.getElementById('app');
  if (!app) return;

  app.innerHTML = `
    <div class="login-overlay">
      <div class="login-card" style="max-width:380px;">
        <h2>智云科技 · 知识库</h2>
        <div class="subtitle">请选择角色进入</div>
        <div class="role-grid">
          <a href="#" class="role-card" id="login-cs">
            <div class="role-icon">💬</div>
            <div class="role-name">客服</div>
            <div class="role-desc">浏览 D1 知识库</div>
          </a>
          <a href="#" class="role-card" id="login-rd">
            <div class="role-icon">🔧</div>
            <div class="role-name">二线研发</div>
            <div class="role-desc">浏览全部知识库</div>
          </a>
          <a href="#" class="role-card" id="login-doc" style="grid-column:1/-1;">
            <div class="role-icon">📄</div>
            <div class="role-name">文档团队</div>
            <div class="role-desc">浏览 + 编辑知识库</div>
          </a>
        </div>
      </div>
    </div>`;

  document.getElementById('login-cs').onclick = (e) => { e.preventDefault(); doLogin('cs').then(renderApp); };
  document.getElementById('login-rd').onclick = (e) => { e.preventDefault(); doLogin('rd').then(renderApp); };
  document.getElementById('login-doc').onclick = (e) => { e.preventDefault(); doLogin('doc').then(renderApp); };
}

async function renderApp() {
  const app = document.getElementById('app');
  if (!app) return;

  if (!state.role) {
    const authed = await checkAuth();
    if (!authed) {
      renderLogin();
      return;
    }
  }

  app.innerHTML = `
    <div class="header wiki-header">
      <h1>智云科技 · 知识库</h1>
      <div class="wiki-header-search">
        <input type="text" id="wikiInpageSearch" placeholder="搜索文档..."
          oninput="app.searchWikiFromTOC()"
          onkeydown="if(event.key==='Escape'){this.value='';app.searchWikiFromTOC();}">
        <div class="wiki-header-search-results" id="wikiTOCResults" style="display:none;"></div>
      </div>
      <div class="header-right">
        <span class="role-badge ${state.role}">${roleLabels[state.role]}: ${state.displayName || state.username}</span>
        <button class="btn-sm" onclick="app.doLogout()">退出</button>
      </div>
    </div>
    ${renderWikiBrowser()}`;

  await loadWikiTree();

  // Auto-navigate to slug from URL path (e.g., /wiki/bgp)
  const pathParts = window.location.pathname.replace(/\/$/, '').split('/');
  const slugFromPath = pathParts[pathParts.length - 1];
  if (slugFromPath && slugFromPath !== 'wiki' && slugFromPath.length > 0) {
    loadWikiPage(slugFromPath);
  }

  initWikiResize();
}

function initWikiResize() {
  const handle = document.getElementById('wikiResizeHandle');
  const sidebar = document.querySelector('.wiki-sidebar');
  if (!handle || !sidebar) return;

  let dragging = false;
  let startX = 0;
  let startWidth = 0;

  handle.addEventListener('mousedown', (e) => {
    dragging = true;
    startX = e.clientX;
    startWidth = sidebar.offsetWidth;
    handle.classList.add('active');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const delta = e.clientX - startX;
    const newWidth = Math.min(500, Math.max(180, startWidth + delta));
    sidebar.style.width = newWidth + 'px';
    sidebar.style.flex = '0 0 ' + newWidth + 'px';
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
}

// --- Exports ---

window.app = {
  renderApp,

  // Auth
  doLogin,
  doLogout,

  // Wiki browser
  loadWikiTree,
  loadWikiPage,
  showWikiEditor,
  saveWikiPage,
  deleteWikiPage,
  submitPageForReview,
  searchWiki,
  searchWikiFromTOC,
  filterWikiTree,
  toggleTreeNode,
  showLinkSearchModal,
  closeLinkSearchModal,
  searchWikiPagesForLink,
  insertWikiLink,
};

// --- Init ---
renderApp();
