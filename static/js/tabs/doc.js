import { api } from '../api.js';
import { escHtml, formatDate, toast } from '../utils.js';

export function renderDocReview() {
  return `
    <div class="card">
      <h3>审核待发布知识 (Process 6)</h3>
      <button class="btn btn-outline" onclick="app.loadPendingReviews()" style="margin-bottom:12px;">刷新待审核列表</button>
      <div id="pendingReviewList"><div class="empty">点击刷新加载待审核知识</div></div>
    </div>`;
}

export async function loadPendingReviews() {
  const data = await api('/api/knowledge/pending');
  const container = document.getElementById('pendingReviewList');
  if (!container) {
    return;
  }

  const entries = data.data || [];
  if (!entries.length) {
    container.innerHTML = '<div class="empty">暂无待审核知识</div>';
    return;
  }

  let html = '<table><thead><tr><th>ID</th><th>标题</th><th>时间</th><th>操作</th></tr></thead><tbody>';
  entries.forEach((entry) => {
    html += `<tr>
      <td>#${entry.id}</td>
      <td>
        <a href="#" onclick="event.preventDefault();app.switchTab('wiki-browser');setTimeout(()=>app.loadWikiPage('${escHtml(entry.slug)}'),100)" style="color:var(--primary);">
          ${escHtml(entry.title)}
        </a>
      </td>
      <td>${formatDate(entry.created_at || entry.updated_at)}</td>
      <td>
        <button class="btn-sm" onclick="app.reviewKnowledge(${entry.id}, 'approved')" style="color:#34c759;">通过</button>
        <button class="btn-sm" onclick="app.reviewKnowledge(${entry.id}, 'rejected')" style="color:#ff3b30;">拒绝</button>
      </td>
    </tr>`;
  });
  html += '</tbody></table>';

  container.innerHTML = html;
}

export async function reviewKnowledge(id, status) {
  await api(`/api/knowledge/review/${id}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ review_status: status }),
  });

  toast(`知识已${status === 'approved' ? '通过审核' : '拒绝'}`);
  await loadPendingReviews();
}
