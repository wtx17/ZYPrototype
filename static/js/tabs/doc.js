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
  if (!container) return;

  const entries = data.data || [];
  if (!entries.length) {
    container.innerHTML = '<div class="empty">暂无待审核知识</div>';
    return;
  }

  container.innerHTML = entries.map(entry => `
    <div class="review-card">
      <div class="review-card-header">
        <a href="/wiki/${escHtml(entry.slug)}" target="_blank" class="review-card-title">
          ${escHtml(entry.title)}
        </a>
        <div class="review-card-actions">
          <button class="btn-sm" onclick="app.reviewKnowledge(${entry.id}, 'approved')" style="color:var(--success);font-weight:600;">通过</button>
          <button class="btn-sm" onclick="app.reviewKnowledge(${entry.id}, 'rejected')" style="color:var(--danger);">驳回</button>
        </div>
      </div>
      <div class="review-card-meta">
        <span>提交人: ${escHtml(entry.owner || '-')}</span>
        <span>${formatDate(entry.created_at || entry.updated_at)}</span>
        ${entry.keywords ? `<span>关键词: ${escHtml(entry.keywords)}</span>` : ''}
      </div>
      ${entry.content ? `
        <div class="review-card-preview">${escHtml(entry.content.substring(0, 180))}${entry.content.length > 180 ? '...' : ''}</div>
      ` : ''}
    </div>
  `).join('');
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
