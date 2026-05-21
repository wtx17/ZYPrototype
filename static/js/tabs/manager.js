import { api } from '../api.js';
import { statusLabels } from '../config.js';
import { escHtml, formatDate, formatDuration } from '../utils.js';

// ==================== Dashboard ====================

let _metricsTimer = null;

export function renderDashboard() {
  return `
    <div class="card" style="margin-bottom:24px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <h3 style="margin:0;">运营看板</h3>
        <button class="btn btn-outline btn-sm" onclick="app.loadMetrics()">刷新</button>
      </div>
      <div id="metricsDisplay"></div>
    </div>`;
}

export async function loadMetrics() {
  try {
    const data = await api('/api/metrics');
    const m = data.data;
    const display = document.getElementById('metricsDisplay');
    if (!display) return;

    const redRate = m.red_rate || 0;
    display.innerHTML = `
      <div class="dashboard-section">
        <div class="dashboard-section-title">工单</div>
        <div class="metrics-grid">
          ${metricCard('本周新建', m.week_tickets)}
          ${metricCard('待处理', m.pending_tickets, m.pending_tickets > 0 ? 'var(--warning)' : '')}
          ${metricCard('升级中', m.escalated_count, m.escalated_count > 0 ? 'var(--danger)' : '')}
          ${metricCard('已关闭', (m.total_tickets || 0) - (m.pending_tickets || 0) - (m.escalated_count || 0))}
        </div>
      </div>

      <div class="dashboard-section">
        <div class="dashboard-section-title">AI 质量</div>
        <div class="metrics-grid">
          ${metricCard('平均置信度', (m.avg_confidence * 100).toFixed(0) + '%', m.avg_confidence >= 0.8 ? 'var(--success)' : m.avg_confidence >= 0.6 ? 'var(--warning)' : 'var(--danger)')}
          ${metricCard('今日查询', m.ai_queries_today)}
          ${metricCard('绿色率', (m.green_rate * 100).toFixed(0) + '%', 'var(--success)')}
          ${metricCard('红色率', (redRate * 100).toFixed(0) + '%', redRate > 0.2 ? 'var(--danger)' : redRate > 0.1 ? 'var(--warning)' : '')}
        </div>
      </div>

      <div class="dashboard-section">
        <div class="dashboard-section-title">满意度</div>
        <div class="metrics-grid">
          ${metricCard('好评', m.satisfaction_yes || 0, 'var(--success)')}
          ${metricCard('差评', m.satisfaction_no || 0, m.satisfaction_no > 0 ? 'var(--danger)' : '')}
          ${metricCard('好评率', ((m.satisfaction_yes || 0) + (m.satisfaction_no || 0) > 0 ? ((m.satisfaction_yes || 0) / ((m.satisfaction_yes || 0) + (m.satisfaction_no || 0)) * 100).toFixed(0) + '%' : '-'), 'var(--success)')}
        </div>
      </div>

      <div class="dashboard-section">
        <div class="dashboard-section-title">知识库</div>
        <div class="metrics-grid">
          ${metricCard('D1 已审核', m.d1_doc_count, 'var(--cs)')}
          ${metricCard('D2 研发', m.d2_doc_count, 'var(--rd)')}
          ${metricCard('待审核', m.pending_review_count, m.pending_review_count > 0 ? 'var(--warning)' : '')}
        </div>
      </div>
    `;
  } catch (e) {
    // ignore
  }

  // Auto-refresh every 30s
  if (_metricsTimer) clearInterval(_metricsTimer);
  _metricsTimer = setInterval(() => loadMetrics(), 30000);
}

function metricCard(label, value, color) {
  const style = color ? ` style="color:${color};"` : '';
  return `
    <div class="metric">
      <div class="value"${style}>${value ?? '-'}</div>
      <div class="label">${label}</div>
    </div>`;
}

// ==================== All Tickets ====================

let _ticketFilter = 'all';

export function renderAllTickets() {
  return `
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="margin:0;">全部工单</h3>
        <button class="btn btn-outline btn-sm" onclick="app.loadManagerTickets()">刷新</button>
      </div>
      <div class="filter-bar" id="ticketFilterBar">
        <button class="filter-btn ${_ticketFilter === 'all' ? 'active' : ''}" onclick="app.setTicketFilter('all')">全部</button>
        <button class="filter-btn ${_ticketFilter === 'pending' ? 'active' : ''}" onclick="app.setTicketFilter('pending')">待处理</button>
        <button class="filter-btn ${_ticketFilter === 'escalated' ? 'active' : ''}" onclick="app.setTicketFilter('escalated')">升级中</button>
        <button class="filter-btn ${_ticketFilter === 'closed' ? 'active' : ''}" onclick="app.setTicketFilter('closed')">已关闭</button>
      </div>
      <div id="allTicketList"><div class="empty">加载中...</div></div>
    </div>`;
}

export function setTicketFilter(filter) {
  _ticketFilter = filter;
  // Re-render filter bar
  const bar = document.getElementById('ticketFilterBar');
  if (bar) {
    bar.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    bar.querySelector(`.filter-btn[onclick*="${filter}"]`)?.classList.add('active');
  }
  loadManagerTickets();
}

export async function loadManagerTickets() {
  const container = document.getElementById('allTicketList');
  if (!container) return;

  try {
    const data = await api('/api/tickets');
    let tickets = data.data || [];

    // Client-side filter
    if (_ticketFilter === 'pending') {
      tickets = tickets.filter(t => t.status === 'pending');
    } else if (_ticketFilter === 'escalated') {
      tickets = tickets.filter(t => t.status === 'escalated');
    } else if (_ticketFilter === 'closed') {
      tickets = tickets.filter(t => t.status === 'closed' || t.service_ended);
    }

    if (!tickets.length) {
      container.innerHTML = '<div class="empty">暂无工单</div>';
      return;
    }

    let html = '<table class="tickets-table"><thead><tr>'
      + '<th>ID</th><th>标题</th><th>状态</th><th>处理人</th>'
      + '<th>创建时间</th><th>接管时间</th><th>更新时间</th><th>处理时长</th><th>满意度</th>'
      + '</tr></thead><tbody>';
    tickets.forEach((ticket) => {
      let status = statusLabels[ticket.status] || ticket.status;
      let statusCls = ticket.status;
      let barColor = ticket.status === 'closed' || ticket.service_ended ? 'var(--success)'
        : ticket.status === 'escalated' ? 'var(--danger)'
        : ticket.status === 'handling' ? 'var(--cs)'
        : 'var(--warning)';

      if (ticket.status === 'escalated') {
        if (!ticket.assigned_rd_id) {
          status = '等待接管';
          statusCls = 'escalated-waiting';
        } else {
          status = '研发处理中';
          statusCls = 'escalated-handling';
          barColor = 'var(--rd)';
        }
      }

      // Handler
      const handler = ticket.cs_name || ticket.rd_name || '-';

      // Acceptance time & duration
      const acceptedAt = ticket.rd_accepted_at || ticket.cs_accepted_at || null;
      const duration = formatDuration(acceptedAt, ticket.service_ended ? ticket.updated_at : null);

      // Satisfaction
      let satHtml = '-';
      if (ticket.satisfaction === 'yes') satHtml = '<span style="color:var(--success);font-weight:600;">好评</span>';
      else if (ticket.satisfaction === 'no') satHtml = '<span style="color:var(--danger);font-weight:600;">差评</span>';

      html += `<tr style="border-left:3px solid ${barColor};cursor:pointer;" onclick="app.showManagerTicketDetail(${ticket.id}, this)" data-ticket='${JSON.stringify(ticket).replace(/'/g, "&#39;")}'>
        <td class="ticket-id-cell">#${ticket.id}</td>
        <td class="ticket-title-cell">${escHtml(ticket.title).substring(0, 60)}</td>
        <td><span class="status-tag ${statusCls}">${status}</span></td>
        <td>${escHtml(handler)}</td>
        <td>${formatDate(ticket.created_at)}</td>
        <td>${formatDate(acceptedAt)}</td>
        <td>${formatDate(ticket.updated_at)}</td>
        <td>${duration}</td>
        <td>${satHtml}</td>
      </tr>`;
    });
    html += '</tbody></table>';
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = '<div class="empty">加载失败</div>';
  }
}

// ==================== Ticket Detail Card ====================

export async function showManagerTicketDetail(ticketId, rowEl) {
  // Clear previous row highlight
  document.querySelectorAll('.tickets-table tr.row-active').forEach(r => r.classList.remove('row-active'));
  rowEl.classList.add('row-active');

  // Parse ticket data from the row
  let ticket = {};
  try {
    ticket = JSON.parse(rowEl.getAttribute('data-ticket'));
  } catch (e) { /* ignore */ }

  const acceptedAt = ticket.rd_accepted_at || ticket.cs_accepted_at || null;
  const handler = ticket.cs_name || ticket.rd_name || '-';
  const duration = formatDuration(acceptedAt, ticket.service_ended ? ticket.updated_at : null);

  let status = statusLabels[ticket.status] || ticket.status;
  let statusCls = ticket.status;
  if (ticket.status === 'escalated') {
    status = ticket.assigned_rd_id ? '研发处理中' : '等待接管';
    statusCls = ticket.assigned_rd_id ? 'escalated-handling' : 'escalated-waiting';
  }

  // Build basic info section
  let html = '<div class="detail-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:8px 24px;margin-bottom:16px;">'
    + `<div><strong>标题:</strong> ${escHtml(ticket.title || '-')}</div>`
    + `<div><strong>描述:</strong> ${escHtml(ticket.description || '-')}</div>`
    + `<div><strong>状态:</strong> <span class="status-tag ${statusCls}">${status}</span></div>`
    + `<div><strong>客户:</strong> ${escHtml(ticket.customer_name || '-')}</div>`
    + `<div><strong>处理人:</strong> ${escHtml(handler)}</div>`
    + `<div><strong>创建时间:</strong> ${formatDate(ticket.created_at)}</div>`
    + `<div><strong>接管时间:</strong> ${formatDate(acceptedAt)}</div>`
    + `<div><strong>更新时间:</strong> ${formatDate(ticket.updated_at)}</div>`
    + `<div><strong>处理时长:</strong> ${duration}</div>`;

  if (ticket.satisfaction) {
    const satLabel = ticket.satisfaction === 'yes' ? '好评' : '差评';
    const satColor = ticket.satisfaction === 'yes' ? 'var(--success)' : 'var(--danger)';
    html += `<div><strong>满意度:</strong> <span style="color:${satColor};font-weight:600;">${satLabel}</span></div>`;
  }

  html += '</div>';

  // Sections for messages and AI logs
  html += '<div id="detail-messages" class="detail-section"><div class="empty">对话加载中...</div></div>';
  html += '<div id="detail-ai-logs" class="detail-section"><div class="empty">AI 日志加载中...</div></div>';

  // Build modal
  const modalHtml = '<div class="modal-overlay" id="ticketDetailModal" onclick="if(event.target===this)app.closeTicketDetailModal()">'
    + '<div class="card ticket-detail-card" style="max-width:800px;width:100%;">'
    + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">'
    + `<h3 style="margin:0;">工单 #${ticket.id} 详情</h3>`
    + '<button class="btn btn-outline btn-sm" onclick="app.closeTicketDetailModal()">关闭</button>'
    + '</div>'
    + html
    + '</div></div>';

  // Remove existing modal, add new one
  document.getElementById('ticketDetailModal')?.remove();
  document.body.insertAdjacentHTML('beforeend', modalHtml);

  // Fetch messages and AI logs in parallel
  const [msgRes, aiRes] = await Promise.all([
    api(`/api/tickets/${ticketId}/messages`),
    api(`/api/tickets/${ticketId}/ai-logs`),
  ]);

  _renderDetailMessages(msgRes.data || []);
  _renderDetailAILogs(aiRes.data || []);
}

export function closeTicketDetailModal() {
  document.getElementById('ticketDetailModal')?.remove();
  document.querySelectorAll('.tickets-table tr.row-active').forEach(r => r.classList.remove('row-active'));
}

function _renderDetailMessages(messages) {
  const el = document.getElementById('detail-messages');
  if (!el) return;

  if (!messages.length) {
    el.innerHTML = '<div class="section-title">对话记录</div><div class="empty">暂无对话记录</div>';
    return;
  }

  const roleColors = { customer: '#8e8e93', cs: 'var(--accent)', rd: 'var(--rd)', system: '#ff9f0a' };
  const roleLabels = { customer: '客户', cs: '客服', rd: '研发', system: '系统' };

  // Show last 20 messages
  const recent = messages.slice(-20);

  let html = '<div class="section-title">对话记录 (' + messages.length + ' 条)</div>';
  html += '<div class="msg-timeline">';
  recent.forEach(m => {
    const color = roleColors[m.sender_type] || '#8e8e93';
    const label = roleLabels[m.sender_type] || m.sender_type;
    html += '<div class="msg-item" style="padding:6px 0;border-bottom:1px solid var(--gray-100);">'
      + `<span class="sender-tag" style="display:inline-block;min-width:36px;padding:1px 6px;border-radius:var(--radius-sm);font-size:11px;font-weight:600;color:#fff;background:${color};text-align:center;margin-right:8px;">${label}</span>`
      + `<span style="color:var(--text-secondary);font-size:var(--text-xs);">${escHtml(m.sender_name)}</span>`
      + `<span style="color:var(--text-secondary);font-size:var(--text-xs);margin-left:8px;">${formatDate(m.created_at)}</span>`
      + `<div style="margin-top:2px;color:var(--text-primary);">${escHtml(m.content)}</div>`
      + '</div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

function _renderDetailAILogs(logs) {
  const el = document.getElementById('detail-ai-logs');
  if (!el) return;

  if (!logs.length) {
    el.innerHTML = '<div class="section-title">AI 查询记录</div><div class="empty">未使用 AI 辅助</div>';
    return;
  }

  let html = '<div class="section-title">AI 查询记录 (' + logs.length + ' 次)</div>';

  logs.forEach((log, i) => {
    const score = log.confidence_score || 0;
    const label = log.confidence_label || 'red';
    const labelText = { green: '高', yellow: '中', red: '低' }[label] || label;
    const confColor = label === 'green' ? 'var(--success)' : label === 'yellow' ? 'var(--warning)' : 'var(--danger)';
    const answerPreview = (log.answer_text || '').substring(0, 150);

    html += '<div style="margin-bottom:12px;padding:10px;background:var(--gray-50);border-radius:var(--radius-sm);">'
      + `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">`
      + `<span style="font-weight:600;color:var(--text-primary);">#${i + 1} ${escHtml(log.query_text).substring(0, 80)}</span>`
      + `<span style="display:flex;align-items:center;gap:8px;">`
      + `<span style="font-size:var(--text-xs);color:var(--text-secondary);">${formatDate(log.created_at)}</span>`
      + `<span style="padding:1px 8px;border-radius:10px;font-size:var(--text-xs);font-weight:600;background:${confColor}20;color:${confColor};">置信度: ${(score * 100).toFixed(0)}% (${labelText})</span>`
      + `</span></div>`
      + `<div style="color:var(--text-secondary);font-size:var(--text-sm);margin-bottom:4px;">${escHtml(answerPreview)}${log.answer_text && log.answer_text.length > 150 ? '...' : ''}</div>`;

    if (log.citations && log.citations.length) {
      html += '<div style="font-size:var(--text-xs);color:var(--text-secondary);">引用: ';
      log.citations.forEach((c, j) => {
        html += `${j > 0 ? '、' : ''}${escHtml(c.doc_title || '未知')}`;
      });
      html += '</div>';
    }

    html += '</div>';
  });

  el.innerHTML = html;
}
