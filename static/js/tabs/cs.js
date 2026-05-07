import { api } from '../api.js';
import { state, resetChatState } from '../state.js';
import { escHtml, stripHtml, toast } from '../utils.js';
import { loadTickets } from '../features/tickets.js';

function renderChatBubble(message) {
  const isUser = message.role === 'user';
  return `
    <div style="display:flex;gap:10px;margin-bottom:16px;justify-content:${isUser ? 'flex-end' : 'flex-start'};">
      <div style="max-width:80%;padding:12px 18px;border-radius:18px;font-size:14px;line-height:1.6;
        ${isUser
          ? 'background:rgba(0,122,255,0.9);color:#fff;border-bottom-right-radius:6px;'
          : 'background:rgba(255,255,255,0.8);color:var(--text);border-bottom-left-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,0.04);'}">
        ${isUser ? escHtml(message.content) : message.content}
      </div>
    </div>`;
}

export function renderCSQuery() {
  const historyHtml = state.chatHistory.length === 0
    ? '<div class="empty">开始对话 — 输入客户问题，AI 将基于 D1 公开知识库回答</div>'
    : state.chatHistory.map((message) => renderChatBubble(message)).join('');

  return `
    <div class="card" style="display:flex;flex-direction:column;height:calc(100vh - 200px);min-height:500px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <h3 style="margin:0;">AI 智能对话 (Process 1)</h3>
        <div style="display:flex;gap:8px;">
          <button class="btn-sm" onclick="app.newChat()">新对话</button>
          <button class="btn-sm" onclick="app.createTicketFromChat()" ${state.chatHistory.length === 0 ? 'disabled' : ''}>转为工单</button>
        </div>
      </div>
      <div class="section-label">多轮对话模式。AI 从 D1 知识库检索，D2 仅做存在性提示不泄露内容。工单需手动创建。</div>
      <div id="chatMessages" style="flex:1;overflow-y:auto;padding:8px 0;">${historyHtml}</div>
      <div style="display:flex;gap:10px;margin-top:12px;border-top:1px solid rgba(0,0,0,0.06);padding-top:12px;">
        <textarea id="chatInput" rows="2" placeholder="输入客户问题..." style="flex:1;"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();app.submitChat();}"></textarea>
        <button class="btn btn-primary" onclick="app.submitChat()" style="align-self:flex-end;">发送</button>
      </div>
    </div>`;
}

export function newChat() {
  resetChatState();
  refreshChatUI();
}

export async function submitChat() {
  const input = document.getElementById('chatInput');
  if (!input) {
    return;
  }

  const text = input.value.trim();
  if (!text) {
    return;
  }

  input.value = '';
  input.disabled = true;

  state.chatHistory.push({ role: 'user', content: text });
  refreshChatUI();
  scrollChatBottom();

  try {
    const response = await api('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query_text: text,
        ticket_id: null,
        history: state.chatHistory.slice(0, -1),
      }),
    });

    if (!response.success) {
      state.chatHistory.push({
        role: 'assistant',
        content: `查询失败: ${escHtml(response.error || '未知错误')}`,
      });
    } else {
      const data = response.data;
      const confidenceColor = data.confidence_label === 'green'
        ? 'rgba(52,199,89,0.2)'
        : data.confidence_label === 'yellow'
          ? 'rgba(255,204,0,0.2)'
          : 'rgba(255,59,48,0.2)';
      const textColor = data.confidence_label === 'green'
        ? '#34c759'
        : data.confidence_label === 'yellow'
          ? '#ffcc00'
          : '#ff3b30';

      let metaHtml = '<div style="margin-top:6px;font-size:11px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">';
      metaHtml += `<span style="display:inline-block;padding:2px 8px;border-radius:8px;font-size:10px;font-weight:600;background:${confidenceColor};color:${textColor};">${escHtml(data.confidence_label.toUpperCase())} ${(data.confidence_score * 100).toFixed(0)}%</span>`;

      if (data.d2_match_found) {
        metaHtml += `<span style="color:#b36800;font-weight:600;font-size:10px;">⚠️ ${escHtml(data.d2_hint || '建议升级工单')}</span>`;
      }
      if (data.is_blocked) {
        metaHtml += `<span style="color:#ff3b30;font-weight:600;font-size:10px;">已拦截: ${escHtml(data.block_reason || '')}</span>`;
      }
      metaHtml += '</div>';

      let content = escHtml(data.answer_text || '(无回答)');
      if (data.citations && data.citations.length > 0) {
        content += '<div style="margin-top:8px;font-size:11px;opacity:0.7;border-top:1px solid rgba(0,0,0,0.08);padding-top:6px;">📎 引用: ';
        content += data.citations.map((citation, index) => `${index + 1}. ${escHtml(citation.doc_title)}`).join('; ');
        content += '</div>';
      }
      content += metaHtml;

      state.chatHistory.push({ role: 'assistant', content });
    }
  } catch (error) {
    state.chatHistory.push({
      role: 'assistant',
      content: `网络错误: ${escHtml(error.message)}`,
    });
  } finally {
    input.disabled = false;
    input.focus();
    refreshChatUI();
    scrollChatBottom();
  }
}

export function scrollChatBottom() {
  setTimeout(() => {
    const element = document.getElementById('chatMessages');
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }, 100);
}

function refreshChatUI() {
  const container = document.getElementById('chatMessages');
  if (!container) {
    return;
  }

  if (state.chatHistory.length === 0) {
    container.innerHTML = '<div class="empty">开始对话 — 输入客户问题，AI 将基于 D1 公开知识库回答</div>';
  } else {
    container.innerHTML = state.chatHistory.map((message) => renderChatBubble(message)).join('');
  }

  const ticketButton = document.querySelector('button[onclick="app.createTicketFromChat()"]');
  if (ticketButton) {
    ticketButton.disabled = state.chatHistory.length === 0;
  }
}

export async function createTicketFromChat() {
  if (state.chatHistory.length === 0) {
    toast('没有对话内容', 'error');
    return;
  }

  const firstMessage = state.chatHistory.find((message) => message.role === 'user');
  const title = firstMessage ? stripHtml(firstMessage.content).substring(0, 80) : '对话记录';
  const description = state.chatHistory
    .map((message) => `[${message.role === 'user' ? '客服' : 'AI'}]: ${stripHtml(message.content)}`)
    .join('\n\n');

  const response = await api('/api/tickets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, description, created_by: 'cs' }),
  });

  toast(`工单 #${response.ticket_id} 已创建，请前往工单管理查看`);
}

export function renderCSTickets() {
  return `
    <div class="card">
      <h3>创建工单</h3>
      <input type="text" id="ticketTitle" placeholder="工单标题" style="margin-bottom:8px;">
      <textarea id="ticketDesc" rows="2" placeholder="客户问题描述..."></textarea>
      <div class="btn-group"><button class="btn btn-primary" onclick="app.createTicket()">创建工单</button></div>
    </div>
    <div class="card">
      <h3>工单列表 (Process 7)</h3>
      <button class="btn btn-outline" onclick="app.loadTickets()" style="margin-bottom:12px;">刷新列表</button>
      <div id="csTicketList"><div class="empty">点击刷新加载工单</div></div>
    </div>`;
}

export async function createTicket() {
  const titleInput = document.getElementById('ticketTitle');
  const descInput = document.getElementById('ticketDesc');
  if (!titleInput || !descInput) {
    return;
  }

  const title = titleInput.value.trim();
  const description = descInput.value.trim();
  if (!title) {
    toast('请输入标题', 'error');
    return;
  }

  await api('/api/tickets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, description, created_by: 'cs' }),
  });

  toast('工单已创建');
  titleInput.value = '';
  descInput.value = '';
  await loadTickets();
}

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
  if (!input || !result) {
    return;
  }

  const text = input.value.trim();
  if (!text) {
    toast('请输入文本', 'error');
    return;
  }

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
