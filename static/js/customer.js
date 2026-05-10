import { escHtml } from './utils.js';

let ws = null;
let customerId = null;
let ticketId = null;
let statusIndicator = null;
let feedbackShown = false;

async function init() {
  statusIndicator = document.getElementById('statusIndicator');

  // Get token from server
  try {
    const resp = await fetch('/api/customer/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ customer_name: '游客' }),
    });
    const data = await resp.json();
    customerId = data.customer_id;
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

  ws.onclose = () => {
    setStatus('连接断开', 'disconnected');
    if (!feedbackShown) {
      addSystemMessage('连接已断开，请刷新页面重新连接');
    }
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

function addMessage(side, content, senderName) {
  const container = document.getElementById('chatMessages');
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
  document.getElementById('chatInputArea').style.display = 'none';
  document.getElementById('feedbackArea').style.display = 'block';
}

export async function submitFeedback(resolved) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  ws.send(JSON.stringify({
    type: 'satisfaction',
    payload: { ticket_id: ticketId, resolved, feedback_text: '' },
  }));

  document.getElementById('feedbackArea').innerHTML =
    '<div style="text-align:center;padding:20px;color:#666;">感谢您的反馈！</div>';

  setTimeout(() => { ws.close(); }, 1000);
}

export async function submitFeedbackWithText() {
  const textArea = document.getElementById('feedbackText');
  const feedbackText = textArea ? textArea.value.trim() : '';
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  ws.send(JSON.stringify({
    type: 'satisfaction',
    payload: { ticket_id: ticketId, resolved: 'feedback', feedback_text: feedbackText },
  }));

  document.getElementById('feedbackArea').innerHTML =
    '<div style="text-align:center;padding:20px;color:#666;">感谢您的反馈！</div>';

  setTimeout(() => { ws.close(); }, 1000);
}

window.sendMessage = sendMessage;
window.submitFeedback = submitFeedback;
window.submitFeedbackWithText = submitFeedbackWithText;

init();
