import { escHtml } from './utils.js';

let _token = null;
let _customerId = null;
let _currentView = 'list';    // 'list' | 'create' | 'detail'
let _activeTicketId = null;
let _selectedRating = null;
let _pollTimer = null;
let _lastMsgId = 0;
let _ticket = null;       // current ticket info
let _replyOpen = false;   // inline reply visibility

// ==================== Init ====================

async function init() {
  _token = sessionStorage.getItem('customer_token');
  _customerId = sessionStorage.getItem('customer_id');

  if (!_token || !_customerId) {
    try {
      const resp = await fetch('/api/customer/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customer_name: '游客' }),
      });
      const data = await resp.json();
      _token = data.token;
      _customerId = data.customer_id;
      sessionStorage.setItem('customer_token', _token);
      sessionStorage.setItem('customer_id', _customerId);
    } catch (e) {
      document.getElementById('ticketListContainer').innerHTML =
        '<div class="cus-empty">连接失败，请刷新页面重试</div>';
      return;
    }
  }

  showView('list');
  await loadTicketList();
}

// ==================== View Switching ====================

function showView(view) {
  _currentView = view;
  stopPolling();

  document.getElementById('cusTicketList').style.display = view === 'list' ? '' : 'none';
  document.getElementById('cusTicketCreate').style.display = view === 'create' ? '' : 'none';
  document.getElementById('cusTicketDetail').style.display = view === 'detail' ? '' : 'none';

  const backBtn = document.getElementById('cusBackBtn');
  const titleEl = document.getElementById('cusHeaderTitle');
  const newBtn = document.getElementById('cusNewBtn');

  if (view === 'list') {
    backBtn.style.display = 'none';
    titleEl.textContent = '我的工单';
    newBtn.style.display = '';
  } else if (view === 'create') {
    backBtn.style.display = '';
    titleEl.textContent = '新建工单';
    newBtn.style.display = 'none';
  } else if (view === 'detail') {
    backBtn.style.display = '';
    titleEl.textContent = '工单详情';
    newBtn.style.display = 'none';
  }
}

function back() {
  if (_currentView === 'detail' || _currentView === 'create') {
    showView('list');
    _activeTicketId = null;
    loadTicketList();
  }
}

// ==================== Ticket List ====================

async function loadTicketList() {
  const container = document.getElementById('ticketListContainer');
  if (!container) return;

  try {
    const resp = await fetch(`/api/customer/tickets?token=${encodeURIComponent(_token)}`);
    if (resp.status === 401) {
      sessionStorage.removeItem('customer_token');
      sessionStorage.removeItem('customer_id');
      _token = null;
      _customerId = null;
      init();
      return;
    }
    const data = await resp.json();
    const tickets = data.data || [];

    if (!tickets.length) {
      container.innerHTML = `
        <div class="cus-empty">
          <div style="font-size:40px;margin-bottom:16px;">📋</div>
          <div>暂无工单</div>
          <div style="margin-top:8px;font-size:13px;">点击右上角「新建工单」提交问题，我们会在 4 小时内回复</div>
        </div>`;
      return;
    }

    container.innerHTML = tickets.map(t => renderTicketCard(t)).join('');
  } catch (e) {
    container.innerHTML = '<div class="cus-empty">加载失败，请刷新重试</div>';
  }
}

function renderTicketCard(t) {
  const statusLabel = statusText(t);
  const statusCls = statusClass(t);
  const created = formatTime(t.created_at);
  const updated = formatTime(t.updated_at);
  const isNew = t.updated_at !== t.created_at ? false : true;

  return `
    <div class="cus-ticket-card" onclick="CustomerView.showDetail(${t.id})">
      <div class="cus-ticket-left">
        <div class="cus-ticket-title">#${t.id} ${escHtml(t.title)}</div>
        <div class="cus-ticket-meta">
          <span>创建: ${created}</span>
          ${!isNew ? `<span>更新: ${updated}</span>` : ''}
        </div>
      </div>
      <span class="cus-ticket-status ${statusCls}">${statusLabel}</span>
    </div>`;
}

function statusText(t) {
  if (t.service_ended || t.status === 'closed') return '已关闭';
  if (t.status === 'escalated') return t.assigned_rd_id ? '研发处理中' : '已升级';
  if (t.status === 'handling') return '处理中';
  return '待处理';
}

function statusClass(t) {
  if (t.service_ended || t.status === 'closed') return 'closed';
  if (t.status === 'escalated') return 'escalated';
  if (t.status === 'handling') return 'handling';
  return 'pending';
}

// ==================== Create Ticket ====================

function showCreate() {
  document.getElementById('ticketTitle').value = '';
  document.getElementById('ticketDescription').value = '';
  document.getElementById('cusFormError').style.display = 'none';
  document.getElementById('cusSubmitBtn').disabled = false;
  showView('create');
}

async function submitTicket() {
  const titleEl = document.getElementById('ticketTitle');
  const descEl = document.getElementById('ticketDescription');
  const errorEl = document.getElementById('cusFormError');
  const submitBtn = document.getElementById('cusSubmitBtn');

  const title = titleEl.value.trim();
  const description = descEl.value.trim();

  if (!title) { showError(errorEl, '请输入标题'); return; }
  if (!description) { showError(errorEl, '请输入问题描述'); return; }

  errorEl.style.display = 'none';
  submitBtn.disabled = true;
  submitBtn.textContent = '提交中...';

  try {
    const resp = await fetch(`/api/customer/tickets?token=${encodeURIComponent(_token)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description }),
    });

    const data = await resp.json();
    if (!resp.ok) {
      showError(errorEl, data.detail || '提交失败');
      submitBtn.disabled = false;
      submitBtn.textContent = '提交工单';
      return;
    }

    // Show success briefly then go to list
    document.getElementById('cusTicketCreate').innerHTML = `
      <div class="cus-form-success">
        <div style="font-size:48px;margin-bottom:16px;">✅</div>
        <div style="font-weight:600;font-size:16px;color:var(--text-primary);margin-bottom:8px;">工单已提交</div>
        <div>工单号 #${data.ticket_id}</div>
        <div style="margin-top:4px;">我们会在 4 小时内回复您</div>
      </div>`;

    setTimeout(() => {
      showView('list');
      loadTicketList();
    }, 2000);

  } catch (e) {
    showError(errorEl, '网络错误，请重试');
    submitBtn.disabled = false;
    submitBtn.textContent = '提交工单';
  }
}

function showError(el, msg) {
  el.textContent = msg;
  el.style.display = '';
}

// ==================== Ticket Detail ====================

async function showDetail(ticketId) {
  _activeTicketId = ticketId;
  _lastMsgId = 0;
  _replyOpen = false;
  showView('detail');

  await loadMessages();
  startPolling();
}

async function loadMessages() {
  if (!_activeTicketId) return;

  try {
    const isInitial = _lastMsgId === 0;
    const params = new URLSearchParams({ limit: '100' });
    if (!isInitial) {
      params.set('after', String(_lastMsgId));
    }
    const resp = await fetch(
      `/api/tickets/${_activeTicketId}/messages?${params}`
    );
    if (!resp.ok) return;
    const data = await resp.json();
    const messages = data.data || [];

    if (!isInitial && messages.length === 0) {
      // Poll: no new messages, only update ticket status (reply/satisfaction may have changed)
      await refreshTicketState();
      return;
    }

    if (messages.length > 0) {
      _lastMsgId = data.last_id || messages[messages.length - 1].id;
    }

    // Fetch ticket info and refresh header + reply/satisfaction UI
    await refreshTicketState();

    // For poll with new messages, we need to re-fetch all messages to rebuild stages.
    // buildStages groups by system events, so a single new message can change structure.
    if (!isInitial) {
      const fullResp = await fetch(
        `/api/tickets/${_activeTicketId}/messages?limit=100`
      );
      if (fullResp.ok) {
        const fullData = await fullResp.json();
        const allMessages = fullData.data || [];
        _lastMsgId = fullData.last_id || _lastMsgId;
        renderTimelineFrom(allMessages);
        return;
      }
    }

    renderTimelineFrom(messages);

  } catch (e) {
    document.getElementById('cusDetailHeader').innerHTML =
      '<div class="cus-detail-title">加载失败</div>';
    document.getElementById('cusMessages').innerHTML =
      '<div class="cus-empty">加载失败</div>';
  }
}

async function refreshTicketState() {
  try {
    const tResp = await fetch(`/api/customer/tickets?token=${encodeURIComponent(_token)}`);
    if (!tResp.ok) return;
    const tData = await tResp.json();
    _ticket = (tData.data || []).find(t => t.id === _activeTicketId) || null;
    renderDetailHeader(_ticket);
    updateSatisfactionUI();
  } catch (e) { /* ignore */ }
}

function renderTimelineFrom(messages) {
  const stages = buildStages(messages);
  document.getElementById('cusMessages').innerHTML = renderTimeline(stages);
}

// ==================== Stage Builder ====================

function buildStages(messages) {
  if (!messages.length) return [];

  const stages = [];
  let currentStage = null;

  for (const m of messages) {
    if (m.sender_type === 'system') {
      const stage = systemToStage(m);
      if (stage) {
        stages.push(stage);
        currentStage = stage;
      }
    } else {
      if (!currentStage) {
        currentStage = {
          type: 'created',
          title: '工单已提交',
          subtitle: '待客服处理',
          time: m.created_at,
          messages: [],
        };
        stages.push(currentStage);
      }
      currentStage.messages.push(m);
    }
  }

  // Reverse: newest stage at top
  stages.reverse();
  stages.forEach(s => s.messages.reverse());

  if (stages.length > 0) {
    stages[0].isLatest = true;
    stages[stages.length - 1].isFirst = true;
  }

  return stages;
}

function systemToStage(m) {
  const content = m.content || '';

  let match = content.match(/客服\s*(.+)\s*为您服务/);
  if (match) {
    return {
      type: 'cs_assigned',
      title: '客服已接入',
      subtitle: '处理中',
      time: m.created_at,
      senderName: match[1],
      messages: [],
    };
  }

  match = content.match(/工程师\s*(.+)\s*为您服务/);
  if (match) {
    return {
      type: 'rd_assigned',
      title: '工程师已接入',
      subtitle: '研发处理中',
      time: m.created_at,
      senderName: match[1],
      messages: [],
    };
  }

  if (content.includes('升级工单')) {
    return {
      type: 'escalated',
      title: '工单已升级',
      subtitle: '等待工程师接入',
      time: m.created_at,
      messages: [],
    };
  }

  if (content.includes('服务已结束')) {
    return {
      type: 'resolved',
      title: '服务已结束',
      subtitle: '',
      time: m.created_at,
      messages: [],
    };
  }

  if (content.includes('客户已结束工单')) {
    return {
      type: 'customer_closed',
      title: '工单已结束',
      subtitle: '由您关闭',
      time: m.created_at,
      messages: [],
    };
  }

  match = content.match(/客户已评价：(.+)/);
  if (match) {
    return {
      type: 'feedback',
      title: '已反馈',
      subtitle: match[1],
      time: m.created_at,
      messages: [],
    };
  }

  return {
    type: 'system',
    title: content,
    subtitle: '',
    time: m.created_at,
    messages: [],
  };
}

// ==================== Timeline Renderer ====================

function renderTimeline(stages) {
  if (!stages.length) {
    return '<div class="cus-empty">暂无消息</div>';
  }

  const ticketOpen = _ticket && !_ticket.service_ended && _ticket.status !== 'closed';

  let html = '<div class="cus-timeline">';

  stages.forEach((stage, i) => {
    const isLast = i === stages.length - 1;
    const dotClass = stage.isLatest ? 'cus-stage-dot active'
      : isLast ? 'cus-stage-dot end'
      : 'cus-stage-dot';
    const isFirst = i === 0;

    html += `<div class="cus-stage">
        <div class="cus-stage-connector">
          <div class="${dotClass}"></div>
          ${!isLast ? '<div class="cus-stage-line"></div>' : ''}
        </div>
        <div class="cus-stage-body">
          <div class="cus-stage-header">
            <span class="cus-stage-title">${escHtml(stage.title)}</span>
            ${stage.senderName ? `<span class="cus-stage-subtitle">· ${escHtml(stage.senderName)}</span>` : ''}
            ${stage.subtitle ? `<span class="cus-stage-subtitle">${escHtml(stage.subtitle)}</span>` : ''}
            <span class="cus-stage-time">${formatTime(stage.time)}</span>
          </div>
          ${stage.messages.length > 0 ? `
            <div class="cus-sub-msgs">
              ${stage.messages.map(m => renderSubMessage(m)).join('')}
            </div>` : ''}
          ${isFirst && _replyOpen ? `
            <div class="cus-inline-reply">
              <textarea id="cusInlineReplyInput" class="cus-inline-reply-input" rows="2" placeholder="输入回复..."
                onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();CustomerView.sendInlineReply();}"></textarea>
              <button class="cus-inline-reply-btn" onclick="CustomerView.sendInlineReply()">发送</button>
            </div>` : ''}
          ${isFirst && ticketOpen ? `
            <div class="cus-stage-actions">
              ${!_replyOpen ? '<button class="cus-action-btn" onclick="CustomerView.toggleReply()">补充信息</button>' : ''}
              <button class="cus-action-btn secondary" onclick="CustomerView.closeTicket()">结束工单</button>
            </div>` : ''}
        </div>
      </div>`;
  });

  html += '</div>';
  return html;
}

function renderSubMessage(m) {
  const isCustomer = m.sender_type === 'customer';
  const senderLabel = isCustomer ? '我'
    : m.sender_type === 'cs' ? '客服'
    : m.sender_type === 'rd' ? '工程师'
    : m.sender_name || '';

  return `<div class="cus-sub-msg ${isCustomer ? 'customer' : ''}">
      <div class="cus-sub-msg-sender">${escHtml(senderLabel)}${!isCustomer && m.sender_name ? ' · ' + escHtml(m.sender_name) : ''}</div>
      <div class="cus-sub-msg-content">${escHtml(m.content)}</div>
      <div class="cus-sub-msg-time">${formatTime(m.created_at)}</div>
    </div>`;
}

function renderDetailHeader(ticket) {
  const header = document.getElementById('cusDetailHeader');
  const title = ticket ? ticket.title : `#${_activeTicketId}`;
  header.innerHTML = `<div class="cus-detail-title">#${_activeTicketId} ${escHtml(title)}</div>`;
}

function updateSatisfactionUI() {
  if (!_ticket) {
    document.getElementById('cusSatisfaction').style.display = 'none';
    return;
  }

  if ((_ticket.service_ended || _ticket.status === 'closed') && !_ticket.satisfaction) {
    document.getElementById('cusSatisfaction').style.display = '';
    _selectedRating = null;
    document.querySelectorAll('.cus-sat-btn').forEach(b => b.classList.remove('selected'));
  } else {
    document.getElementById('cusSatisfaction').style.display = 'none';
  }
}

function toggleReply() {
  _replyOpen = !_replyOpen;
  renderCurrentTimeline();
}

function renderCurrentTimeline() {
  // Re-render timeline from cached DOM — just re-fetch messages
  _lastMsgId = 0;
  loadMessages();
}

async function closeTicket() {
  if (!confirm('确认结束此工单？如果问题已解决，请评价我们的服务。')) return;

  try {
    const resp = await fetch(
      `/api/customer/tickets/${_activeTicketId}/close?token=${encodeURIComponent(_token)}`,
      { method: 'POST' }
    );
    if (!resp.ok) {
      const err = await resp.json();
      alert(err.detail || '操作失败');
      return;
    }
    _lastMsgId = 0;
    _replyOpen = false;
    await loadMessages();
  } catch (e) {
    alert('网络错误，请重试');
  }
}

// ==================== Reply ====================

async function sendInlineReply() {
  const input = document.getElementById('cusInlineReplyInput');
  if (!input) return;
  const content = input.value.trim();
  if (!content || !_activeTicketId) return;

  input.value = '';
  input.disabled = true;
  const btn = document.querySelector('.cus-inline-reply-btn');
  if (btn) btn.disabled = true;

  try {
    const resp = await fetch(
      `/api/customer/tickets/${_activeTicketId}/reply?token=${encodeURIComponent(_token)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      }
    );

    if (!resp.ok) {
      const err = await resp.json();
      alert(err.detail || '发送失败');
      input.disabled = false;
      if (btn) btn.disabled = false;
      return;
    }

    // Reload messages to show the new one
    _replyOpen = false;
    _lastMsgId = 0;
    await loadMessages();
  } catch (e) {
    alert('网络错误，请重试');
    input.disabled = false;
    if (btn) btn.disabled = false;
  }
}

// ==================== Satisfaction ====================

function selectRating(rating) {
  _selectedRating = rating;
  document.querySelectorAll('.cus-sat-btn').forEach(b => {
    b.classList.toggle('selected',
      (rating === 'yes' && b.classList.contains('yes')) ||
      (rating === 'no' && b.classList.contains('no')));
  });
}

async function submitFeedback() {
  if (!_selectedRating) {
    alert('请先选择「已解决」或「未解决」');
    return;
  }

  const textEl = document.getElementById('cusFeedbackText');
  const feedbackText = textEl ? textEl.value.trim() : '';

  try {
    await fetch(`/api/tickets/${_activeTicketId}/satisfaction`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        resolved: _selectedRating,
        feedback_text: feedbackText,
      }),
    });
  } catch (e) { /* ignore */ }

  document.getElementById('cusSatisfaction').innerHTML = `
    <div style="font-size:40px;margin-bottom:12px;">✨</div>
    <div style="font-size:16px;font-weight:600;color:var(--text-primary);">感谢您的反馈！</div>
    <div style="color:var(--text-secondary);margin-top:6px;font-size:14px;">您的意见帮助我们改进服务</div>`;

  setTimeout(() => {
    showView('list');
    loadTicketList();
  }, 2000);
}

// ==================== Polling ====================

function startPolling() {
  stopPolling();
  _pollTimer = setInterval(() => {
    if (_currentView === 'detail' && _activeTicketId) {
      loadMessages();
    }
  }, 15000); // Poll every 15 seconds
}

function stopPolling() {
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
}

// ==================== Helpers ====================

function formatTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  if (isToday) return `今天 ${hh}:${mm}`;
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${month}/${day} ${hh}:${mm}`;
}

// ==================== Keyboard ====================

document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && _currentView === 'detail') {
    const input = document.getElementById('cusInlineReplyInput');
    if (input && document.activeElement === input) {
      e.preventDefault();
      sendInlineReply();
    }
  }
});

// ==================== Export ====================

window.CustomerView = {
  back,
  showCreate,
  submitTicket,
  showDetail,
  sendInlineReply,
  toggleReply,
  closeTicket,
  selectRating,
  submitFeedback,
};

// Init on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
