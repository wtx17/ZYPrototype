import { api } from '../api.js';
import { statusLabels } from '../config.js';
import { escHtml, formatDate, formatDuration } from '../utils.js';

// ==================== Dashboard ====================

let _metricsTimer = null;
let _dashboardView = 'overview';
let _lastMetrics = null;
let _dashboardTransition = '';

const dashboardViews = [
  { key: 'overview', label: '总览' },
  { key: 'satisfaction', label: '满意度' },
  { key: 'sla', label: 'SLA 指标' },
  { key: 'ai', label: 'AI 质量' },
  { key: 'knowledge', label: '知识库情况' },
];

const dashboardViewConfigs = {
  overview: {
    cards: renderOverviewCards,
    chart: renderOverviewChart,
    insight: renderOverviewInsight,
  },
  satisfaction: {
    cards: renderSatisfactionCards,
    chart: renderSatisfactionChart,
    insight: renderSatisfactionInsight,
  },
  sla: {
    cards: renderSLACards,
    chart: renderSLAChart,
    insight: renderSLAInsight,
  },
  ai: {
    cards: renderAICards,
    chart: renderAIChart,
    insight: renderAIInsight,
  },
  knowledge: {
    cards: renderKnowledgeCards,
    chart: renderKnowledgeChart,
    insight: renderKnowledgeInsight,
  },
};

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
  if (view === _dashboardView) return;
  const oldIndex = dashboardViews.findIndex(v => v.key === _dashboardView);
  const newIndex = dashboardViews.findIndex(v => v.key === view);
  _dashboardTransition = newIndex > oldIndex ? 'slide-from-right' : 'slide-from-left';
  _dashboardView = view;
  if (_lastMetrics) {
    const display = document.getElementById('metricsDisplay');
    if (display) display.innerHTML = renderMetricsDashboard(_lastMetrics);
  }
}

function renderMetricsDashboard(m) {
  const config = dashboardViewConfigs[_dashboardView] || dashboardViewConfigs.overview;
  const transition = _dashboardTransition;
  _dashboardTransition = '';

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

    <div class="dashboard-view-shell ${transition}" data-dashboard-view="${_dashboardView}">
      <div class="dashboard-summary-grid">
        ${config.cards(m)}
      </div>

      <div class="dashboard-main-grid">
        <section class="dashboard-chart-card">
          ${config.chart(m)}
        </section>

        <section class="dashboard-insight-card">
          ${config.insight(m)}
        </section>
      </div>
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

function renderOverviewCards(m) {
  return [
    summaryCard('今日工单数', num(m.today_tickets), `本周累计 ${num(m.week_tickets)} 单`),
    summaryCard('升级率', fmtPct(m.escalation_rate), `${num(m.escalated_total)} 单曾升级，${num(m.escalated_count)} 单升级中`),
    summaryCard('今日文档更新', num(m.doc_updates_today), `${num(m.d1_doc_count) + num(m.d2_doc_count)} 篇知识库文档`),
    summaryCard('AI 提问次数', num(m.ai_queries_today), `平均置信度 ${fmtPct(m.avg_confidence)}`),
  ].join('');
}

function renderOverviewChart(m) {
  return `
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
    ${renderOperationsChart(m.daily_operations)}`;
}

function renderOverviewInsight(m) {
  const closedTickets = Math.max(0, num(m.total_tickets) - num(m.pending_tickets) - num(m.escalated_count));
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

function renderSatisfactionCards(m) {
  const sat = getSatisfactionStats(m);
  return [
    summaryCard('反馈总数', sat.total, `${sat.yes} 个好评，${sat.no} 个差评`),
    summaryCard('好评率', sat.total ? fmtPct(sat.rate) : '-', '服务结束后的客户反馈'),
    summaryCard('好评数', sat.yes, sat.total ? `占比 ${fmtPct(sat.yes / sat.total)}` : '暂无反馈'),
    summaryCard('差评数', sat.no, sat.total ? `占比 ${fmtPct(sat.no / sat.total)}` : '暂无反馈'),
  ].join('');
}

function renderSatisfactionChart(m) {
  const sat = getSatisfactionStats(m);
  return `
    <div class="chart-header">
      <div>
        <h3>满意度分布</h3>
        <p>按客户服务结束后的反馈统计好评与差评。</p>
      </div>
      <div class="chart-legend">
        <span><i class="legend-good"></i>好评</span>
        <span><i class="legend-bad"></i>差评</span>
      </div>
    </div>
    ${renderShareBars([
      { label: '好评', value: sat.yes, total: sat.total, suffix: ' 个', tone: 'good' },
      { label: '差评', value: sat.no, total: sat.total, suffix: ' 个', tone: 'bad' },
    ], '暂无满意度反馈')}`;
}

function renderSatisfactionInsight(m) {
  const sat = getSatisfactionStats(m);
  return `
    <div class="insight-title">满意度</div>
    <div class="insight-subtitle">用反馈总量和好评率判断服务体验是否稳定。</div>
    ${bigStat('好评率', sat.total ? fmtPct(sat.rate) : '-')}
    ${progressBar(sat.rate, 'var(--success)')}
    <div class="panel-list">
      ${panelRow('反馈总数', sat.total)}
      ${panelRow('好评', sat.yes, 'good')}
      ${panelRow('差评', sat.no, sat.no ? 'bad' : '')}
      ${panelRow('建议', sat.total ? (sat.rate >= 0.8 ? '体验稳定' : '关注差评原因') : '先积累反馈')}
    </div>`;
}

function renderSLACards(m) {
  const risk = num(m.sla_at_risk);
  return [
    summaryCard('平均首次响应', fmtMins(num(m.sla_response_sec)), `首次客服接管平均耗时`),
    summaryCard('SLA 达标率', fmtPct(m.sla_compliance_rate), `${num(m.sla_compliant_count)} / ${num(m.sla_total_closed)} 单在 24h 内解决`),
    summaryCard('平均解决时长', fmtHours(num(m.sla_resolution_sec)), `已完结工单平均处理时长`),
    summaryCard('工单超时风险', risk, risk ? `${risk} 单超过 SLA 阈值未关闭` : '当前无超时工单'),
  ].join('');
}

function renderSLAChart(m) {
  const compliant = num(m.sla_compliant_count);
  const total = num(m.sla_total_closed);
  const breached = Math.max(0, total - compliant);
  return `
    <div class="chart-header">
      <div>
        <h3>SLA 达标分布</h3>
        <p>以 24 小时为 SLA 阈值，统计已完结工单的时效表现。</p>
      </div>
      <div class="chart-legend">
        <span><i class="legend-good"></i>达标</span>
        <span><i class="legend-bad"></i>超时</span>
      </div>
    </div>
    ${renderShareBars([
      { label: 'SLA 达标', value: compliant, total, suffix: ' 单', tone: 'good' },
      { label: 'SLA 超时', value: breached, total, suffix: ' 单', tone: 'bad' },
    ], '暂无已完结工单')}`;
}

function renderSLAInsight(m) {
  const risk = num(m.sla_at_risk);
  const rate = num(m.sla_compliance_rate);
  return `
    <div class="insight-title">SLA 指标</div>
    <div class="insight-subtitle">监控首次响应与解决时效，及时发现超时风险工单。</div>
    ${bigStat('SLA 达标率', fmtPct(rate))}
    ${progressBar(rate, rate >= 0.8 ? 'var(--success)' : rate >= 0.6 ? 'var(--warning)' : 'var(--danger)')}
    <div class="panel-list">
      ${panelRow('平均首次响应', fmtMins(num(m.sla_response_sec)))}
      ${panelRow('平均解决时长', fmtHours(num(m.sla_resolution_sec)))}
      ${panelRow('SLA 达标数', num(m.sla_compliant_count), 'good')}
      ${panelRow('超时风险工单', risk, risk ? 'bad' : '')}
    </div>`;
}

function renderAICards(m) {
  return [
    summaryCard('今日 AI 提问', num(m.ai_queries_today), '客服工作台 AI 调用次数'),
    summaryCard('平均置信度', fmtPct(m.avg_confidence), qualityNote(num(m.avg_confidence))),
    summaryCard('绿色率', fmtPct(m.green_rate), '高置信度回答占比'),
    summaryCard('红色率', fmtPct(m.red_rate), num(m.red_rate) > 0.2 ? '需要关注低置信回答' : '低置信占比较低'),
  ].join('');
}

function renderAIChart(m) {
  return `
    <div class="chart-header">
      <div>
        <h3>AI 置信度分布</h3>
        <p>绿色、黄色、红色分别代表高、中、低置信度回答占比。</p>
      </div>
      <div class="chart-legend">
        <span><i class="legend-good"></i>绿色</span>
        <span><i class="legend-warn"></i>黄色</span>
        <span><i class="legend-bad"></i>红色</span>
      </div>
    </div>
    ${renderShareBars([
      { label: '绿色回答', value: Math.round(num(m.green_rate) * 100), total: 100, suffix: '%', tone: 'good' },
      { label: '黄色回答', value: Math.round(num(m.yellow_rate) * 100), total: 100, suffix: '%', tone: 'warn' },
      { label: '红色回答', value: Math.round(num(m.red_rate) * 100), total: 100, suffix: '%', tone: 'bad' },
    ], '暂无 AI 质量数据')}`;
}

function renderAIInsight(m) {
  return `
    <div class="insight-title">AI 质量</div>
    <div class="insight-subtitle">观察 AI 辅助回答的置信度结构，及时发现低质量回答。</div>
    ${bigStat('平均置信度', fmtPct(m.avg_confidence))}
    ${progressBar(num(m.avg_confidence), confidenceColor(num(m.avg_confidence)))}
    <div class="panel-list">
      ${panelRow('今日提问', num(m.ai_queries_today))}
      ${panelRow('绿色率', fmtPct(m.green_rate), 'good')}
      ${panelRow('黄色率', fmtPct(m.yellow_rate), 'warn')}
      ${panelRow('红色率', fmtPct(m.red_rate), num(m.red_rate) > 0.2 ? 'bad' : '')}
    </div>`;
}

function renderKnowledgeCards(m) {
  return [
    summaryCard('今日更新', num(m.doc_updates_today), '文档版本更新次数'),
    summaryCard('D1 已审核', num(m.d1_doc_count), '客服可用知识'),
    summaryCard('D2 研发知识', num(m.d2_doc_count), '研发沉淀知识'),
    summaryCard('待审核', num(m.pending_review_count), num(m.pending_review_count) ? '需要文档团队处理' : '当前无积压'),
  ].join('');
}

function renderKnowledgeChart(m) {
  const total = num(m.d1_doc_count) + num(m.d2_doc_count) + num(m.pending_review_count);
  return `
    <div class="chart-header">
      <div>
        <h3>知识库状态分布</h3>
        <p>展示已审核 D1、D2 研发知识与待审核内容的规模。</p>
      </div>
      <div class="chart-legend">
        <span><i class="legend-info"></i>D1</span>
        <span><i class="legend-warn"></i>D2</span>
        <span><i class="legend-bad"></i>待审核</span>
      </div>
    </div>
    ${renderShareBars([
      { label: 'D1 已审核', value: num(m.d1_doc_count), total, suffix: ' 篇', tone: 'info' },
      { label: 'D2 研发知识', value: num(m.d2_doc_count), total, suffix: ' 篇', tone: 'warn' },
      { label: '待审核', value: num(m.pending_review_count), total, suffix: ' 篇', tone: 'bad' },
    ], '暂无知识库数据')}`;
}

function renderKnowledgeInsight(m) {
  const totalDocs = num(m.d1_doc_count) + num(m.d2_doc_count);
  return `
    <div class="insight-title">知识库情况</div>
    <div class="insight-subtitle">关注知识沉淀规模和待审核积压，避免 AI 可用知识滞后。</div>
    ${bigStat('今日更新次数', num(m.doc_updates_today))}
    <div class="panel-list">
      ${panelRow('知识库文档', totalDocs)}
      ${panelRow('D1 已审核', num(m.d1_doc_count), 'good')}
      ${panelRow('D2 研发知识', num(m.d2_doc_count), 'warn')}
      ${panelRow('待审核', num(m.pending_review_count), num(m.pending_review_count) ? 'bad' : '')}
    </div>`;
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

function renderShareBars(items, emptyText) {
  const hasData = items.some(item => num(item.value) > 0);
  if (!hasData) {
    return `<div class="dashboard-empty-state">${emptyText}</div>`;
  }

  return `
    <div class="share-bars">
      ${items.map(item => {
        const total = Math.max(1, num(item.total));
        const value = num(item.value);
        const width = Math.max(value > 0 ? 4 : 0, Math.min(100, (value / total) * 100));
        const suffix = item.suffix || ' 单';
        return `
          <div class="share-bar-row">
            <div class="share-bar-meta">
              <span>${item.label}</span>
              <strong>${value}${suffix}</strong>
            </div>
            <div class="share-bar-track">
              <span class="share-bar-fill ${item.tone || ''}" style="width:${width.toFixed(1)}%;"></span>
            </div>
            <div class="share-bar-pct">${fmtPct(value / total)}</div>
          </div>`;
      }).join('')}
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
    return `<rect class="chart-bar" x="${x.toFixed(1)}" y="${barY.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barHeight.toFixed(1)}" rx="5">
      <title>${chartTooltip(d)}</title>
    </rect>`;
  }).join('');

  const linePoints = data.map((d, index) => {
    const x = left + index * step + step / 2;
    return `${x.toFixed(1)},${y(d.escalations).toFixed(1)}`;
  }).join(' ');

  const lineDots = data.map((d, index) => {
    const x = left + index * step + step / 2;
    return `<circle class="chart-dot" cx="${x.toFixed(1)}" cy="${y(d.escalations).toFixed(1)}" r="4">
      <title>${chartTooltip(d)}</title>
    </circle>`;
  }).join('');

  const hoverZones = data.map((d, index) => {
    const x = left + index * step;
    return `<rect class="chart-hover-zone" x="${x.toFixed(1)}" y="${top}" width="${step.toFixed(1)}" height="${height}">
      <title>${chartTooltip(d)}</title>
    </rect>`;
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
      ${hoverZones}
      ${labels}
    </svg>`;
}

function chartTooltip(d) {
  return `${escHtml(d.label || '')}：工单 ${num(d.tickets)} 单，升级 ${num(d.escalations)} 单`;
}

function getSatisfactionStats(m) {
  const yes = num(m.satisfaction_yes);
  const no = num(m.satisfaction_no);
  const total = yes + no;
  return { yes, no, total, rate: total ? yes / total : 0 };
}

function qualityNote(value) {
  if (value >= 0.8) return '整体回答质量较稳';
  if (value >= 0.6) return '需要关注中低置信回答';
  return '建议补充知识库内容';
}

function confidenceColor(value) {
  if (value >= 0.8) return 'var(--success)';
  if (value >= 0.6) return 'var(--warning)';
  return 'var(--danger)';
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

function fmtMins(seconds) {
  const sec = num(seconds);
  if (sec <= 0) return '-';
  if (sec < 60) return `${sec}秒`;
  if (sec < 3600) return `${Math.round(sec / 60)} 分钟`;
  return `${(sec / 3600).toFixed(1)} 小时`;
}

function fmtHours(seconds) {
  const sec = num(seconds);
  if (sec <= 0) return '-';
  if (sec < 3600) return `${Math.round(sec / 60)} 分钟`;
  return `${(sec / 3600).toFixed(1)} 小时`;
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
    if (ticket.satisfaction_feedback) {
      html += `<div style="grid-column:1/-1;margin-top:4px;padding:8px 12px;background:var(--gray-50);border-radius:var(--radius-sm);font-size:var(--text-sm);color:var(--text-secondary);"><strong>客户反馈:</strong> ${escHtml(ticket.satisfaction_feedback)}</div>`;
    }
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
