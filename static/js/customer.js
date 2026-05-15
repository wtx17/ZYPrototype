import { escHtml } from './utils.js';

let ws = null;
let customerId = null;
let ticketId = null;
let statusIndicator = null;
let feedbackShown = false;
let selectedRating = null;

async function init() {
  statusIndicator = document.getElementById('statusIndicator');

  // Reuse existing token from sessionStorage on refresh
  let token = sessionStorage.getItem('customer_token');
  let cid = sessionStorage.getItem('customer_id');

  if (token && cid) {
    customerId = cid;
    connect(token);
    return;
  }

  try {
    const resp = await fetch('/api/customer/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ customer_name: '游客' }),
    });
    const data = await resp.json();
    customerId = data.customer_id;
    sessionStorage.setItem('customer_token', data.token);
    sessionStorage.setItem('customer_id', data.customer_id);
    connect(data.token);
  } catch (e) {
    setStatus('连接失败', 'disconnected');
  }
}

function connect(token) {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${location.host}/ws/customer?token=${encodeURIComponent(token)}`;

  ws = new WebSocket(url);

  ws.onopen = () => {
    setStatus('已连接', 'connected');
    document.getElementById('sendBtn').disabled = false;
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleMessage(data);
  };

  ws.onclose = (event) => {
    if (feedbackShown) return;

    if (event.code === 4001) {
      // Server restarted — token invalid, get a new one
      sessionStorage.removeItem('customer_token');
      sessionStorage.removeItem('customer_id');
      addSystemMessage('会话已过期，正在重新连接...');
      setTimeout(() => init(), 1000);
      return;
    }

    // Network hiccup, timeout, etc. — reconnect with same token
    setStatus('重连中...', 'disconnected');
    setTimeout(() => connect(token), 2000);
  };

  ws.onerror = () => {
    setStatus('连接错误', 'disconnected');
  };
}

function handleMessage(data) {
  const { type, payload } = data;

  switch (type) {
    case 'connected':
      ticketId = payload.ticket_id;
      // Render history if reconnecting to an active ticket
      if (payload.history && payload.history.length > 0) {
        const container = document.getElementById('chatMessages');
        container.innerHTML = ''; // Clear welcome message
        payload.history.forEach(msg => {
          if (msg.sender_type === 'system') {
            addSystemMessage(msg.content);
          } else if (msg.sender_type === 'customer') {
            addMessage('customer', msg.content);
          } else {
            addMessage('agent', msg.content, msg.sender_name);
          }
        });
      }
      break;

    case 'ticket_assigned':
      ticketId = payload.ticket_id;
      break;

    case 'system_message':
      addSystemMessage(payload.content);
      break;

    case 'agent_message':
      addMessage(payload.sender_type === 'rd' ? 'rd' : 'agent', payload.content, payload.sender_name);
      break;

    case 'service_end':
      addSystemMessage(payload.content || '服务已结束');
      showFeedback();
      break;

    case 'pong':
      break;
  }
}

let _lastMsgTime = 0;

function maybeAddTimeDivider(container) {
  const now = Date.now();
  const d = new Date();
  const timeStr = String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0');
  if (now - _lastMsgTime > 120000) {
    const div = document.createElement('div');
    div.className = 'msg-time-divider';
    div.textContent = timeStr;
    container.appendChild(div);
  }
  _lastMsgTime = now;
}

function addMessage(side, content, senderName) {
  const container = document.getElementById('chatMessages');
  maybeAddTimeDivider(container);
  const senderLabel = side === 'customer' ? '' : (senderName || '');
  const row = document.createElement('div');
  row.className = `msg-row ${side}`;
  row.innerHTML = `
    ${senderLabel ? `<div class="msg-sender">${escHtml(senderLabel)}</div>` : ''}
    <div class="msg-bubble">${escHtml(content)}</div>`;
  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
}

function addSystemMessage(content) {
  const container = document.getElementById('chatMessages');
  maybeAddTimeDivider(container);
  const row = document.createElement('div');
  row.className = 'msg-row system';
  row.innerHTML = `<div class="msg-bubble">${escHtml(content)}</div>`;
  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
}

function setStatus(text, cls) {
  if (!statusIndicator) return;
  statusIndicator.textContent = text;
  statusIndicator.className = `header-status ${cls}`;
}

export async function sendMessage() {
  const input = document.getElementById('messageInput');
  const text = input.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

  addMessage('customer', text);
  input.value = '';

  ws.send(JSON.stringify({
    type: 'customer_message',
    payload: { ticket_id: ticketId, content: text },
  }));
}

function showFeedback() {
  feedbackShown = true;
  selectedRating = null;
  document.getElementById('chatInputArea').style.display = 'none';
  document.getElementById('feedbackArea').style.display = 'block'; // Inline bottom block
}

export function selectRating(rating) {
  selectedRating = rating;
  const yesBtn = document.querySelector('.feedback-btn.yes');
  const noBtn = document.querySelector('.feedback-btn.no');
  
  if (yesBtn) {
    if (rating === 'yes') yesBtn.classList.add('selected');
    else yesBtn.classList.remove('selected');
  }
  if (noBtn) {
    if (rating === 'no') noBtn.classList.add('selected');
    else noBtn.classList.remove('selected');
  }
}

export async function submitFeedback() {
  if (!selectedRating) {
    alert('请先选择"已解决"或"未解决"');
    return;
  }
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  const textArea = document.getElementById('feedbackText');
  const feedbackText = textArea ? textArea.value.trim() : '';

  ws.send(JSON.stringify({
    type: 'satisfaction',
    payload: { ticket_id: ticketId, resolved: selectedRating, feedback_text: feedbackText },
  }));

  document.getElementById('feedbackArea').innerHTML = `
    <div style="display:flex; flex-direction:column; justify-content:center; align-items:center; min-height: 200px;">
      <div style="font-size: 48px; margin-bottom:16px;">✨</div>
      <div style="font-size: 18px; font-weight:600; color:#1d1d1f;">感谢您的反馈！</div>
      <div style="color:#86868b; margin-top:8px;">本次会话已圆满结束</div>
    </div>`;

  setTimeout(() => { ws.close(); }, 1000);
}

window.sendMessage = sendMessage;

function initDividerResize() {
  const handle = document.querySelector('.chat-input-divider');
  const inputArea = document.getElementById('chatInputArea');
  if (!handle || !inputArea) return;

  let dragging = false, startY = 0, startH = 0;
  handle.addEventListener('mousedown', (e) => {
    dragging = true; startY = e.clientY; startH = inputArea.offsetHeight;
    handle.style.background = '#007aff';
    document.body.style.cursor = 'row-resize'; document.body.style.userSelect = 'none';
    e.preventDefault();
  });
  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const h = Math.min(300, Math.max(60, startH + startY - e.clientY));
    inputArea.style.height = h + 'px';
  });
  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    handle.style.background = '';
    document.body.style.cursor = ''; document.body.style.userSelect = '';
  });
}

window.selectRating = selectRating;
window.submitFeedback = submitFeedback;

// init after DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => { init(); initDividerResize(); });
} else {
  init(); initDividerResize();
}
