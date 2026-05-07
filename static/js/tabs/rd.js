import { api } from '../api.js';
import { statusLabels } from '../config.js';
import { escHtml, formatDate, toast } from '../utils.js';

export function renderRDEscalations() {
  return `
    <div class="card">
      <h3>升级工单列表 (Process 4 & 5)</h3>
      <button class="btn btn-outline" onclick="app.loadEscalatedTickets()" style="margin-bottom:12px;">刷新列表</button>
      <div id="escalatedList"><div class="empty">点击刷新加载升级工单</div></div>
    </div>`;
}

export async function loadEscalatedTickets() {
  const data = await api('/api/tickets');
  const container = document.getElementById('escalatedList');
  if (!container) {
    return;
  }

  const tickets = (data.data || []).filter((ticket) => ticket.escalated_to_rd && ticket.status !== 'closed');
  if (!tickets.length) {
    container.innerHTML = '<div class="empty">暂无升级工单</div>';
    return;
  }

  let html = '<table><thead><tr><th>ID</th><th>标题</th><th>状态</th><th>描述</th><th>操作</th></tr></thead><tbody>';
  tickets.forEach((ticket) => {
    const encodedSuggestion = encodeURIComponent(ticket.ai_suggestion || '');
    html += `<tr>
      <td>#${ticket.id}</td>
      <td>${escHtml(ticket.title).substring(0, 50)}</td>
      <td><span class="status-tag ${ticket.status}">${escHtml(statusLabels[ticket.status] || ticket.status)}</span></td>
      <td>${escHtml((ticket.description || '').substring(0, 80))}</td>
      <td>
        <button class="btn-sm" onclick="app.showResolveForm(${ticket.id})">解决</button>
        ${ticket.ai_suggestion ? `<button class="btn-sm" onclick="app.showTextPreview('AI建议', decodeURIComponent('${encodedSuggestion}'))">查看AI建议</button>` : ''}
      </td>
    </tr>`;
  });
  html += '</tbody></table>';

  container.innerHTML = html;
}

export async function showResolveForm(ticketId) {
  const solution = window.prompt('请输入解决方案:');
  if (!solution) {
    return;
  }

  const version = window.prompt('版本号 (可选):') || '';
  await api(`/api/escalations/${ticketId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ solution, version }),
  });

  toast('升级工单已解决 (P5)');
  await loadEscalatedTickets();
}

export function renderRDSubmitSolution() {
  return `
    <div class="card">
      <h3>沉淀知识至 D2 研发知识库 (Process 2)</h3>
      <input type="text" id="solTitle" placeholder="方案标题" style="margin-bottom:8px;">
      <input type="text" id="solVersion" placeholder="版本号 (可选)" style="margin-bottom:8px;">
      <input type="text" id="solKeywords" placeholder="关键词 (逗号分隔)" style="margin-bottom:8px;">
      <textarea id="solContent" rows="5" placeholder="方案内容..."></textarea>
      <div class="btn-group"><button class="btn btn-primary" onclick="app.submitSolution()">提交至 D2</button></div>
      <div id="solResult"></div>
    </div>`;
}

export async function submitSolution() {
  const titleInput = document.getElementById('solTitle');
  const versionInput = document.getElementById('solVersion');
  const keywordsInput = document.getElementById('solKeywords');
  const contentInput = document.getElementById('solContent');
  const result = document.getElementById('solResult');
  if (!titleInput || !versionInput || !keywordsInput || !contentInput || !result) {
    return;
  }

  const title = titleInput.value.trim();
  const content = contentInput.value.trim();
  if (!title || !content) {
    toast('请填写标题和内容', 'error');
    return;
  }

  const data = await api('/api/knowledge/rd', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title,
      content,
      version: versionInput.value.trim(),
      keywords: keywordsInput.value.trim(),
      entry_type: 'solution',
    }),
  });

  result.innerHTML = `<div class="answer-box" style="background:#f0fdf4;margin-top:12px;">${escHtml(data.message)} (ID: ${data.id})</div>`;
  toast('知识已沉淀至 D2');
  titleInput.value = '';
  versionInput.value = '';
  keywordsInput.value = '';
  contentInput.value = '';
}

export function renderRDReleaseNotes() {
  return `
    <div class="card">
      <h3>发布 Release Notes 至 D2 (Process 3)</h3>
      <input type="text" id="rnTitle" placeholder="Release Notes 标题" style="margin-bottom:8px;">
      <input type="text" id="rnVersion" placeholder="版本号" style="margin-bottom:8px;">
      <input type="text" id="rnKeywords" placeholder="关键词" style="margin-bottom:8px;">
      <textarea id="rnContent" rows="5" placeholder="Release Notes 内容..."></textarea>
      <div class="btn-group"><button class="btn btn-primary" onclick="app.submitReleaseNote()">发布至 D2</button></div>
      <div id="rnResult"></div>
    </div>`;
}

export async function submitReleaseNote() {
  const titleInput = document.getElementById('rnTitle');
  const versionInput = document.getElementById('rnVersion');
  const keywordsInput = document.getElementById('rnKeywords');
  const contentInput = document.getElementById('rnContent');
  const result = document.getElementById('rnResult');
  if (!titleInput || !versionInput || !keywordsInput || !contentInput || !result) {
    return;
  }

  const title = titleInput.value.trim();
  const content = contentInput.value.trim();
  if (!title || !content) {
    toast('请填写标题和内容', 'error');
    return;
  }

  const data = await api('/api/knowledge/release-notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title,
      content,
      version: versionInput.value.trim(),
      keywords: keywordsInput.value.trim(),
      release_note: title,
    }),
  });

  result.innerHTML = `<div class="answer-box" style="background:#f0fdf4;margin-top:12px;">${escHtml(data.message)} (ID: ${data.id})</div>`;
  toast('Release Note 已发布');
  titleInput.value = '';
  versionInput.value = '';
  keywordsInput.value = '';
  contentInput.value = '';
}

export function renderRDKnowledge() {
  return `
    <div class="card">
      <h3>D2 研发知识库</h3>
      <button class="btn btn-outline" onclick="app.loadRDKnowledge()" style="margin-bottom:12px;">刷新列表</button>
      <div id="rdKnowledgeList"><div class="empty">点击刷新加载 D2 知识库</div></div>
    </div>`;
}

export async function loadRDKnowledge() {
  const data = await api('/api/knowledge/rd');
  const container = document.getElementById('rdKnowledgeList');
  if (!container) {
    return;
  }

  const entries = data.data || [];
  if (!entries.length) {
    container.innerHTML = '<div class="empty">暂无 D2 知识条目</div>';
    return;
  }

  let html = '<table><thead><tr><th>ID</th><th>标题</th><th>类型</th><th>版本</th><th>时间</th></tr></thead><tbody>';
  entries.forEach((entry) => {
    html += `<tr>
      <td>#${entry.id}</td>
      <td>${escHtml(entry.title)}</td>
      <td><span class="d2-badge">${entry.entry_type === 'release_note' ? 'Release Note' : '方案'}</span></td>
      <td>${escHtml(entry.version || '-')}</td>
      <td>${formatDate(entry.created_at)}</td>
    </tr>`;
  });
  html += '</tbody></table>';

  container.innerHTML = html;
}
