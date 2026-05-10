import { escHtml } from './utils.js';
import { state } from './state.js';
import { api } from './api.js';
import { sendMessage } from './websocket.js';
import { renderMessages, renderActionBar, renderEndServiceButton } from './agent-chat.js';

// ==================== Session List Views ====================

export async function loadAgentSessions() {
  const endpoint = state.role === 'cs' ? '/api/cs/sessions' : '/api/rd/sessions';
  const data = await api(endpoint);
  const tickets = data.data || [];

  const listEl = document.getElementById('sessionList');
  if (!listEl) return;

  if (!tickets.length) {
    listEl.innerHTML = '<div class="empty">暂无活跃会话</div>';
    return;
  }

  listEl.innerHTML = tickets.map(t => {
    const statusLabel = t.status === 'escalated' ? '已升级' : t.status === 'pending' ? '待处理' : '处理中';
    const statusCls = t.status === 'escalated' ? 'escalated' : t.status === 'pending' ? 'pending' : 'ai_processing';
    return `
      <div class="session-row" onclick="app.openSession(${t.id})">
        <div class="session-top">
          <span class="session-id">#${t.id}</span>
          <span class="status-tag ${statusCls}">${statusLabel}</span>
        </div>
        <div class="session-title">${escHtml(t.title || '无标题')}</div>
        <div class="session-meta">${escHtml(t.customer_id || '')} · ${escHtml(t.updated_at || '')}</div>
      </div>`;
  }).join('');
}

export function renderSessionList() {
  return `
    <div class="card" style="height:100%;display:flex;flex-direction:column;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="margin:0;">${state.role === 'cs' ? '客户会话' : '升级工单'}</h3>
        <button class="btn btn-outline btn-sm" onclick="app.refreshSessions()">刷新</button>
      </div>
      <div id="sessionList" style="flex:1;overflow-y:auto;">
        <div class="empty">加载中...</div>
      </div>
    </div>`;
}

// ==================== Session Workspace ====================

export function renderSessionWorkspace() {
  const ticket = state.activeSession;
  if (!ticket) return '<div class="empty">请选择一个会话</div>';

  const leftWidth = state.aiPanelVisible ? '30%' : '100%';

  return `
    <div style="display:flex;height:calc(100vh - 200px);gap:16px;">
      <!-- Left: Chat Panel -->
      <div style="flex:0 0 ${leftWidth};display:flex;flex-direction:column;transition:flex 0.3s;min-width:0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <button class="btn-sm" onclick="app.backToSessionList()">← 返回列表</button>
          <span class="status-tag ${ticket.status || 'pending'}">${ticket.status || 'pending'}</span>
          <div style="display:flex;gap:8px;">
            ${state.role === 'cs' && ticket.status !== 'escalated' ? `
              <button class="btn btn-outline btn-sm" style="color:var(--red);" onclick="app.escalateSession(${ticket.id})">升级工单</button>
            ` : ''}
            ${state.role === 'rd' && ticket.status === 'escalated' ? `
              <button class="btn btn-primary btn-sm" onclick="app.acceptEscalation(${ticket.id})">接管工单</button>
            ` : ''}
            ${renderEndServiceButton(ticket.id)}
          </div>
        </div>
        <div id="sessionChatMessages" style="flex:1;overflow-y:auto;padding:8px;background:rgba(255,255,255,0.3);border-radius:12px;margin-bottom:8px;">
          ${renderMessages(state.sessionMessages || [])}
        </div>
        <div style="display:flex;gap:8px;align-items:flex-end;">
          <textarea id="sessionReplyInput" rows="2" placeholder="输入回复..."
            style="flex:1;"
            onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();app.sendReply(${ticket.id});}"></textarea>
          <button class="btn btn-primary btn-sm" onclick="app.sendReply(${ticket.id})" style="align-self:flex-end;">发送</button>
        </div>
        <div style="margin-top:8px;display:flex;gap:8px;">
          <button class="btn btn-outline btn-sm" onclick="app.askAIAssistant(${ticket.id})">
            询问 AI 助手
          </button>
          ${state.role === 'cs' && ticket.status !== 'escalated' ? `
            <button class="btn btn-outline btn-sm" style="color:var(--red);" onclick="app.escalateSession(${ticket.id})">
              升级工单
            </button>
          ` : ''}
        </div>
      </div>
      <!-- Right: AI Panel -->
      ${state.aiPanelVisible ? renderAIPanel() : ''}
    </div>`;
}

// ==================== AI Panel ====================

function renderAIPanel() {
  const result = state.aiQueryResult;

  if (!result) {
    return `
      <div class="ai-panel">
        <div class="ai-panel-header">
          <h4>AI 智能助手</h4>
          <button class="btn-sm" onclick="app.closeAIPanel()">✕</button>
        </div>
        <div class="empty" style="flex:1;display:flex;align-items:center;justify-content:center;">
          正在查询 AI ...
        </div>
      </div>`;
  }

  const confColor = result.confidence_label === 'green' ? 'var(--green)'
    : result.confidence_label === 'yellow' ? 'var(--yellow)' : 'var(--red)';
  const confBg = result.confidence_label === 'green' ? 'rgba(52,199,89,0.1)'
    : result.confidence_label === 'yellow' ? 'rgba(255,204,0,0.1)' : 'rgba(255,59,48,0.1)';
  const confPct = (result.confidence_score * 100).toFixed(0);

  return `
    <div class="ai-panel">
      <div class="ai-panel-header">
        <h4>AI 智能助手</h4>
        <button class="btn-sm" onclick="app.closeAIPanel()">✕</button>
      </div>
      <div style="font-size:12px;color:var(--muted);margin-bottom:8px;">
        客户问题: ${escHtml(result.query_text || state.activeSession?.description || '')}
      </div>
      <div class="ai-answer-box">${escHtml(result.answer_text || '(无回答)')}</div>
      ${renderCitations(result.citations || [])}
      <div style="margin-top:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
        <span class="confidence ${result.confidence_label || 'red'}">
          置信度: ${confPct}% (${(result.confidence_label || 'RED').toUpperCase()})
        </span>
        ${result.d2_match_found ? '<span style="color:#b36800;font-size:12px;">⚠ 检测到内部资料</span>' : ''}
        ${result.escalation_required ? '<span style="color:var(--red);font-size:12px;">建议升级</span>' : ''}
      </div>
      <div style="margin-top:12px;display:flex;gap:8px;">
        <button class="btn btn-outline btn-sm" onclick="app.retryAI()">重试</button>
        <button class="btn btn-outline btn-sm" style="color:var(--red);" onclick="app.escalateFromAI()">升级</button>
      </div>
    </div>`;
}

function renderCitations(citations) {
  if (!citations || !citations.length) return '';
  return `
    <div style="margin-top:8px;font-size:12px;border-top:1px solid rgba(0,0,0,0.08);padding-top:8px;">
      <strong>引用来源:</strong>
      ${citations.map((c, i) => `
        <div class="citation">
          <span class="title">${i + 1}. ${escHtml(c.doc_title || '')}</span>
          ${c.section ? `<span class="meta">${escHtml(c.section)}</span>` : ''}
          ${c.snippet ? `<div style="font-size:11px;color:var(--muted);margin-top:2px;">${escHtml(c.snippet).substring(0, 120)}</div>` : ''}
        </div>
      `).join('')}
    </div>`;
}

// ==================== Session Actions ====================

export async function openSession(ticketId) {
  state.activeSessionId = ticketId;
  const data = await api(`/api/sessions/${ticketId}`);
  state.activeSession = data.data.ticket;
  state.sessionMessages = data.data.messages || [];
  state.aiPanelVisible = false;
  state.aiQueryResult = null;
  window.app.renderApp();
}

export async function sendReply(ticketId) {
  const input = document.getElementById('sessionReplyInput');
  if (!input || !input.value.trim()) return;

  const content = input.value.trim();
  input.value = '';

  // Use REST (reliable, auth-gated, handles DB insert + WS forward to customer)
  await api(`/api/tickets/${ticketId}/send-message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });

  setTimeout(() => reloadMessages(ticketId), 300);
}

export async function askAIAssistant(ticketId) {
  state.aiPanelVisible = true;
  state.aiQueryResult = null;
  window.app.renderApp();

  sendMessage({
    type: 'ai_request',
    payload: { ticket_id: ticketId },
  });
}

export async function escalateSession(ticketId) {
  if (!confirm('确认将此工单升级至二线研发？')) return;

  sendMessage({
    type: 'escalate',
    payload: { ticket_id: ticketId, reason: '客服主动升级' },
  });

  state.activeSessionId = null;
  state.activeSession = null;
  state.aiPanelVisible = false;
  window.app.renderApp();
}

export async function acceptEscalation(ticketId) {
  sendMessage({
    type: 'accept_escalation',
    payload: { ticket_id: ticketId },
  });

  const data = await api(`/api/sessions/${ticketId}`);
  state.activeSession = data.data.ticket;
  state.sessionMessages = data.data.messages || [];
  window.app.renderApp();
}

export function escalateFromAI() {
  if (state.activeSessionId) {
    escalateSession(state.activeSessionId);
  }
}

export async function endService(ticketId) {
  if (!confirm('确认结束服务？')) return;

  sendMessage({
    type: 'service_end',
    payload: { ticket_id: ticketId },
  });

  await api(`/api/tickets/${ticketId}/end-service`, { method: 'POST' }).catch(() => {});

  state.activeSessionId = null;
  state.activeSession = null;
  state.sessionMessages = [];
  state.aiPanelVisible = false;
  state.aiQueryResult = null;
  window.app.renderApp();
}

export async function retryAI() {
  if (state.activeSessionId) {
    askAIAssistant(state.activeSessionId);
  }
}

export function closeAIPanel() {
  state.aiPanelVisible = false;
  state.aiQueryResult = null;
  window.app.renderApp();
}

export function backToSessionList() {
  state.activeSessionId = null;
  state.activeSession = null;
  state.sessionMessages = [];
  state.aiPanelVisible = false;
  state.aiQueryResult = null;
  window.app.renderApp();
}

async function reloadMessages(ticketId) {
  const data = await api(`/api/tickets/${ticketId}/messages`);
  state.sessionMessages = (data.data || []).length ? data.data : state.sessionMessages;
  const container = document.getElementById('sessionChatMessages');
  if (container) {
    container.innerHTML = renderMessages(state.sessionMessages);
    container.scrollTop = container.scrollHeight;
  }
}

export function refreshSessions() {
  loadAgentSessions();
}
