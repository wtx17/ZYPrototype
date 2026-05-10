import { escHtml, formatDate } from './utils.js';
import { state } from './state.js';

export function renderAgentChatBubble(msg) {
  const side = msg.sender_type === 'customer' ? 'customer'
    : msg.sender_type === 'system' ? 'system'
    : 'agent';

  if (side === 'system') {
    return `
      <div class="msg-system">
        <span class="msg-system-text">${escHtml(msg.content)}</span>
      </div>`;
  }

  const isCustomer = side === 'customer';
  const senderLabel = msg.sender_name || (isCustomer ? '客户' : '坐席');

  return `
    <div class="msg-row ${isCustomer ? 'msg-customer' : 'msg-agent'}">
      <div class="msg-meta">
        <span class="msg-sender">${escHtml(senderLabel)}</span>
        <span class="msg-time">${formatTime(msg.created_at)}</span>
      </div>
      <div class="msg-bubble ${isCustomer ? 'bubble-customer' : 'bubble-agent'}">
        ${escHtml(msg.content)}
      </div>
    </div>`;
}

export function renderMessages(messages) {
  if (!messages || !messages.length) {
    return '<div class="empty">暂无消息</div>';
  }
  return messages.map(renderAgentChatBubble).join('');
}

export function renderActionBar(ticketId, role) {
  const canEscalate = role === 'cs' && ticketId;
  const canAccept = role === 'rd' && ticketId;

  return `
    <div class="action-bar">
      ${canEscalate ? `
        <button class="btn btn-outline btn-sm" onclick="app.askAIAssistant(${ticketId})">
          询问 AI 助手
        </button>
        <button class="btn btn-outline btn-sm" style="color:var(--red);" onclick="app.escalateSession(${ticketId})">
          升级工单
        </button>
      ` : ''}
      ${canAccept ? `
        <button class="btn btn-primary btn-sm" onclick="app.acceptEscalation(${ticketId})">
          接管工单
        </button>
      ` : ''}
      ${role === 'rd' ? `
        <button class="btn btn-outline btn-sm" onclick="app.askAIAssistant(${ticketId})">
          询问 AI 助手
        </button>
      ` : ''}
    </div>`;
}

export function renderEndServiceButton(ticketId) {
  return `
    <button class="btn btn-danger btn-sm" onclick="app.endService(${ticketId})" style="margin-left:8px;">
      结束服务
    </button>`;
}

function formatTime(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return '';
  }
}
