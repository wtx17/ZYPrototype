import { api } from '../api.js';
import { state } from '../state.js';
import { toast } from '../utils.js';
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
      state.aiMessages = [];
    }
    loadAgentSessions();
    if (window.app) window.app.renderApp();
  });

  setHandler('ticket_closed', (payload) => {
    if (state.activeSessionId === payload.ticket_id) {
      state.activeSessionId = null;
      state.activeSession = null;
      state.aiPanelVisible = false;
    }
    loadAgentSessions();
    if (window.app) window.app.renderApp();
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
