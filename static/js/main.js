import { setUnauthorizedHandler } from './api.js';
import { checkAuth, handleUnauthorized, login, logout, setRenderApp } from './auth.js';
import { roleLabels, roleTabs, tabLabels } from './config.js';
import { doEscalate, loadTickets, showHandlingForm, showTicketDetail } from './features/tickets.js';
import { state, resetSessionState } from './state.js';
import { copyText, showTextPreview, toast } from './utils.js';
import {
  createTicket,
  renderCSTickets,
  renderCSQuery,
  newChat,
  submitChat,
  createTicketFromChat,
  scrollChatBottom,
  initCSSessions,
} from './tabs/cs.js';
import {
  loadPendingReviews,
  renderDocReview,
  reviewKnowledge,
} from './tabs/doc.js';
import {
  renderWikiBrowser,
  loadWikiTree,
  loadWikiPage,
  showWikiEditor,
  saveWikiPage,
  deleteWikiPage,
  submitPageForReview,
  searchWiki,
  toggleTreeNode,
} from './tabs/wiki.js';
import { loadMetrics, renderAllTickets, renderDashboard, loadManagerTickets, setTicketFilter } from './tabs/manager.js';
import {
  renderRDEscalations,
  initRDSessions,
} from './tabs/rd.js';
import {
  loadAgentSessions,
  renderSessionWorkspace,
  openSession,
  sendReply,
  askAIForMessage,
  askAIDirectly,
  aiFollowUp,
  handleTicket,
  escalateSession,
  acceptEscalation,
  endService,
  closeAIPanel,
  backToSessionList,
  refreshSessions,
} from './agent-workspace.js';

const tabRenderers = {
  sessions: renderCSQuery,
  tickets: renderCSTickets,
  escalations: renderRDEscalations,
  'review-knowledge': renderDocReview,
  'wiki-browser': renderWikiBrowser,
  dashboard: renderDashboard,
  'all-tickets': renderAllTickets,
};

function renderLogin() {
  return `
    <div class="login-overlay">
      <div class="login-card">
        <h2>智云科技 · AI 知识库系统</h2>
        <div class="subtitle">请选择角色进入系统（每个角色可在独立标签页打开）</div>
        <div class="role-grid">
          <a href="/cs" class="role-card" style="text-decoration:none;color:inherit;">
            <div class="role-icon">💬</div>
            <div class="role-name">客服</div>
            <div class="role-desc">在线服务 · 工单管理</div>
          </a>
          <a href="/rd" class="role-card" style="text-decoration:none;color:inherit;">
            <div class="role-icon">🔧</div>
            <div class="role-name">二线研发</div>
            <div class="role-desc">升级处理 · 知识沉淀</div>
          </a>
          <a href="/doc" class="role-card" style="text-decoration:none;color:inherit;">
            <div class="role-icon">📄</div>
            <div class="role-name">文档团队</div>
            <div class="role-desc">提交知识 · 审核</div>
          </a>
          <a href="/manager" class="role-card" style="text-decoration:none;color:inherit;">
            <div class="role-icon">📊</div>
            <div class="role-name">管理层</div>
            <div class="role-desc">仪表盘 · 汇总</div>
          </a>
        </div>
        <p style="margin-top:20px;font-size:12px;color:var(--muted);">
          每个角色在独立标签页中运行，互不干扰
        </p>
      </div>
    </div>`;
}

function renderMain() {
  const tabs = roleTabs[state.role];
  const navButtons = tabs
    .map((tab) => `<button class="${tab === state.currentTab ? 'active' : ''}" onclick="app.switchTab('${tab}')">${tabLabels[tab] || tab}</button>`)
    .join('');
  const tabPanels = tabs
    .map((tab) => `<div id="tab-${tab}" class="tab">${tabRenderers[tab]()}</div>`)
    .join('');

  return `
    <div class="header">
      <h1>智云科技 · AI 知识库系统</h1>
      <div class="header-right">
        <span class="role-badge ${state.role}">${roleLabels[state.role]}: ${state.displayName || state.username}</span>
        <button class="btn-sm" onclick="app.logout()">退出</button>
      </div>
    </div>
    <nav>${navButtons}</nav>
    ${tabPanels}`;
}

export function renderApp() {
  const root = document.getElementById('app');
  if (!root) return;

  if (!state.role) {
    root.innerHTML = renderLogin();
    return;
  }

  const tabs = roleTabs[state.role];
  if (!tabs.includes(state.currentTab)) {
    state.currentTab = tabs[0];
  }

  root.innerHTML = renderMain();
  switchTab(state.currentTab);
}

export function switchTab(name) {
  const tabs = state.role ? roleTabs[state.role] : [];
  if (!tabs.includes(name)) return;

  state.currentTab = name;
  document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(btn => btn.classList.remove('active'));

  const activeTab = document.getElementById(`tab-${name}`);
  if (activeTab) activeTab.classList.add('active');

  const activeButton = document.querySelector(`nav button[onclick="app.switchTab('${name}')"]`);
  if (activeButton) activeButton.classList.add('active');

  // Initialize sessions tab
  if (name === 'sessions' && state.role === 'cs') {
    initCSSessions();
  }
  if (name === 'escalations' && state.role === 'rd') {
    initRDSessions();
  }
  if (name === 'tickets') {
    void loadTickets();
  }
  if (name === 'all-tickets') {
    void loadManagerTickets();
  }
  if (name === 'dashboard') {
    void loadMetrics();
  }
  if (name === 'review-knowledge') {
    void loadPendingReviews();
  }
  if (name === 'wiki-browser') {
    void loadWikiTree();
  }
}

function closeCard(button) {
  const card = button.closest('.card');
  if (card) card.remove();
}

window.app = {
  // Core
  renderApp,

  // Legacy
  copyText,
  createTicket,
  createTicketFromChat,
  doEscalate,
  loadMetrics,
  loadManagerTickets,
  setTicketFilter,
  loadPendingReviews,
  loadTickets,
  login,
  logout,
  newChat,
  reviewKnowledge,
  showHandlingForm,
  showTextPreview,
  showTicketDetail,
  submitChat,
  switchTab,
  closeCard,

  // Session workspace
  loadAgentSessions,
  renderCSQuery,
  renderCSTickets,
  renderRDEscalations,
  openSession,
  sendReply,
  askAIForMessage,
  askAIDirectly,
  aiFollowUp,
  handleTicket,
  escalateSession,
  acceptEscalation,
  endService,
  closeAIPanel,
  backToSessionList,
  refreshSessions,
  scrollChatBottom,

  // Wiki browser
  loadWikiTree,
  loadWikiPage,
  showWikiEditor,
  saveWikiPage,
  deleteWikiPage,
  submitPageForReview,
  searchWiki,
  toggleTreeNode,
};

function autoLoginFromPath() {
  const path = location.pathname.replace(/\/$/, '');
  const roleMap = { '/cs': 'cs', '/rd': 'rd', '/doc': 'doc', '/manager': 'manager' };
  const role = roleMap[path];
  if (role) {
    login(role);
    return true;
  }
  return false;
}

setRenderApp(renderApp);
setUnauthorizedHandler(handleUnauthorized);

if (!autoLoginFromPath()) {
  void checkAuth();
}
