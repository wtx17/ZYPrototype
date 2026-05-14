import { escHtml } from './utils.js';
import { state } from './state.js';

// Build sorted term→slug map (longest terms first to avoid partial matches)
let _kwTerms = null;
function getKwTerms() {
  if (_kwTerms) return _kwTerms;
  const map = new Map();
  for (const entry of state.keywordIndex) {
    const terms = [entry.title];
    if (entry.keywords) {
      entry.keywords.split(',').forEach(kw => {
        const t = kw.trim();
        if (t) terms.push(t);
      });
    }
    for (const term of terms) {
      if (term.length < 2) continue;
      const existing = map.get(term);
      if (!existing || existing.length < entry.slug.length) {
        map.set(term, entry.slug);
      }
    }
  }
  _kwTerms = Array.from(map.entries())
    .sort((a, b) => b[0].length - a[0].length);
  return _kwTerms;
}

function linkifyKeywords(text) {
  if (!text) return '';
  const safe = escHtml(text);
  const terms = getKwTerms();
  if (!terms.length) return safe;

  // Escape regex special chars in terms, build alternation
  const escapedTerms = terms.map(([term]) =>
    term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  );
  const regex = new RegExp(escapedTerms.join('|'), 'gi');

  // Build lookup for replacement
  const slugMap = new Map(terms.map(([t, s]) => [t.toLowerCase(), s]));

  return safe.replace(regex, (match) => {
    const slug = slugMap.get(match.toLowerCase());
    if (slug) {
      return `<a href="#" class="kw-link" data-wiki-slug="${slug}" title="查看文档: ${match}">${match}</a>`;
    }
    return match;
  });
}

export function renderAgentChatBubble(msg, index) {
  const side = msg.sender_type === 'customer' ? 'customer'
    : msg.sender_type === 'system' ? 'system'
    : 'agent';

  if (side === 'system') {
    return `
      <div class="msg-system">
        <span class="msg-system-text">${escHtml(msg.content)}</span>
      </div>`;
  }

  const isCustomer = side === 'customer';
  const senderLabel = msg.sender_name || (isCustomer ? '客户' : '坐席');

  return `
    <div class="msg-row ${isCustomer ? 'msg-customer msg-hoverable' : 'msg-agent'}">
      <div class="msg-meta">
        <span class="msg-sender">${escHtml(senderLabel)}</span>
        <span class="msg-time">${formatTime(msg.created_at)}</span>
      </div>
      <div class="msg-bubble ${isCustomer ? 'bubble-customer' : 'bubble-agent'}">
        ${isCustomer ? linkifyKeywords(msg.content) : escHtml(msg.content)}
      </div>
      ${isCustomer ? `
        <div class="msg-ask-btn">
          <button class="btn btn-outline btn-sm" onclick="app.askAIForMessage(${index})">
            询问 AI 助手
          </button>
        </div>
      ` : ''}
    </div>`;
}

export function renderMessages(messages) {
  if (!messages || !messages.length) {
    return '<div class="empty">暂无消息</div>';
  }
  return messages.map((m, i) => renderAgentChatBubble(m, i)).join('');
}

export function renderActionBar(ticketId, role) {
  const canEscalate = role === 'cs' && ticketId;
  const canAccept = role === 'rd' && ticketId;

  return `
    <div class="action-bar">
      ${canEscalate ? `
        <button class="btn btn-outline btn-sm" style="color:var(--red);" onclick="app.escalateSession(${ticketId})">
          升级工单
        </button>
      ` : ''}
      ${canAccept ? `
        <button class="btn btn-primary btn-sm" onclick="app.acceptEscalation(${ticketId})">
          接管工单
        </button>
      ` : ''}
    </div>`;
}

export function renderEndServiceButton(ticketId) {
  return `
    <button class="btn btn-danger btn-sm" onclick="app.endService(${ticketId})" style="margin-left:8px;">
      结束服务
    </button>`;
}

function formatTime(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  } catch (e) { return ''; }
}
