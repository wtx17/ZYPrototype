import { api } from '../api.js';
import { statusLabels } from '../config.js';
import { escHtml, formatDate } from '../utils.js';

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

    let html = '<table class="tickets-table"><thead><tr><th>ID</th><th>标题</th><th>状态</th><th>创建时间</th></tr></thead><tbody>';
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

      html += `<tr style="border-left:3px solid ${barColor};">
        <td class="ticket-id-cell">#${ticket.id}</td>
        <td class="ticket-title-cell">${escHtml(ticket.title).substring(0, 60)}</td>
        <td><span class="status-tag ${statusCls}">${status}</span></td>
        <td>${formatDate(ticket.created_at)}</td>
      </tr>`;
    });
    html += '</tbody></table>';
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = '<div class="empty">加载失败</div>';
  }
}
