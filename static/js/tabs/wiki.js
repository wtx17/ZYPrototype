import { api } from '../api.js';
import { state } from '../state.js';
import { escHtml, formatDate, toast } from '../utils.js';

let _wikiTreeData = [];
let _wikiExpandedNodes = {};
let _wikiCurrentSlug = null;
let _wikiCurrentPageStatus = '';

// ==================== Main Renderer ====================

export function renderWikiBrowser() {
  return `
    <div class="wiki-container">
      <div class="wiki-sidebar">
        <div class="wiki-filter-bar">
          <input type="text" id="wikiFilterInput" placeholder="在目录中筛选..."
            oninput="app.filterWikiTree()"
            onkeydown="if(event.key==='Escape'){this.value='';app.filterWikiTree();}if(event.key==='Enter'){app.searchWiki()}">
        </div>
        ${state.role === 'doc' ? `
          <div class="wiki-actions">
            <a href="#" class="wiki-new-page-link" onclick="event.preventDefault();app.showWikiEditor()">+ 新建页面</a>
          </div>
        ` : ''}
        <div class="wiki-tree" id="wikiTree">
          <div class="empty" style="padding:20px;">加载中...</div>
        </div>
      </div>
      <div class="wiki-resize-handle" id="wikiResizeHandle"></div>
      <div class="wiki-main" id="wikiMain">
        <div class="wiki-welcome">
          <h3>知识库浏览</h3>
          <p>请从左侧目录选择文档，或使用搜索查找内容。</p>
        </div>
      </div>
      <div class="wiki-toc-sidebar" id="wikiTOCSidebar">
        <div class="wiki-toc-title">本文目录</div>
        <div class="empty" id="wikiTOCTip" style="padding:10px;font-size:12px;color:var(--muted);">选择文档后显示</div>
      </div>
    </div>`;
}

// ==================== Tree ====================

export async function loadWikiTree() {
  try {
    const data = await api('/api/wiki/tree');
    _wikiTreeData = data.data || [];
    renderTree(_wikiTreeData);
  } catch (e) {
    const tree = document.getElementById('wikiTree');
    if (tree) tree.innerHTML = '<div class="empty" style="padding:20px;">加载失败</div>';
  }
}

function renderTree(nodes) {
  const tree = document.getElementById('wikiTree');
  if (!tree) return;

  if (!nodes.length) {
    tree.innerHTML = '<div class="empty" style="padding:20px;">暂无文档</div>';
    return;
  }

  tree.innerHTML = nodes.map(n => renderTreeNode(n, 0)).join('');

  // Restore expanded state
  for (const [id, expanded] of Object.entries(_wikiExpandedNodes)) {
    if (expanded) {
      const el = document.getElementById('wiki-children-' + id);
      if (el) el.style.display = 'block';
      const toggle = document.querySelector(`[data-wiki-toggle="${id}"]`);
      if (toggle) toggle.classList.add('expanded');
    }
  }
}

function renderTreeNode(node, depth) {
  const hasChildren = node.children && node.children.length > 0;
  const isActive = node.slug === _wikiCurrentSlug;
  const expanded = _wikiExpandedNodes[node.id] || false;
  const isD2 = node.source === 'd2';
  const isD2Folder = node.source === 'd2-folder';
  const st = node.status || '';
  const isDraft = st === 'draft';
  const isPending = st === 'pending_review';

  const statusDot = isDraft ? '<span class="wiki-status-dot draft" title="草稿"></span>'
    : isPending ? '<span class="wiki-status-dot pending" title="审核中"></span>' : '';

  return `
    <div class="wiki-tree-node" style="padding-left:${isD2Folder ? 0 : depth * 20}px;">
      <div class="wiki-tree-row">
        <span class="wiki-tree-toggle ${hasChildren ? '' : 'invisible'}${expanded ? ' expanded' : ''}"
          data-wiki-toggle="${node.id}"
          onclick="event.stopPropagation();app.toggleTreeNode(${node.id})">▸</span>
        <span class="wiki-tree-label ${isActive ? 'active' : ''} ${isD2Folder ? 'wiki-d2-folder' : ''} ${isDraft || isPending ? 'wiki-tree-dim' : ''}"
          onclick="${node.slug ? `app.loadWikiPage('${escHtml(node.slug)}')` : ''}">
          ${escHtml(node.title)}
          ${statusDot}
          ${isD2 ? '<span class="wiki-d2-dot" title="D2 研发知识库"></span>' : ''}
        </span>
      </div>
      ${hasChildren ? `
        <div class="wiki-tree-children" id="wiki-children-${node.id}"
          style="display:${expanded ? 'block' : 'none'}">
          ${node.children.map(c => renderTreeNode(c, depth + 1)).join('')}
        </div>
      ` : ''}
    </div>`;
}

export function toggleTreeNode(id) {
  _wikiExpandedNodes[id] = !_wikiExpandedNodes[id];
  const el = document.getElementById('wiki-children-' + id);
  if (el) el.style.display = _wikiExpandedNodes[id] ? 'block' : 'none';
  const toggle = document.querySelector(`[data-wiki-toggle="${id}"]`);
  if (toggle) toggle.classList.toggle('expanded', _wikiExpandedNodes[id]);
}

// ==================== Page Viewing ====================

export async function loadWikiPage(slug) {
  if (!slug) return;
  _wikiCurrentSlug = slug;
  _wikiCurrentPageStatus = '';

  // Update tree highlight
  const tree = document.getElementById('wikiTree');
  if (tree) {
    tree.querySelectorAll('.wiki-tree-label').forEach(l => l.classList.remove('active'));
    const activeLabel = tree.querySelector(`[onclick*="${slug}"]`);
    if (activeLabel) activeLabel.classList.add('active');
  }

  const main = document.getElementById('wikiMain');
  if (!main) return;

  try {
    const data = await api('/api/wiki/' + encodeURIComponent(slug));
    const page = data.data;
    if (!page) {
      main.innerHTML = '<div class="empty" style="padding:40px;">页面不存在</div>';
      return;
    }

    _wikiCurrentPageStatus = page.status || '';

    const isD2 = page.source === 'd2';
    const st = page.status || '';
    const role = state.role;
    const isLocked = st === 'pending_review';
    // doc can edit all; rd can edit D2; both blocked by pending_review
    const canEdit = !isLocked && (role === 'doc' || (role === 'rd' && isD2));

    const statusBadge = st === 'draft'
      ? '<span class="wiki-status-tag draft">草稿</span>'
      : st === 'pending_review'
        ? '<span class="wiki-status-tag pending">审核中</span>'
        : '';

    const actionButtons = canEdit
      ? (st === 'draft'
          ? `<a href="#" class="wiki-action-link" onclick="event.preventDefault();app.submitPageForReview(${page.id})">提交审核</a>
             <a href="#" class="wiki-action-link" onclick="event.preventDefault();app.showWikiEditor(${page.id})">编辑</a>
             <a href="#" class="wiki-action-link wiki-action-danger" onclick="event.preventDefault();app.deleteWikiPage(${page.id})">删除</a>`
          : `<a href="#" class="wiki-action-link" onclick="event.preventDefault();app.showWikiEditor(${page.id})">编辑</a>
             <a href="#" class="wiki-action-link wiki-action-danger" onclick="event.preventDefault();app.deleteWikiPage(${page.id})">删除</a>`)
      : (isLocked && (role === 'doc' || role === 'rd')
          ? '<span style="font-size:12px;color:var(--muted);">审核中，无法编辑</span>' : '');

    const metaTags = [
      isD2 ? '<span class="wiki-d2-label">研发知识库 (D2)</span>' : '',
      statusBadge,
      page.version ? `<span>版本: ${escHtml(page.version)}</span>` : '',
      page.entry_type ? `<span>类型: ${escHtml(page.entry_type === 'solution' ? '技术方案' : page.entry_type === 'release_note' ? '发布说明' : page.entry_type)}</span>` : '',
      page.keywords ? `<span>关键词: ${escHtml(page.keywords)}</span>` : '',
    ].filter(Boolean).join('');

    const breadcrumbs = buildBreadcrumbs(slug, page);
    const prevNext = getPrevNext(slug, page);

    main.innerHTML = `
      ${breadcrumbs}
      <div class="wiki-page-header">
        <h2>${escHtml(page.title)}</h2>
        <div class="wiki-meta">
          ${metaTags}
          <span>更新: ${formatDate(page.updated_at)}</span>
          <span>负责人: ${escHtml(page.owner || '-')}</span>
          ${actionButtons ? `<span style="flex:1;"></span>${actionButtons}` : ''}
        </div>
        ${page.release_note ? `<div class="wiki-release-note">📋 ${escHtml(page.release_note)}</div>` : ''}
      </div>
      ${isD2 ? '<div class="wiki-d2-disclaimer">此文档来自研发知识库，未经文档团队审核，请谨慎使用。</div>' : ''}
      ${st === 'draft' ? '<div class="wiki-draft-notice">此页面为草稿，仅文档团队可见。编辑完成后请提交审核。</div>' : ''}
      ${st === 'pending_review' ? '<div class="wiki-draft-notice">此页面正在审核中，审核通过后将对全员可见。</div>' : ''}
      <div class="wiki-markdown wiki-content">${renderMarkdown(page.content)}</div>
      ${prevNext}
      <div class="wiki-related-docs" id="wikiRelatedDocs"></div>
    `;

    // Wire up internal wiki links for SPA navigation
    const contentEl = main.querySelector('.wiki-content');
    if (contentEl) {
      contentEl.querySelectorAll('a[data-wiki-slug]').forEach(a => {
        const targetSlug = a.getAttribute('data-wiki-slug');
        a.setAttribute('onclick', `event.preventDefault();app.loadWikiPage('${escHtml(targetSlug)}')`);
        a.setAttribute('href', '#');
        a.style.cursor = 'pointer';
      });
    }

    // Load related pages and build TOC
    loadRelatedDocs(slug);
    buildTOC(slug);
  } catch (e) {
    main.innerHTML = '<div class="empty" style="padding:40px;">加载失败: ' + escHtml(e.message) + '</div>';
  }
}

async function loadRelatedDocs(slug) {
  const container = document.getElementById('wikiRelatedDocs');
  if (!container) return;

  try {
    const data = await api('/api/wiki/' + encodeURIComponent(slug) + '/related');
    const pages = data.data || [];
    if (!pages.length) {
      container.innerHTML = '';
      return;
    }
    container.innerHTML = `
      <h3>相关文档</h3>
      <ul class="wiki-related-list">
        ${pages.map(p => `
          <li><a href="#" class="wiki-related-link" onclick="event.preventDefault();app.loadWikiPage('${escHtml(p.slug)}')">${escHtml(p.title)}</a></li>
        `).join('')}
      </ul>`;
  } catch (e) {
    container.innerHTML = '';
  }
}

// ==================== Breadcrumbs ====================

function buildBreadcrumbs(slug, page) {
  if (!_wikiTreeData.length) return '';

  const chain = [];
  findAncestors(_wikiTreeData, slug, chain);
  chain.reverse();
  chain.push({ title: page.title, slug: slug });

  return `
    <div class="wiki-breadcrumbs">
      <a href="#" onclick="event.preventDefault();app.loadWikiPage(null);app.loadWikiTree();document.getElementById('wikiMain').innerHTML='<div class=\\'wiki-welcome\\'><h3>知识库浏览</h3><p>请从左侧目录选择文档，或使用搜索查找内容。</p></div>'">首页</a>
      ${chain.map((item, i) => {
        if (i === chain.length - 1) {
          return `<span class="sep">></span><span class="current">${escHtml(item.title)}</span>`;
        }
        return `<span class="sep">></span><a href="#" onclick="event.preventDefault();app.loadWikiPage('${escHtml(item.slug)}')">${escHtml(item.title)}</a>`;
      }).join('')}
    </div>`;
}

function findAncestors(nodes, targetSlug, chain) {
  for (const node of nodes) {
    if (node.slug === targetSlug) {
      return true;
    }
    if (node.children && node.children.length > 0) {
      if (findAncestors(node.children, targetSlug, chain)) {
        chain.push({ title: node.title, slug: node.slug });
        return true;
      }
    }
  }
  return false;
}

// ==================== Prev / Next ====================

function getPrevNext(slug, page) {
  const flat = [];
  flattenForNav(_wikiTreeData, flat);
  // Filter to same knowledge_type (d2 or non-d2)
  const kt = page.source === 'd2' ? 'd2' : (page.knowledge_type || 'd1');
  const sameType = flat.filter(n => {
    const nkt = n.source === 'd2' ? 'd2' : 'd1';
    return nkt === kt;
  });

  const idx = sameType.findIndex(n => n.slug === slug);
  if (idx < 0) return '';

  const prev = idx > 0 ? sameType[idx - 1] : null;
  const next = idx < sameType.length - 1 ? sameType[idx + 1] : null;

  if (!prev && !next) return '';

  return `
    <div class="wiki-prev-next">
      ${prev ? `<a href="#" class="prev-link" onclick="event.preventDefault();app.loadWikiPage('${escHtml(prev.slug)}')">
          <span class="prev-label">上一篇</span>${escHtml(prev.title)}
        </a>` : '<span style="flex:1;"></span>'}
      ${next ? `<a href="#" class="next-link" onclick="event.preventDefault();app.loadWikiPage('${escHtml(next.slug)}')">
          <span class="next-label">下一篇</span>${escHtml(next.title)}
        </a>` : '<span style="flex:1;"></span>'}
    </div>`;
}

function flattenForNav(nodes, result) {
  for (const node of nodes) {
    if (node.slug && !node.source?.startsWith('d2-folder') && node.title) {
      result.push(node);
    }
    if (node.children && node.children.length > 0) {
      flattenForNav(node.children, result);
    }
  }
}

// ==================== TOC ====================

function buildTOC(slug) {
  const sidebar = document.getElementById('wikiTOCSidebar');
  if (!sidebar) return;

  // Document selected — hide the placeholder tip
  const tipEl = document.getElementById('wikiTOCTip');
  if (tipEl) tipEl.style.display = 'none';

  const contentEl = document.querySelector(`.wiki-content`);
  if (!contentEl) {
    updateTOCList(sidebar, null);
    return;
  }

  const headings = contentEl.querySelectorAll('h2, h3');
  if (headings.length === 0) {
    updateTOCList(sidebar, null);
    return;
  }

  // Assign IDs and build TOC
  const items = [];
  headings.forEach((h, index) => {
    const id = 'wiki-h-' + index + '-' + slug.replace(/[^a-z0-9]/g, '-');
    h.id = id;
    items.push({
      id,
      text: h.textContent.trim(),
      tag: h.tagName.toLowerCase(),
    });
  });

  updateTOCList(sidebar, items);

  // IntersectionObserver for scroll highlighting
  if (window._wikiTocObserver) window._wikiTocObserver.disconnect();
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        sidebar.querySelectorAll('.wiki-toc-list a').forEach(a => a.classList.remove('active'));
        const link = sidebar.querySelector(`a[href="#${entry.target.id}"]`);
        if (link) link.classList.add('active');
        break;
      }
    }
  }, { rootMargin: '-80px 0px -60% 0px' });
  headings.forEach(h => observer.observe(h));
  window._wikiTocObserver = observer;
}

function updateTOCList(sidebar, items) {
  let tocList = sidebar.querySelector('.wiki-toc-list');
  if (!tocList) {
    tocList = document.createElement('ul');
    tocList.className = 'wiki-toc-list';
    const titleEl = sidebar.querySelector('.wiki-toc-title');
    if (titleEl) {
      titleEl.after(tocList);
    } else {
      sidebar.appendChild(tocList);
    }
  }
  if (!items || items.length === 0) {
    tocList.innerHTML = '<li><div class="empty" style="padding:10px;font-size:12px;color:var(--muted);">无标题</div></li>';
  } else {
    tocList.innerHTML = items.map(item => `
      <li>
        <a href="#${item.id}" class="${item.tag === 'h3' ? 'wiki-toc-h3' : ''}"
          onclick="event.preventDefault();document.getElementById('${item.id}').scrollIntoView({behavior:'smooth',block:'start'})">
          ${escHtml(item.text)}
        </a>
      </li>
    `).join('');
  }
}

export async function searchWikiFromTOC() {
  const tocInput = document.getElementById('wikiInpageSearch');
  const resultsEl = document.getElementById('wikiTOCResults');
  const tipEl = document.getElementById('wikiTOCTip');
  if (!tocInput || !resultsEl) return;

  const query = tocInput.value.trim();
  if (!query || query.length < 2) {
    resultsEl.style.display = 'none';
    if (tipEl) tipEl.style.display = '';
    return;
  }

  try {
    const data = await api('/api/wiki/search?q=' + encodeURIComponent(query));
    const results = data.data || [];
    if (!results.length) {
      resultsEl.style.display = 'block';
      resultsEl.innerHTML = '<div class="empty" style="padding:10px;font-size:12px;">无匹配结果</div>';
      if (tipEl) tipEl.style.display = 'none';
      return;
    }
    resultsEl.style.display = 'block';
    if (tipEl) tipEl.style.display = 'none';
    resultsEl.innerHTML = results.map(r => `
      <div class="wiki-toc-result-item" onclick="app.loadWikiPage('${escHtml(r.slug)}')">
        <div class="wiki-toc-result-title">${escHtml(r.title)}</div>
        <div class="wiki-toc-result-snippet">${escHtml(r.snippet || '')}</div>
      </div>
    `).join('');
  } catch (e) {
    resultsEl.style.display = 'none';
  }
}

// ==================== Markdown Rendering ====================

export function renderMarkdown(text) {
  if (!text) return '';

  // Use marked.js if available
  let html;
  if (typeof window.marked !== 'undefined' && window.marked.parse) {
    html = window.marked.parse(text);
  } else {
    html = basicMarkdown(text);
  }

  // Post-process: convert /wiki/{slug} links to data-wiki-slug attributes
  html = html.replace(
    /<a\s+(?:[^>]*?\s+)?href="\/wiki\/([^"]+)"([^>]*)>/gi,
    '<a data-wiki-slug="$1"$2>'
  );

  return html;
}

function basicMarkdown(text) {
  let html = escHtml(text);

  // Code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Italic
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  // Images
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1">');
  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
  // Headings
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // Unordered lists
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
  // Paragraphs (double newlines)
  html = html.replace(/\n\n/g, '</p><p>');
  html = '<p>' + html + '</p>';
  // Clean up empty paragraphs
  html = html.replace(/<p>\s*<\/p>/g, '');
  // Blockquotes
  html = html.replace(/<p>&gt; (.+)<\/p>/g, '<blockquote>$1</blockquote>');

  return html;
}

// ==================== Search / Filter ====================

export function filterWikiTree() {
  const input = document.getElementById('wikiFilterInput');
  if (!input) return;
  const query = input.value.trim().toLowerCase();

  if (!query) {
    renderTree(_wikiTreeData);
    return;
  }

  if (query.length < 2) {
    renderTree(_wikiTreeData);
    return;
  }

  // Filter tree: keep nodes whose title matches, plus their ancestors
  const filtered = filterNodes(_wikiTreeData, query);
  renderTree(filtered);
}

function filterNodes(nodes, query) {
  const result = [];
  for (const node of nodes) {
    const titleMatch = (node.title || '').toLowerCase().includes(query);
    const childMatches = node.children ? filterNodes(node.children, query) : [];
    if (titleMatch || childMatches.length > 0) {
      result.push({ ...node, children: childMatches.length > 0 ? childMatches : (node.children || []) });
      if (titleMatch && childMatches.length === 0 && node.children && node.children.length > 0) {
        // Title matches but no children match — still show children for context
        result[result.length - 1].children = node.children;
      }
    }
  }
  return result;
}

export async function searchWiki(query) {
  if (query === undefined) {
    const input = document.getElementById('wikiFilterInput');
    if (!input) return;
    query = input.value.trim();
  }

  if (!query) {
    renderTree(_wikiTreeData);
    return;
  }

  if (query.length < 2) return;

  try {
    const data = await api('/api/wiki/search?q=' + encodeURIComponent(query));
    const results = data.data || [];
    const tree = document.getElementById('wikiTree');
    if (!tree) return;

    if (!results.length) {
      tree.innerHTML = '<div class="empty" style="padding:20px;">无匹配结果</div>';
      return;
    }

    tree.innerHTML = results.map(r => `
      <div class="wiki-search-result" onclick="app.loadWikiPage('${escHtml(r.slug)}')">
        <div class="wiki-result-title">${escHtml(r.title)}</div>
        <div class="wiki-result-meta">${formatDate(r.updated_at)}</div>
      </div>
    `).join('');
  } catch (e) {
    // ignore search errors
  }
}

// ==================== Editor ====================

export async function showWikiEditor(pageId) {
  const main = document.getElementById('wikiMain');
  if (!main) return;

  let page = { title: '', content: '', parent_id: null, slug: '',
                 version: '', entry_type: '', release_note: '', keywords: '',
                 knowledge_type: state.role === 'rd' ? 'd2' : 'd1' };
  let isEdit = false;

  if (pageId) {
    try {
      const data = await api('/api/wiki/tree');
      const pages = flattenTree(data.data || []);
      const found = pages.find(p => p.id === pageId);
      if (found) {
        const pageData = await api('/api/wiki/' + encodeURIComponent(found.slug));
        if (pageData.data) {
          page = { ...page, ...pageData.data };
          isEdit = true;
        }
      }
    } catch (e) {
      toast('获取页面数据失败', 'error');
      return;
    }
  }

  const pagesFlat = flattenTree(_wikiTreeData);
  const parentOptions = pagesFlat
    .filter(p => !isEdit || p.id !== pageId)
    .map(p => `
      <option value="${p.id}" ${p.id === page.parent_id ? 'selected' : ''}>
        ${escHtml(p.title)}
      </option>
    `).join('');

  const ktOptions = [
    { val: 'd1', label: '客服知识库 (D1)' },
    { val: 'd2', label: '研发知识库 (D2)' },
  ].map(o => `<option value="${o.val}" ${page.knowledge_type === o.val ? 'selected' : ''}>${o.label}</option>`).join('');

  const entryTypeOptions = ['', 'solution', 'release_note']
    .map(t => `<option value="${t}" ${page.entry_type === t ? 'selected' : ''}>
      ${t === 'solution' ? '技术方案' : t === 'release_note' ? '发布说明' : '通用文档'}
    </option>`).join('');

  const editWarning = isEdit && page.status === 'approved'
    ? '<div class="wiki-draft-notice" style="margin-bottom:12px;">此页面已通过审核，修改后将退回草稿状态，需重新提交审核。</div>'
    : '';

  const showKt = state.role === 'doc' || state.role === 'rd';

  main.innerHTML = `
    <div class="card wiki-editor-card">
      <h3>${isEdit ? '编辑页面' : '新建页面'}</h3>
      ${editWarning}
      <div class="wiki-editor-grid">
        <div>
          <div class="section-label">标题</div>
          <input type="text" id="wikiEditorTitle" value="${escHtml(page.title)}" placeholder="页面标题">
        </div>
        <div>
          <div class="section-label">版本号</div>
          <input type="text" id="wikiEditorVersion" value="${escHtml(page.version || '')}" placeholder="如 v1.0">
        </div>
      </div>
      <div class="wiki-editor-grid" style="margin-top:8px;">
        ${showKt ? `
          <div>
            <div class="section-label">知识库分类</div>
            <select id="wikiEditorKnowledgeType">${ktOptions}</select>
          </div>
        ` : ''}
        <div>
          <div class="section-label">父页面</div>
          <select id="wikiEditorParent">
            <option value="">无父页面（根节点）</option>
            ${parentOptions}
          </select>
        </div>
      </div>
      <div class="wiki-editor-grid" style="margin-top:8px;">
        <div>
          <div class="section-label">文档类型</div>
          <select id="wikiEditorEntryType">${entryTypeOptions}</select>
        </div>
        <div>
          <div class="section-label">关键词</div>
          <input type="text" id="wikiEditorKeywords" value="${escHtml(page.keywords || '')}" placeholder="逗号分隔">
        </div>
      </div>
      <div class="section-label" style="margin-top:8px;">发布说明</div>
      <input type="text" id="wikiEditorReleaseNote" value="${escHtml(page.release_note || '')}" placeholder="本次更新的简要说明（可选）">
      <div class="section-label" style="margin-top:8px;">内容 (Markdown)</div>
      <div class="wiki-editor-toolbar">
        <button class="btn-sm btn-outline" onclick="app.showLinkSearchModal()">插入链接</button>
        <span class="wiki-editor-hint">或输入 [文字](/wiki/slug)</span>
      </div>
      <textarea id="wikiEditorContent" rows="15" placeholder="使用 Markdown 编写文档内容...">${escHtml(page.content)}</textarea>
      <div class="btn-group" style="margin-top:12px;">
        <button class="btn btn-primary" onclick="app.saveWikiPage(${pageId || 'null'})">保存</button>
        ${isEdit ? `<button class="btn btn-outline" onclick="app.loadWikiPage('${escHtml(page.slug)}')">取消</button>` : ''}
        ${!isEdit ? `<button class="btn btn-outline" onclick="app.loadWikiTree(); document.getElementById('wikiMain').innerHTML='<div class=\\'wiki-welcome\\'><h3>知识库浏览</h3><p>请从左侧目录选择文档，或使用搜索查找内容。</p></div>'">取消</button>` : ''}
      </div>
    </div>
    <div class="wiki-link-search-modal" id="wikiLinkSearchModal" style="display:none;">
      <div class="wiki-link-search-backdrop" onclick="app.closeLinkSearchModal()"></div>
      <div class="wiki-link-search-dialog">
        <div class="wiki-link-search-header">
          <h4>插入 Wiki 链接</h4>
          <button class="btn-sm" onclick="app.closeLinkSearchModal()">✕</button>
        </div>
        <input type="text" id="wikiLinkSearchInput" placeholder="搜索页面标题..."
          oninput="app.searchWikiPagesForLink()"
          onkeydown="if(event.key==='Escape'){app.closeLinkSearchModal()}">
        <div class="wiki-link-search-results" id="wikiLinkSearchResults">
          <div class="empty" style="padding:20px;">输入关键词搜索</div>
        </div>
      </div>
    </div>`;
}

export async function saveWikiPage(pageId) {
  const titleEl = document.getElementById('wikiEditorTitle');
  const parentEl = document.getElementById('wikiEditorParent');
  const contentEl = document.getElementById('wikiEditorContent');
  const versionEl = document.getElementById('wikiEditorVersion');
  const entryTypeEl = document.getElementById('wikiEditorEntryType');
  const releaseNoteEl = document.getElementById('wikiEditorReleaseNote');
  const keywordsEl = document.getElementById('wikiEditorKeywords');
  const ktEl = document.getElementById('wikiEditorKnowledgeType');

  if (!titleEl || !contentEl) return;

  const title = titleEl.value.trim();
  if (!title) { toast('标题不能为空', 'error'); return; }

  const body = {
    title: title,
    content: contentEl.value,
    parent_id: parentEl ? (parentEl.value || null) : null,
    version: versionEl ? versionEl.value.trim() : '',
    entry_type: entryTypeEl ? entryTypeEl.value : '',
    release_note: releaseNoteEl ? releaseNoteEl.value.trim() : '',
    keywords: keywordsEl ? keywordsEl.value.trim() : '',
    knowledge_type: ktEl ? ktEl.value : (state.role === 'rd' ? 'd2' : 'd1'),
  };
  if (body.parent_id) body.parent_id = parseInt(body.parent_id);

  try {
    if (pageId && pageId !== 'null') {
      // Editing an approved page → revert to draft for re-review
      if (_wikiCurrentPageStatus === 'approved') {
        body.status = 'draft';
      }
      await api('/api/wiki/' + pageId, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (_wikiCurrentPageStatus === 'approved') {
        toast('页面已更新，已退回草稿状态，请重新提交审核');
      } else {
        toast('页面已更新');
      }
    } else {
      const resp = await api('/api/wiki', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      toast('页面已创建');
      pageId = resp.id;
    }

    // Reload tree and navigate to the saved page
    await loadWikiTree();
    const data = await api('/api/wiki/tree');
    const pages = flattenTree(data.data || []);
    const saved = pages.find(p => p.id === pageId);
    if (saved) {
      await loadWikiPage(saved.slug);
    }
  } catch (e) {
    toast('保存失败: ' + e.message, 'error');
  }
}

export async function deleteWikiPage(pageId) {
  if (!pageId) return;
  if (!confirm('确认删除此页面？子页面将移至根节点。')) return;

  try {
    await api('/api/wiki/' + pageId, { method: 'DELETE' });
    toast('页面已删除');
    _wikiCurrentSlug = null;
    await loadWikiTree();
    const main = document.getElementById('wikiMain');
    if (main) {
      main.innerHTML = '<div class="wiki-welcome"><h3>知识库浏览</h3><p>请从左侧目录选择文档，或使用搜索查找内容。</p></div>';
    }
  } catch (e) {
    toast('删除失败: ' + e.message, 'error');
  }
}

export async function submitPageForReview(pageId) {
  if (!pageId) return;
  if (!confirm('确认提交审核？审核通过后将对全员可见。')) return;
  try {
    await api('/api/wiki/' + pageId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'pending_review' }),
    });
    toast('已提交审核');
    if (_wikiCurrentSlug) await loadWikiPage(_wikiCurrentSlug);
  } catch (e) {
    toast('提交失败: ' + e.message, 'error');
  }
}

// ==================== Link Search Modal ====================

export function showLinkSearchModal() {
  const modal = document.getElementById('wikiLinkSearchModal');
  if (!modal) return;
  modal.style.display = 'block';
  const input = document.getElementById('wikiLinkSearchInput');
  if (input) {
    input.value = '';
    input.focus();
  }
  document.getElementById('wikiLinkSearchResults').innerHTML = '<div class="empty" style="padding:20px;">输入关键词搜索</div>';
}

export function closeLinkSearchModal() {
  const modal = document.getElementById('wikiLinkSearchModal');
  if (modal) modal.style.display = 'none';
}

export async function searchWikiPagesForLink() {
  const input = document.getElementById('wikiLinkSearchInput');
  const resultsEl = document.getElementById('wikiLinkSearchResults');
  if (!input || !resultsEl) return;

  const q = input.value.trim();
  if (q.length < 2) {
    resultsEl.innerHTML = '<div class="empty" style="padding:20px;">输入关键词搜索</div>';
    return;
  }

  try {
    const data = await api('/api/wiki/search?q=' + encodeURIComponent(q));
    const results = data.data || [];
    if (!results.length) {
      resultsEl.innerHTML = '<div class="empty" style="padding:20px;">无匹配结果</div>';
      return;
    }
    resultsEl.innerHTML = results.map(r => `
      <div class="wiki-link-search-result" onclick="app.insertWikiLink('${escHtml(r.title)}', '${escHtml(r.slug)}')">
        <div class="wiki-link-search-result-title">${escHtml(r.title)}</div>
        <div class="wiki-link-search-result-slug">/${escHtml(r.slug)}</div>
      </div>
    `).join('');
  } catch (e) {
    resultsEl.innerHTML = '<div class="empty" style="padding:20px;">搜索失败</div>';
  }
}

export function insertWikiLink(title, slug) {
  const textarea = document.getElementById('wikiEditorContent');
  if (!textarea) return;

  const markdownLink = `[${title}](/wiki/${slug})`;
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const before = textarea.value.substring(0, start);
  const after = textarea.value.substring(end);
  textarea.value = before + markdownLink + after;
  textarea.focus();
  textarea.setSelectionRange(start + markdownLink.length, start + markdownLink.length);

  closeLinkSearchModal();
}

// ==================== Helpers ====================

function flattenTree(nodes) {
  const result = [];
  function walk(list) {
    for (const n of list) {
      result.push({ id: n.id, slug: n.slug, title: n.title, parent_id: n.parent_id });
      if (n.children) walk(n.children);
    }
  }
  walk(nodes);
  return result;
}
