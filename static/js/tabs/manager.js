import { api } from '../api.js';
import { statusLabels } from '../config.js';
import { escHtml, formatDate, formatDuration } from '../utils.js';

// ==================== Dashboard ====================

let _metricsTimer = null;
let _dashboardView = 'overview';
let _lastMetrics = null;

const dashboardViews = [
  { key: 'overview', label: '总览' },
  { key: 'satisfaction', label: '满意度' },
  { key: 'ai', label: 'AI 质量' },
  { key: 'knowledge', label: '知识库情况' },
];

export function renderDashboard() {
  return `
    <div class="manager-dashboard">
      <div class="manager-dashboard-titlebar">
        <div>
          <div class="dashboard-eyebrow">Management Dashboard</div>
          <h2>运营仪表盘</h2>
        </div>
        <button class="dashboard-refresh" onclick="app.loadMetrics()">刷新</button>
      </div>
      <div id="metricsDisplay"></div>
    </div>`;
}

export async function loadMetrics() {
  try {
    const data = await api('/api/metrics');
    const m = data.data;
    _lastMetrics = m;
    const display = document.getElementById('metricsDisplay');
    if (!display) return;
    display.innerHTML = renderMetricsDashboard(m);
  } catch (e) {
    const display = document.getElementById('metricsDisplay');
    if (display) display.innerHTML = '<div class="dashboard-error">指标加载失败，请稍后重试。</div>';
  }

  // Auto-refresh every 30s
  if (_metricsTimer) clearInterval(_metricsTimer);
  _metricsTimer = setInterval(() => loadMetrics(), 30000);
}

export function setDashboardView(view) {
  if (!dashboardViews.some(v => v.key === view)) return;
  _dashboardView = view;
  if (_lastMetrics) {
    const display = document.getElementById('metricsDisplay');
    if (display) display.innerHTML = renderMetricsDashboard(_lastMetrics);
  }
}

function renderMetricsDashboard(m) {
  const todayTickets = num(m.today_tickets);
  const escalationRate = fmtPct(m.escalation_rate);
  const docUpdatesToday = num(m.doc_updates_today);
  const aiQueriesToday = num(m.ai_queries_today);
  const closedTickets = Math.max(0, num(m.total_tickets) - num(m.pending_tickets) - num(m.escalated_count));

  return `
    <div class="dashboard-toolbar">
      <div class="dashboard-tabs">
        ${dashboardViews.map(v => `
          <button class="dashboard-tab-btn ${_dashboardView === v.key ? 'active' : ''}" onclick="app.setDashboardView('${v.key}')">
            ${v.label}
          </button>`).join('')}
      </div>
      <div class="dashboard-updated">自动刷新 · 30s</div>
    </div>

    <div class="dashboard-summary-grid">
      ${summaryCard('今日工单数', todayTickets, `本周累计 ${num(m.week_tickets)} 单`)}
      ${summaryCard('升级率', escalationRate, `${num(m.escalated_count)} 单升级中，${num(m.escalated_waiting)} 单待接管`)}
      ${summaryCard('今日文档更新', docUpdatesToday, `${num(m.d1_doc_count) + num(m.d2_doc_count)} 篇知识库文档`)}
      ${summaryCard('AI 提问次数', aiQueriesToday, `平均置信度 ${fmtPct(m.avg_confidence)}`)}
    </div>

    <div class="dashboard-main-grid">
      <section class="dashboard-chart-card">
        <div class="chart-header">
          <div>
            <h3>往日工单趋势</h3>
            <p>柱状图为每日工单数量，折线为升级数量。</p>
          </div>
          <div class="chart-legend">
            <span><i class="legend-bar"></i>工单数</span>
            <span><i class="legend-line"></i>升级数</span>
          </div>
        </div>
        ${renderOperationsChart(m.daily_operations)}
      </section>

      <section class="dashboard-insight-card">
        ${renderInsightPanel(m, closedTickets)}
      </section>
    </div>
  `;
}

function summaryCard(label, value, note) {
  return `
    <div class="summary-card">
      <div class="summary-label">${label}</div>
      <div class="summary-value">${value ?? '-'}</div>
      <div class="summary-note">${note}</div>
    </div>`;
}

function renderInsightPanel(m, closedTickets) {
  if (_dashboardView === 'satisfaction') {
    const yes = num(m.satisfaction_yes);
    const no = num(m.satisfaction_no);
    const total = yes + no;
    const rate = total ? yes / total : 0;
    return `
      <div class="insight-title">满意度</div>
      <div class="insight-subtitle">客户服务结束后的反馈汇总</div>
      ${bigStat('好评率', total ? fmtPct(rate) : '-')}
      ${progressBar(rate, 'var(--success)')}
      <div class="panel-list">
        ${panelRow('好评', yes)}
        ${panelRow('差评', no)}
        ${panelRow('反馈总数', total)}
      </div>
    `;
  }

  if (_dashboardView === 'ai') {
    return `
      <div class="insight-title">AI 质量</div>
      <div class="insight-subtitle">按回答置信度分层观察 AI 辅助效果</div>
      ${bigStat('平均置信度', fmtPct(m.avg_confidence))}
      <div class="panel-list">
        ${panelRow('绿色率', fmtPct(m.green_rate), 'good')}
        ${panelRow('黄色率', fmtPct(m.yellow_rate), 'warn')}
        ${panelRow('红色率', fmtPct(m.red_rate), num(m.red_rate) > 0.2 ? 'bad' : '')}
        ${panelRow('今日提问', num(m.ai_queries_today))}
      </div>
    `;
  }

  if (_dashboardView === 'knowledge') {
    const approved = num(m.d1_doc_count);
    const rd = num(m.d2_doc_count);
    const pending = num(m.pending_review_count);
    return `
      <div class="insight-title">知识库情况</div>
      <div class="insight-subtitle">D1 客服知识、D2 研发知识与审核队列</div>
      ${bigStat('今日更新次数', num(m.doc_updates_today))}
      <div class="panel-list">
        ${panelRow('D1 已审核', approved)}
        ${panelRow('D2 研发知识', rd)}
        ${panelRow('待审核', pending, pending ? 'warn' : '')}
        ${panelRow('文档人员', num(m.doc_count))}
      </div>
    `;
  }

  return `
    <div class="insight-title">运营总览</div>
    <div class="insight-subtitle">今日数据与当前工单池状态</div>
    ${bigStat('今日工单数', num(m.today_tickets))}
    <div class="panel-list">
      ${panelRow('待处理', num(m.pending_tickets), num(m.pending_tickets) ? 'warn' : '')}
      ${panelRow('升级中', num(m.escalated_count), num(m.escalated_count) ? 'bad' : '')}
      ${panelRow('已关闭', closedTickets, 'good')}
      ${panelRow('总工单数', num(m.total_tickets))}
    </div>
  `;
}

function bigStat(label, value) {
  return `
    <div class="insight-big-stat">
      <div>${label}</div>
      <strong>${value}</strong>
    </div>`;
}

function panelRow(label, value, tone = '') {
  return `
    <div class="panel-row">
      <span>${label}</span>
      <strong class="${tone}">${value}</strong>
    </div>`;
}

function progressBar(value, color) {
  const width = Math.max(0, Math.min(100, Math.round(num(value) * 100)));
  return `
    <div class="progress-bar">
      <span style="width:${width}%;background:${color};"></span>
    </div>`;
}

function renderOperationsChart(history) {
  const data = normalizeDailyOperations(history);
  const maxValue = Math.max(1, ...data.flatMap(d => [num(d.tickets), num(d.escalations)]));
  const maxY = Math.max(5, Math.ceil(maxValue * 1.2));
  const left = 46;
  const top = 24;
  const width = 604;
  const height = 210;
  const step = width / data.length;
  const barWidth = Math.min(36, Math.max(20, step * 0.42));
  const y = value => top + height - (num(value) / maxY) * height;

  const bars = data.map((d, index) => {
    const x = left + index * step + (step - barWidth) / 2;
    const barY = y(d.tickets);
    const barHeight = Math.max(2, top + height - barY);
    return `<rect class="chart-bar" x="${x.toFixed(1)}" y="${barY.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barHeight.toFixed(1)}" rx="5"></rect>`;
  }).join('');

  const linePoints = data.map((d, index) => {
    const x = left + index * step + step / 2;
    return `${x.toFixed(1)},${y(d.escalations).toFixed(1)}`;
  }).join(' ');

  const lineDots = data.map((d, index) => {
    const x = left + index * step + step / 2;
    return `<circle class="chart-dot" cx="${x.toFixed(1)}" cy="${y(d.escalations).toFixed(1)}" r="4"></circle>`;
  }).join('');

  const labels = data.map((d, index) => {
    const x = left + index * step + step / 2;
    return `<text class="chart-label" x="${x.toFixed(1)}" y="264" text-anchor="middle">${escHtml(d.label || '')}</text>`;
  }).join('');

  const ticks = [maxY, Math.round(maxY / 2), 0].map(value => {
    const tickY = y(value);
    return `
      <line class="chart-gridline" x1="${left}" y1="${tickY.toFixed(1)}" x2="${left + width}" y2="${tickY.toFixed(1)}"></line>
      <text class="chart-axis-label" x="34" y="${(tickY + 4).toFixed(1)}" text-anchor="end">${value}</text>`;
  }).join('');

  return `
    <svg class="dashboard-svg" viewBox="0 0 690 280" role="img" aria-label="近七日工单与升级趋势">
      ${ticks}
      ${bars}
      <polyline class="chart-line" points="${linePoints}"></polyline>
      ${lineDots}
      ${labels}
    </svg>`;
}

function normalizeDailyOperations(history) {
  if (Array.isArray(history) && history.length) return history;
  const formatter = new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' });
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - (6 - index));
    return {
      label: formatter.format(date).replace(/\//g, '/'),
      tickets: 0,
      escalations: 0,
    };
  });
}

function fmtPct(value) {
  return `${Math.round(num(value) * 100)}%`;
}

function num(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
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
