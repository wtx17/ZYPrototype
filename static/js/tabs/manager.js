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

    display.innerHTML = `
      <div class="dashboard-section">
        <div class="dashboard-section-title">工单概览</div>
        <div class="metrics-grid">
          ${metricCard('本周新建', m.week_tickets, 'var(--primary)')}
          ${metricCard('待处理', m.pending_tickets, '#ff9500')}
          ${metricCard('升级待接管', m.escalated_waiting, m.escalated_waiting > 0 ? 'var(--red)' : 'var(--muted)')}
          ${metricCard('升级处理中', m.escalated_count - m.escalated_waiting, m.escalated_count > m.escalated_waiting ? '#ff9500' : 'var(--muted)')}
          ${metricCard('好评', m.satisfaction_yes || 0, 'var(--green)')}
          ${metricCard('差评', m.satisfaction_no || 0, m.satisfaction_no > 0 ? 'var(--red)' : 'var(--muted)')}
        </div>
      </div>

      <div class="dashboard-section">
        <div class="dashboard-section-title">AI 质量</div>
        <div class="metrics-grid">
          ${metricCard('平均置信度', (m.avg_confidence * 100).toFixed(0) + '%', m.avg_confidence >= 0.8 ? 'var(--green)' : m.avg_confidence >= 0.6 ? 'var(--yellow)' : 'var(--red)')}
          ${metricCard('今日 AI 查询', m.ai_queries_today)}
          ${metricCard('绿色率', (m.green_rate * 100).toFixed(0) + '%', 'var(--green)')}
          ${metricCard('红色率', (m.red_rate * 100).toFixed(0) + '%', 'var(--red)')}
        </div>
      </div>

      <div class="dashboard-section">
        <div class="dashboard-section-title">知识库</div>
        <div class="metrics-grid">
          ${metricCard('D1 已审核', m.d1_doc_count, 'var(--primary)')}
          ${metricCard('D2 研发', m.d2_doc_count, '#ff9500')}
          ${metricCard('待审核', m.pending_review_count, m.pending_review_count > 0 ? 'var(--yellow)' : 'var(--muted)')}
        </div>
      </div>

      <div class="dashboard-section">
        <div class="dashboard-section-title">团队</div>
        <div class="metrics-grid">
          ${metricCard('客服', m.cs_count || '-')}
          ${metricCard('研发', m.rd_count || '-')}
          ${metricCard('文档', m.doc_count || '-')}
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

    let html = '<table><thead><tr><th>ID</th><th>标题</th><th>状态</th><th>创建时间</th></tr></thead><tbody>';
    tickets.forEach((ticket) => {
      let status = statusLabels[ticket.status] || ticket.status;
      let statusCls = ticket.status;

      // Distinguish escalated: waiting vs handling
      if (ticket.status === 'escalated') {
        if (!ticket.assigned_rd_id) {
          status = '等待接管';
          statusCls = 'escalated-waiting';
        } else {
          status = '研发处理中';
          statusCls = 'escalated-handling';
        }
      }

      html += `<tr>
        <td>#${ticket.id}</td>
        <td>${escHtml(ticket.title).substring(0, 50)}</td>
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
