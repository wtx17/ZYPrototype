import { api } from '../api.js';
import { state } from '../state.js';
import { toast } from '../utils.js';
import { loadAgentSessions, renderSessionList, renderSessionWorkspace } from '../agent-workspace.js';

// ==================== Main Tab Renderer ====================

export function renderRDEscalations() {
  if (state.activeSessionId && state.activeSession) {
    return renderSessionWorkspace();
  }
  return renderSessionList();
}

export async function initRDSessions() {
  await loadAgentSessions();

  const { setHandler, connectAgentWsWithRetry, getSessionId } = await import('../websocket.js');
  const sessionId = getSessionId();
  if (sessionId) {
    connectAgentWsWithRetry(sessionId);
  }

  if (window._rdPollInterval) clearInterval(window._rdPollInterval);
  window._rdPollInterval = setInterval(() => loadAgentSessions(), 5000);

  setHandler('new_escalation', (payload) => {
    toast(`新的升级工单 #${payload.ticket_id}: ${payload.title}`);
    loadAgentSessions();
  });

  setHandler('customer_message', (payload) => {
    if (state.activeSessionId === payload.ticket_id) {
      reloadWorkspaceMessages(payload.ticket_id);
    }
    loadAgentSessions();
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
