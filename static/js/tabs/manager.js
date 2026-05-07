import { api } from '../api.js';

export function renderDashboard() {
  return `
    <div class="card">
      <h3>系统指标 (Process 8: 汇总)</h3>
      <button class="btn btn-outline" onclick="app.loadMetrics()" style="margin-bottom:16px;">刷新指标</button>
      <div id="metricsDisplay"></div>
    </div>`;
}

export function renderAllTickets() {
  return `
    <div class="card">
      <h3>全部工单</h3>
      <button class="btn btn-outline" onclick="app.loadTickets()" style="margin-bottom:12px;">刷新列表</button>
      <div id="allTicketList"><div class="empty">点击刷新加载工单</div></div>
    </div>`;
}

export async function loadMetrics() {
  const data = await api('/api/metrics');
  const metrics = data.data;
  const display = document.getElementById('metricsDisplay');
  if (!display) {
    return;
  }

  display.innerHTML = `
    <div class="metrics-grid">
      <div class="metric"><div class="value">${metrics.total_tickets}</div><div class="label">总工单数</div></div>
      <div class="metric"><div class="value">${metrics.escalated_count}</div><div class="label">已升级工单</div></div>
      <div class="metric"><div class="value">${(metrics.escalation_rate * 100).toFixed(1)}%</div><div class="label">升级率</div></div>
      <div class="metric"><div class="value" style="color:var(--green);">${(metrics.green_rate * 100).toFixed(1)}%</div><div class="label">绿色置信度</div></div>
      <div class="metric"><div class="value" style="color:var(--yellow);">${(metrics.yellow_rate * 100).toFixed(1)}%</div><div class="label">黄色置信度</div></div>
      <div class="metric"><div class="value" style="color:var(--red);">${(metrics.red_rate * 100).toFixed(1)}%</div><div class="label">红色置信度</div></div>
      <div class="metric"><div class="value">${metrics.d1_doc_count}</div><div class="label">D1 公开文档</div></div>
      <div class="metric"><div class="value">${metrics.d2_doc_count}</div><div class="label">D2 内部文档</div></div>
    </div>`;
}
