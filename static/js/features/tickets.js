import { statusLabels } from '../config.js';
import { api } from '../api.js';
import { state } from '../state.js';
import { escHtml, formatDate, toast } from '../utils.js';

function getTicketListId() {
  return state.currentTab === 'all-tickets' ? 'allTicketList' : 'csTicketList';
}

function getTicketListElement() {
  return document.getElementById(getTicketListId());
}

export async function loadTickets() {
  const data = await api('/api/tickets');
  const container = getTicketListElement();
  if (!container) return;

  const tickets = data.data || [];
  if (!tickets.length) {
    container.innerHTML = '<div class="empty">暂无工单</div>';
    return;
  }

  let html = '<table><thead><tr><th>ID</th><th>标题</th><th>状态</th><th>创建者</th><th>时间</th><th>操作</th></tr></thead><tbody>';
  tickets.forEach((ticket) => {
    const status = statusLabels[ticket.status] || ticket.status;
    const canEscalate = ticket.status !== 'closed' && ticket.status !== 'resolved';
    const canRecord = ticket.status !== 'closed' && ticket.status !== 'resolved';

    html += `<tr>
      <td>#${ticket.id}</td>
      <td>${escHtml(ticket.title).substring(0, 50)}</td>
      <td><span class="status-tag ${ticket.status}">${status}</span></td>
      <td>${escHtml(ticket.created_by)}</td>
      <td>${formatDate(ticket.created_at)}</td>
      <td>
        <button class="btn-sm" onclick="app.showTicketDetail(${ticket.id})">详情</button>
        ${state.role === 'cs' && canEscalate ? `<button class="btn-sm" onclick="app.doEscalate(${ticket.id})">升级</button>` : ''}
        ${state.role === 'cs' && canRecord ? `<button class="btn-sm" onclick="app.showHandlingForm(${ticket.id})">记录处理</button>` : ''}
      </td>
    </tr>`;
  });
  html += '</tbody></table>';

  container.innerHTML = html;
}

export async function showTicketDetail(ticketId) {
  const data = await api(`/api/tickets/${ticketId}`);
  const ticket = data.data;

  let html = `<div style="margin-top:12px;">
    <p><strong>标题:</strong> ${escHtml(ticket.title)}</p>
    <p><strong>描述:</strong> ${escHtml(ticket.description || '-')}</p>
    <p><strong>状态:</strong> ${escHtml(statusLabels[ticket.status] || ticket.status)}</p>
    <p><strong>创建时间:</strong> ${escHtml(ticket.created_at || '-')}</p>
    <p><strong>更新时间:</strong> ${escHtml(ticket.updated_at || '-')}</p>
  </div>`;

  document.querySelectorAll('.ticket-detail-card').forEach((card) => card.remove());
  const container = getTicketListElement();
  if (!container) return;

  container.insertAdjacentHTML(
    'beforebegin',
    `<div class="card ticket-detail-card">${html}<button class="btn btn-outline" onclick="app.closeCard(this)" style="margin-top:12px;">关闭</button></div>`,
  );
}

export async function doEscalate(ticketId) {
  await api(`/api/tickets/${ticketId}/escalate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: 'AI推荐升级' }),
  });
  toast('工单已升级至二线研发 (P4)');
  await loadTickets();
}

export async function showHandlingForm(ticketId) {
  const notes = window.prompt('请输入处理记录:');
  if (!notes) return;
  await api(`/api/tickets/${ticketId}/handling`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes }),
  });
  toast('处理记录已保存');
  await loadTickets();
}
