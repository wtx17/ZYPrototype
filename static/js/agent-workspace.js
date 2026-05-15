import { escHtml, toast } from './utils.js';
import { state } from './state.js';
import { api } from './api.js';
import { sendMessage } from './websocket.js';
import { renderMessages, renderEndServiceButton } from './agent-chat.js';

// ==================== Session List ====================

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
    const online = state.onlineCustomers[t.id];
    const onlineDot = online ? '<span class="online-dot" title="客户在线"></span>' : '<span class="online-dot offline" title="客户离线"></span>';
    const isActive = t.id === state.activeSessionId ? ' background: rgba(0,122,255,0.08);' : '';
    return `
      <div class="session-row" onclick="app.openSession(${t.id})" style="${isActive}">
        <div class="session-top">
          <span class="session-id">#${t.id}</span>
          ${onlineDot}
          <span class="status-tag ${statusCls}">${statusLabel}</span>
        </div>
        <div class="session-title">${escHtml(t.title || '无标题')}</div>
        <div class="session-meta">${escHtml(t.customer_id || '')} · ${escHtml(t.updated_at || '')}</div>
      </div>`;
  }).join('');
}

export function initWSResize() {
  const handle = document.getElementById('wsResizeHandle');
  const sidebar = document.getElementById('wsSidebar');
  if (handle && sidebar) {
    let dragging = false, startX = 0, startWidth = 0;
    handle.addEventListener('mousedown', (e) => {
      dragging = true; startX = e.clientX; startWidth = sidebar.offsetWidth;
      handle.classList.add('active');
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      const w = Math.min(500, Math.max(200, startWidth + e.clientX - startX));
      sidebar.style.width = w + 'px';
      sidebar.style.flex = '0 0 ' + w + 'px';
    });
    document.addEventListener('mouseup', () => {
      if (!dragging) return;
      dragging = false;
      handle.classList.remove('active');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    });
  }

  // Input area vertical resize
  const inputHandle = document.getElementById('wsInputDivider');
  const inputArea = document.getElementById('wsInputArea');
  if (inputHandle && inputArea) {
    let draggingV = false, startY = 0, startHeight = 0;
    inputHandle.addEventListener('mousedown', (e) => {
      draggingV = true; startY = e.clientY; startHeight = inputArea.offsetHeight;
      inputHandle.classList.add('active');
      document.body.style.cursor = 'row-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
      if (!draggingV) return;
      const h = Math.min(300, Math.max(60, startHeight + startY - e.clientY));
      inputArea.style.height = h + 'px';
    });
    document.addEventListener('mouseup', () => {
      if (!draggingV) return;
      draggingV = false;
      inputHandle.classList.remove('active');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    });
  }

  // AI sheet input vertical resize
  const aiInputHandle = document.getElementById('aiSheetInputDivider');
  const aiInputArea = document.getElementById('aiSheetInputArea');
  if (aiInputHandle && aiInputArea) {
    let draggingV = false, startY = 0, startH = 0;
    aiInputHandle.addEventListener('mousedown', (e) => {
      draggingV = true; startY = e.clientY; startH = aiInputArea.offsetHeight;
      aiInputHandle.classList.add('active');
      document.body.style.cursor = 'row-resize'; document.body.style.userSelect = 'none';
      e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
      if (!draggingV) return;
      const h = Math.min(300, Math.max(60, startH + startY - e.clientY));
      aiInputArea.style.height = h + 'px';
    });
    document.addEventListener('mouseup', () => {
      if (!draggingV) return;
      draggingV = false;
      aiInputHandle.classList.remove('active');
      document.body.style.cursor = ''; document.body.style.userSelect = '';
    });
  }

  // AI sheet width resize
  const aiSheet = document.getElementById('aiSheet');
  const aiHandle = document.getElementById('aiSheetResizeHandle');
  if (aiSheet && aiHandle) {
    let draggingW = false, startX = 0, startW = 0;
    aiHandle.addEventListener('mousedown', (e) => {
      draggingW = true; startX = e.clientX; startW = aiSheet.offsetWidth;
      aiHandle.classList.add('active');
      document.body.style.cursor = 'col-resize'; document.body.style.userSelect = 'none';
      e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
      if (!draggingW) return;
      const w = Math.min(700, Math.max(300, startW + startX - e.clientX));
      aiSheet.style.width = w + 'px';
    });
    document.addEventListener('mouseup', () => {
      if (!draggingW) return;
      draggingW = false;
      aiHandle.classList.remove('active');
      document.body.style.cursor = ''; document.body.style.userSelect = '';
    });
  }
}

export function renderAgentWorkspaceLayout() {
  const w = state.sidebarWidth || 300;

  let rightContent = '';
  if (state.activeSessionId && state.activeSession) {
    rightContent = renderSessionWorkspace();
  } else {
    rightContent = `
      <div class="card" style="flex:1; display:flex; flex-direction:column; min-width:0;">
        <div style="flex:1; display:flex; align-items:center; justify-content:center; flex-direction:column;">
           <div style="font-size:48px;color:#ccc;margin-bottom:16px;">💬</div>
           <div style="color:var(--text-secondary);">请在左侧选择一个会话</div>
        </div>
      </div>`;
  }

  return `
    <div class="ws-layout" id="wsLayout">
      <div class="card" id="wsSidebar" style="width:${w}px; flex:0 0 ${w}px; display:flex; flex-direction:column; min-width:0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <h3 style="margin:0;">${state.role === 'cs' ? '客户会话' : '升级工单'}</h3>
          <button class="btn btn-sm" onclick="app.refreshSessions()">刷新</button>
        </div>
        <div id="sessionList" style="flex:1; overflow-y:auto;">
          <div class="empty">加载中...</div>
        </div>
      </div>
      <div class="ws-resize-handle" id="wsResizeHandle"></div>
      ${rightContent}
    </div>`;
}

// ==================== Session Workspace ====================

export function renderSessionWorkspace() {
  const ticket = state.activeSession;
  if (!ticket) return '<div class="empty">请选择一个会话</div>';

  const csAccepted = ticket.assigned_cs_id;
  const rdAccepted = ticket.assigned_rd_id;
  const canSend = (state.role === 'cs' && csAccepted) || (state.role === 'rd' && rdAccepted);
  const customerOnline = state.onlineCustomers[ticket.id];
  const onlineBadge = customerOnline
    ? '<span class="online-badge">● 客户在线</span>'
    : '<span class="online-badge offline">○ 客户离线</span>';

  return `
    <div class="card" style="display:flex;flex-direction:column;flex:1;min-width:0;position:relative;">
      <div class="ws-header">
        <span style="font-weight:600;">#${ticket.id}</span>
        <span class="status-tag ${ticket.status || 'pending'}">${ticket.status || 'pending'}</span>
        ${onlineBadge}
        <span style="flex:1;"></span>
        ${state.role === 'cs' && !csAccepted ? `
          <button class="btn btn-primary btn-sm" onclick="app.handleTicket(${ticket.id})">处理工单</button>
        ` : ''}
        ${state.role === 'cs' && csAccepted && ticket.status !== 'escalated' ? `
          <button class="btn btn-sm btn-danger" onclick="app.escalateSession(${ticket.id})">升级工单</button>
        ` : ''}
        ${state.role === 'rd' && !rdAccepted ? `
          <button class="btn btn-primary btn-sm" onclick="app.acceptEscalation(${ticket.id})">接管工单</button>
        ` : ''}
        <button class="btn btn-outline btn-sm" onclick="app.askAIDirectly(${ticket.id})">询问 AI</button>
        ${canSend ? renderEndServiceButton(ticket.id) : ''}
      </div>
      <div id="sessionChatMessages" class="ws-chat-area">
        ${renderMessages(state.sessionMessages || [])}
      </div>
      <div class="ws-input-divider" id="wsInputDivider"></div>
      <div class="ws-input-area" id="wsInputArea">
        ${canSend ? `
          <textarea id="sessionReplyInput" rows="3" placeholder="输入回复..."
            onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();app.sendReply(${ticket.id});}"></textarea>
          <div class="ws-input-actions">
            <button class="btn btn-primary btn-sm" onclick="app.sendReply(${ticket.id})">发送</button>
          </div>
        ` : `
          <div style="display:flex;align-items:center;justify-content:center;height:100%;gap:12px;color:var(--text-secondary);font-size:var(--text-sm);">
            请先点击「${state.role === 'cs' ? '处理工单' : '接管工单'}」接入服务
            ${state.role === 'cs' && !csAccepted ? `
              <button class="btn btn-primary btn-sm" onclick="app.handleTicket(${ticket.id})">处理工单</button>
            ` : ''}
            ${state.role === 'rd' && !rdAccepted ? `
              <button class="btn btn-primary btn-sm" onclick="app.acceptEscalation(${ticket.id})">接管工单</button>
            ` : ''}
          </div>
        `}
      </div>
    </div>
    ${state.aiPanelVisible ? renderAISheet() : ''}
  `;
}

// ==================== AI Sheet (Overlay) ====================

function renderAISheet() {
  const msgs = state.aiMessages || [];

  return `
    <div class="ai-sheet-backdrop" onclick="app.closeAIPanel()"></div>
    <div class="ai-sheet" id="aiSheet">
      <div class="ai-sheet-resize-handle" id="aiSheetResizeHandle"></div>
      <div class="ai-sheet-header">
        <h4>AI 智能助手</h4>
        <button class="btn-sm" onclick="app.closeAIPanel()">✕</button>
      </div>
      <div class="ai-sheet-messages" id="aiDialogMessages">
        ${msgs.length === 0 && !state.aiLoading
          ? '<div class="empty" style="padding:40px;">在下方输入问题，或点击客户消息旁的「询问 AI」按钮</div>'
          : ''}
        ${msgs.map((m, i) => renderAIMessage(m, i)).join('')}
        ${state.aiLoading ? '<div class="msg-row agent"><div class="msg-bubble bubble-agent"><span class="typing-dots">AI 正在思考</span></div></div>' : ''}
      </div>
      <div class="ai-sheet-input-divider" id="aiSheetInputDivider"></div>
      <div class="ai-sheet-input" id="aiSheetInputArea">
        <textarea id="aiFollowUpInput" rows="3" placeholder="输入问题询问 AI..."
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();app.aiFollowUp();}"></textarea>
        <div class="ai-sheet-input-actions">
          <button class="btn btn-primary btn-sm" onclick="app.aiFollowUp()">发送</button>
        </div>
      </div>
    </div>`;
}

function renderAIMessage(m, index) {
  if (m.role === 'user') {
    return `
      <div class="msg-row customer">
        <div class="msg-bubble bubble-customer">${escHtml(m.content)}</div>
      </div>`;
  }

  // AI response
  const confColor = m.confidence_label === 'green' ? 'var(--green)'
    : m.confidence_label === 'yellow' ? 'var(--yellow)' : 'var(--red)';
  const confPct = ((m.confidence_score || 0) * 100).toFixed(0);

  return `
    <div class="msg-row agent">
      <div class="msg-bubble bubble-agent" style="max-width:90%;">
        <div style="white-space:pre-wrap;line-height:1.7;">${escHtml(m.content)}</div>
        ${m.citations && m.citations.length > 0 ? `
          <div class="ai-citations">
            <strong>引用来源:</strong>
            ${m.citations.map((c, i) => `
              <div class="ai-cite-item">${i + 1}. ${c.slug
                ? `<a href="/wiki/${escHtml(c.slug)}" target="_blank" class="cite-link">${escHtml(c.doc_title || '?')}</a>`
                : escHtml(c.doc_title || '?')}</div>
            `).join('')}
          </div>
        ` : ''}
        <div class="ai-confidence" style="background:${m.confidence_label === 'green' ? 'rgba(52,199,89,0.1)' : m.confidence_label === 'yellow' ? 'rgba(255,204,0,0.1)' : 'rgba(255,59,48,0.1)'};color:${confColor};">
          ● 置信度: ${confPct}% (${(m.confidence_label || 'RED').toUpperCase()})
        </div>
        ${m.d2_match_found ? '<div style="margin-top:4px;color:#b36800;font-size:12px;">⚠ 检测到内部资料，建议升级工单</div>' : ''}
      </div>
    </div>`;
}

// ==================== AI Actions ====================

export async function askAIForMessage(index) {
  if (!state.activeSessionId) return;
  const msg = state.sessionMessages[index];
  if (!msg || msg.sender_type !== 'customer') return;

  const question = msg.content;
  state.aiPanelVisible = true;
  state.aiLoading = true;
  state.aiQueryResult = null;
  if (!state.aiMessages) state.aiMessages = [];

  // Add user question to AI dialog
  state.aiMessages.push({ role: 'user', content: question });
  window.app.renderApp();
  scrollAIDialog();

  // Call REST API for AI query
  try {
    const resp = await api('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query_text: question,
        ticket_id: state.activeSessionId,
        history: state.aiMessages.filter(m => m.role !== 'user' || m !== state.aiMessages[state.aiMessages.length - 1]).map(m => ({ role: m.role, content: m.content })),
      }),
    });

    if (resp.success && resp.data) {
      const d = resp.data;
      state.aiMessages.push({
        role: 'assistant',
        content: d.answer_text || '(无回答)',
        confidence_score: d.confidence_score,
        confidence_label: d.confidence_label,
        citations: d.citations || [],
        d2_match_found: d.d2_match_found,
        escalation_required: d.escalation_required,
        d2_hint: d.d2_hint,
      });
      state.aiQueryResult = {
        answer_text: d.answer_text,
        confidence_score: d.confidence_score,
        confidence_label: d.confidence_label,
        citations: d.citations || [],
        d2_match_found: d.d2_match_found,
        d2_hint: d.d2_hint,
        escalation_required: d.escalation_required,
        query_text: question,
      };
    } else {
      state.aiMessages.push({
        role: 'assistant',
        content: 'AI 查询失败: ' + (resp.error || '未知错误'),
        confidence_score: 0, confidence_label: 'red', citations: [],
      });
    }
  } catch (e) {
    state.aiMessages.push({
      role: 'assistant',
      content: '网络错误: ' + e.message,
      confidence_score: 0, confidence_label: 'red', citations: [],
    });
  }

  state.aiLoading = false;
  window.app.renderApp();
  scrollAIDialog();
  checkAutoEscalate();
}

export async function aiFollowUp() {
  const input = document.getElementById('aiFollowUpInput');
  if (!input || !input.value.trim()) return;

  const question = input.value.trim();
  input.value = '';
  state.aiLoading = true;
  state.aiMessages.push({ role: 'user', content: question });
  window.app.renderApp();
  scrollAIDialog();

  try {
    const resp = await api('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query_text: question,
        ticket_id: state.activeSessionId,
        history: state.aiMessages.slice(0, -1).filter(m => m.confidence_score !== undefined || m.role === 'user').map(m => ({ role: m.role, content: m.content })),
      }),
    });

    if (resp.success && resp.data) {
      const d = resp.data;
      state.aiMessages.push({
        role: 'assistant',
        content: d.answer_text || '(无回答)',
        confidence_score: d.confidence_score,
        confidence_label: d.confidence_label,
        citations: d.citations || [],
        d2_match_found: d.d2_match_found,
        escalation_required: d.escalation_required,
        d2_hint: d.d2_hint,
      });
    }
  } catch (e) {
    state.aiMessages.push({
      role: 'assistant',
      content: '网络错误: ' + e.message,
      confidence_score: 0, confidence_label: 'red', citations: [],
    });
  }

  state.aiLoading = false;
  window.app.renderApp();
  scrollAIDialog();
  checkAutoEscalate();
}

export function closeAIPanel() {
  state.aiPanelVisible = false;
  state.aiLoading = false;
  window.app.renderApp();
}

function checkAutoEscalate() {
  if (state.role !== 'cs' || !state.activeSessionId) return;
  const lastMsg = state.aiMessages[state.aiMessages.length - 1];
  if (!lastMsg || lastMsg.role !== 'assistant') return;
  if (!lastMsg.escalation_required) return;

  let reason = 'AI 建议升级工单';
  if (lastMsg.d2_hint) reason = lastMsg.d2_hint;
  else if (lastMsg.confidence_label === 'red') reason = 'AI 置信度过低 (RED)';
  else if (lastMsg.d2_match_found) reason = '检测到内部资料匹配，建议升级';

  if (confirm(`AI 建议升级此工单\n\n原因: ${reason}\n\n是否升级至二线研发？`)) {
    escalateSession(state.activeSessionId);
  }
}

function scrollAIDialog() {
  setTimeout(() => {
    const el = document.getElementById('aiDialogMessages');
    if (el) el.scrollTop = el.scrollHeight;
  }, 100);
}

export async function askAIDirectly(ticketId) {
  state.aiPanelVisible = true;
  state.aiLoading = false;
  if (!state.aiMessages) state.aiMessages = [];
  window.app.renderApp();
}

// ==================== Session Actions ====================

export async function openSession(ticketId) {
  state.activeSessionId = ticketId;
  const data = await api(`/api/sessions/${ticketId}`);
  state.activeSession = data.data.ticket;
  state.sessionMessages = data.data.messages || [];
  if (typeof data.data.customer_online === 'boolean') {
    state.onlineCustomers[ticketId] = data.data.customer_online;
  }
  state.aiPanelVisible = false;
  state.aiQueryResult = null;
  state.aiMessages = [];
  state.aiLoading = false;

  // Restore AI dialog history
  try {
    const aiLogsResp = await api(`/api/tickets/${ticketId}/ai-logs`);
    if (aiLogsResp.success && aiLogsResp.data) {
      for (const log of aiLogsResp.data) {
        state.aiMessages.push({ role: 'user', content: log.query_text });
        state.aiMessages.push({
          role: 'assistant',
          content: log.answer_text,
          confidence_score: log.confidence_score,
          confidence_label: log.confidence_label,
          citations: log.citations || [],
          d2_match_found: log.d2_match_found,
        });
      }
    }
  } catch (e) {
    // AI logs are best-effort; don't block session open on failure
  }

  window.app.renderApp();
}

export async function sendReply(ticketId) {
  const input = document.getElementById('sessionReplyInput');
  if (!input || !input.value.trim()) return;

  const content = input.value.trim();
  input.value = '';

  await api(`/api/tickets/${ticketId}/send-message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });

  setTimeout(() => reloadMessages(ticketId), 300);
}

export async function handleTicket(ticketId) {
  await api(`/api/tickets/${ticketId}/handle`, { method: 'POST' });

  // Mark customer as online (they sent the message that created this ticket)
  state.onlineCustomers[ticketId] = true;

  const data = await api(`/api/sessions/${ticketId}`);
  state.activeSession = data.data.ticket;
  state.sessionMessages = data.data.messages || [];
  window.app.renderApp();
}

export async function escalateSession(ticketId) {
  if (!confirm('确认将此工单升级至二线研发？')) return;

  sendMessage({ type: 'escalate', payload: { ticket_id: ticketId, reason: '客服主动升级' } });

  state.activeSessionId = null;
  state.activeSession = null;
  state.aiPanelVisible = false;
  state.aiMessages = [];
  window.app.renderApp();
}

export async function acceptEscalation(ticketId) {
  await api(`/api/tickets/${ticketId}/accept`, { method: 'POST' });

  const data = await api(`/api/sessions/${ticketId}`);
  state.activeSession = data.data.ticket;
  state.sessionMessages = data.data.messages || [];
  state.aiMessages = [];
  window.app.renderApp();
}

export async function endService(ticketId) {
  if (!confirm('确认结束服务？')) return;

  await api(`/api/tickets/${ticketId}/end-service`, { method: 'POST' });

  state.activeSessionId = null;
  state.activeSession = null;
  state.sessionMessages = [];
  state.aiPanelVisible = false;
  state.aiQueryResult = null;
  state.aiMessages = [];
  state.aiLoading = false;
  window.app.renderApp();
}

export function backToSessionList() {
  state.activeSessionId = null;
  state.activeSession = null;
  state.sessionMessages = [];
  state.aiPanelVisible = false;
  state.aiQueryResult = null;
  state.aiMessages = [];
  state.aiLoading = false;
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
