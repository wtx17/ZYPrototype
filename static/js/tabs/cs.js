import { api } from '../api.js';
import { state } from '../state.js';
import { escHtml, toast, stripHtml } from '../utils.js';
import { loadAgentSessions, renderSessionList, renderSessionWorkspace } from '../agent-workspace.js';

// ==================== Main Tab Renderer ====================

export function renderCSQuery() {
  // If viewing a specific session, show workspace
  if (state.activeSessionId && state.activeSession) {
    return renderSessionWorkspace();
  }
  // Otherwise show session list
  return renderSessionList();
}

// ==================== Session Tab Helper ====================

export async function initCSSessions() {
  await loadAgentSessions();
  // Set up WebSocket handlers for real-time updates
  const { setHandler, connectAgentWsWithRetry, getSessionId } = await import('../websocket.js');
  const sessionId = getSessionId();
  if (sessionId) {
    connectAgentWsWithRetry(sessionId);
  }

  // Polling backup: refresh session list every 5 seconds
  if (window._csPollInterval) clearInterval(window._csPollInterval);
  window._csPollInterval = setInterval(() => loadAgentSessions(), 5000);

  setHandler('customer_message', (payload) => {
    // A new customer message arrived - refresh session list
    loadAgentSessions();
    // If we're viewing this ticket's session, update messages
    if (state.activeSessionId === payload.ticket_id) {
      reloadWorkspaceMessages(payload.ticket_id);
    }
  });

  setHandler('new_session', (payload) => {
    toast(`新会话 #${payload.ticket_id}`);
    loadAgentSessions();
  });

  setHandler('escalation_transfer', (payload) => {
    toast(`工单 #${payload.ticket_id} 已升级至研发`);
    if (state.activeSessionId === payload.ticket_id) {
      state.activeSessionId = null;
      state.activeSession = null;
      state.aiPanelVisible = false;
    }
    loadAgentSessions();
    if (window.app) window.app.switchTab('sessions');
  });

  setHandler('ticket_closed', (payload) => {
    if (state.activeSessionId === payload.ticket_id) {
      state.activeSessionId = null;
      state.activeSession = null;
      state.aiPanelVisible = false;
    }
    loadAgentSessions();
    if (window.app) window.app.switchTab('sessions');
  });

  setHandler('ai_response', (payload) => {
    state.aiQueryResult = {
      answer_text: payload.answer_text,
      confidence_score: payload.confidence_score,
      confidence_label: payload.confidence_label,
      citations: payload.citations,
      d2_match_found: payload.d2_match_found,
      d2_hint: payload.d2_hint,
      escalation_required: payload.escalation_required,
      query_text: payload.query_text,
    };
    // Auto-fill the AI answer into the input box
    const input = document.getElementById('sessionReplyInput');
    if (input && payload.answer_text) {
      input.value = payload.answer_text;
    }
    if (window.app) window.app.switchTab('sessions');
  });

  setHandler('new_escalation', (payload) => {
    toast(`新升级工单 #${payload.ticket_id}`);
  });
}

async function reloadWorkspaceMessages(ticketId) {
  try {
    const data = await api(`/api/tickets/${ticketId}/messages`);
    state.sessionMessages = data.data || [];
    const container = document.getElementById('sessionChatMessages');
    if (container) {
      const { renderMessages } = await import('../agent-chat.js');
      container.innerHTML = renderMessages(state.sessionMessages);
      container.scrollTop = container.scrollHeight;
    }
  } catch (e) {
    // ignore
  }
}

// ==================== Legacy: Desensitize Tool ====================

export function renderDesensitize() {
  return `
    <div class="card">
      <h3>敏感信息脱敏测试 (Process 6)</h3>
      <textarea id="desensitizeInput" rows="3" placeholder="输入包含敏感信息的文本，如：客户 API key: sk-abc123，密码 pwd=secret123"></textarea>
      <div class="btn-group"><button class="btn btn-outline" onclick="app.testDesensitize()">执行脱敏</button></div>
      <div id="desensitizeResult"></div>
    </div>`;
}

export async function testDesensitize() {
  const input = document.getElementById('desensitizeInput');
  const result = document.getElementById('desensitizeResult');
  if (!input || !result) return;

  const text = input.value.trim();
  if (!text) { toast('请输入文本', 'error'); return; }

  const data = await api('/api/desensitize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });

  result.innerHTML = `
    <div style="margin-top:12px;">
      <div class="section-label">原始文本</div><div class="answer-box">${escHtml(data.original)}</div>
      <div class="section-label" style="margin-top:12px;">脱敏后</div><div class="answer-box" style="background:#f0fdf4;">${escHtml(data.desensitized)}</div>
      <div style="margin-top:8px;font-size:12px;color:var(--muted);">共脱敏 ${data.changes} 处敏感信息</div>
    </div>`;
}

// ==================== Legacy: Tickets ====================

export function renderCSTickets() {
  return `
    <div class="card">
      <h3>工单列表 (Process 7)</h3>
      <p style="font-size:13px;color:var(--muted);margin-bottom:12px;">工单由系统在客户发起会话时自动创建</p>
      <button class="btn btn-outline" onclick="app.loadTickets()" style="margin-bottom:12px;">刷新列表</button>
      <div id="csTicketList"><div class="empty">点击刷新加载工单</div></div>
    </div>`;
}

export async function createTicket() {
  // Manual creation is no longer needed — tickets are auto-created by sessions.
  toast('工单由系统自动创建，无需手动操作');
}

// Deprecated legacy exports (kept for backward compat with main.js)
export function newChat() { /* no-op: use WebSocket sessions */ }
export function submitChat() { /* no-op: use WebSocket sessions */ }
export function createTicketFromChat() { /* no-op: tickets auto-created via sessions */ }
export function scrollChatBottom() {
  const el = document.getElementById('sessionChatMessages');
  if (el) el.scrollTop = el.scrollHeight;
}
