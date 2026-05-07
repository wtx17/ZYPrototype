import { setUnauthorizedHandler } from './api.js';
import { checkAuth, handleUnauthorized, login, logout, setRenderApp, switchRole } from './auth.js';
import { roleLabels, roleTabs, tabLabels } from './config.js';
import { doEscalate, loadTickets, showHandlingForm, showTicketDetail } from './features/tickets.js';
import { state } from './state.js';
import { copyText, showTextPreview } from './utils.js';
import {
  createTicket,
  createTicketFromChat,
  newChat,
  renderCSQuery,
  renderCSTickets,
  renderDesensitize,
  scrollChatBottom,
  submitChat,
  testDesensitize,
} from './tabs/cs.js';
import {
  loadPendingReviews,
  renderDocReview,
  renderDocSubmit,
  reviewKnowledge,
  submitKnowledge,
} from './tabs/doc.js';
import { loadMetrics, renderAllTickets, renderDashboard } from './tabs/manager.js';
import {
  loadEscalatedTickets,
  loadRDKnowledge,
  renderRDEscalations,
  renderRDKnowledge,
  renderRDReleaseNotes,
  renderRDSubmitSolution,
  showResolveForm,
  submitReleaseNote,
  submitSolution,
} from './tabs/rd.js';

const tabRenderers = {
  query: renderCSQuery,
  tickets: renderCSTickets,
  desensitize: renderDesensitize,
  escalations: renderRDEscalations,
  'submit-solution': renderRDSubmitSolution,
  'release-notes': renderRDReleaseNotes,
  'rd-knowledge': renderRDKnowledge,
  'submit-knowledge': renderDocSubmit,
  'review-knowledge': renderDocReview,
  dashboard: renderDashboard,
  'all-tickets': renderAllTickets,
};

function renderLogin() {
  return `
    <div class="login-overlay">
      <div class="login-card">
        <h2>智云科技 · AI 知识库系统</h2>
        <div class="subtitle">请选择角色进入系统</div>
        <div class="role-grid">
          <div class="role-card" onclick="app.login('cs')">
            <div class="role-icon">💬</div>
            <div class="role-name">客服</div>
            <div class="role-desc">AI查询 · 工单管理</div>
          </div>
          <div class="role-card" onclick="app.login('rd')">
            <div class="role-icon">🔧</div>
            <div class="role-name">二线研发</div>
            <div class="role-desc">升级处理 · 知识沉淀</div>
          </div>
          <div class="role-card" onclick="app.login('doc')">
            <div class="role-icon">📄</div>
            <div class="role-name">文档团队</div>
            <div class="role-desc">提交知识 · 审核</div>
          </div>
          <div class="role-card" onclick="app.login('manager')">
            <div class="role-icon">📊</div>
            <div class="role-name">管理层</div>
            <div class="role-desc">仪表盘 · 汇总</div>
          </div>
        </div>
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
        <span class="role-badge ${state.role}">${roleLabels[state.role]}: ${state.username}</span>
        <select class="role-select" onchange="app.switchRole(event)">
          <option value="">切换角色</option>
          <option value="cs">客服</option>
          <option value="rd">二线研发</option>
          <option value="doc">文档团队</option>
          <option value="manager">管理层</option>
        </select>
        <button class="btn-sm" onclick="app.logout()">退出</button>
      </div>
    </div>
    <nav>${navButtons}</nav>
    ${tabPanels}`;
}

export function renderApp() {
  const root = document.getElementById('app');
  if (!root) {
    return;
  }

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
  if (!tabs.includes(name)) {
    return;
  }

  state.currentTab = name;
  document.querySelectorAll('.tab').forEach((tab) => tab.classList.remove('active'));
  document.querySelectorAll('nav button').forEach((button) => button.classList.remove('active'));

  const activeTab = document.getElementById(`tab-${name}`);
  if (activeTab) {
    activeTab.classList.add('active');
  }

  const activeButton = document.querySelector(`nav button[onclick="app.switchTab('${name}')"]`);
  if (activeButton) {
    activeButton.classList.add('active');
  }

  if (name === 'query') {
    scrollChatBottom();
  }
  if (name === 'tickets' || name === 'all-tickets') {
    void loadTickets();
  }
  if (name === 'escalations') {
    void loadEscalatedTickets();
  }
  if (name === 'dashboard') {
    void loadMetrics();
  }
  if (name === 'review-knowledge') {
    void loadPendingReviews();
  }
  if (name === 'rd-knowledge') {
    void loadRDKnowledge();
  }
}

function closeCard(button) {
  const card = button.closest('.card');
  if (card) {
    card.remove();
  }
}

window.app = {
  copyText,
  createTicket,
  createTicketFromChat,
  doEscalate,
  loadEscalatedTickets,
  loadMetrics,
  loadPendingReviews,
  loadRDKnowledge,
  loadTickets,
  login,
  logout,
  newChat,
  reviewKnowledge,
  showHandlingForm,
  showResolveForm,
  showTextPreview,
  showTicketDetail,
  submitChat,
  submitKnowledge,
  submitReleaseNote,
  submitSolution,
  switchRole,
  switchTab,
  testDesensitize,
  closeCard,
};

setRenderApp(renderApp);
setUnauthorizedHandler(handleUnauthorized);
void checkAuth();
