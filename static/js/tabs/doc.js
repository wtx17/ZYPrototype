import { api } from '../api.js';
import { escHtml, formatDate, toast } from '../utils.js';

export function renderDocSubmit() {
  return `
    <div class="card">
      <h3>提交知识至 D1 (Process 6: 脱敏、审查)</h3>
      <div class="section-label">提交的知识将自动脱敏后进入待审核状态</div>
      <input type="text" id="docTitle" placeholder="文档标题" style="margin-bottom:8px;">
      <input type="text" id="docCategory" placeholder="分类 (可选)" style="margin-bottom:8px;">
      <input type="text" id="docKeywords" placeholder="关键词 (可选)" style="margin-bottom:8px;">
      <textarea id="docContent" rows="5" placeholder="文档内容..."></textarea>
      <div class="btn-group"><button class="btn btn-primary" onclick="app.submitKnowledge()">提交至 D1 (待审核)</button></div>
      <div id="docSubmitResult"></div>
    </div>`;
}

export async function submitKnowledge() {
  const titleInput = document.getElementById('docTitle');
  const categoryInput = document.getElementById('docCategory');
  const keywordsInput = document.getElementById('docKeywords');
  const contentInput = document.getElementById('docContent');
  const result = document.getElementById('docSubmitResult');
  if (!titleInput || !categoryInput || !keywordsInput || !contentInput || !result) {
    return;
  }

  const title = titleInput.value.trim();
  const content = contentInput.value.trim();
  if (!title || !content) {
    toast('请填写标题和内容', 'error');
    return;
  }

  const data = await api('/api/knowledge/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title,
      content,
      category: categoryInput.value.trim(),
      keywords: keywordsInput.value.trim(),
    }),
  });

  result.innerHTML = `<div class="answer-box" style="background:#f0fdf4;margin-top:12px;">${escHtml(data.message)} (ID: ${data.id}, 脱敏 ${data.desensitized_changes} 处)</div>`;
  toast('知识已提交至 D1 待审核');
  titleInput.value = '';
  categoryInput.value = '';
  keywordsInput.value = '';
  contentInput.value = '';
}

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

  let html = '<table><thead><tr><th>ID</th><th>标题</th><th>分类</th><th>时间</th><th>操作</th></tr></thead><tbody>';
  entries.forEach((entry) => {
    const encodedContent = encodeURIComponent(entry.content || '');
    html += `<tr>
      <td>#${entry.id}</td>
      <td>${escHtml(entry.title)}</td>
      <td>${escHtml(entry.category || '-')}</td>
      <td>${formatDate(entry.created_at)}</td>
      <td>
        <button class="btn-sm" onclick="app.reviewKnowledge(${entry.id}, 'approved')" style="color:#34c759;">通过</button>
        <button class="btn-sm" onclick="app.reviewKnowledge(${entry.id}, 'rejected')" style="color:#ff3b30;">拒绝</button>
        <button class="btn-sm" onclick="app.showTextPreview('内容', decodeURIComponent('${encodedContent}'))">查看内容</button>
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
