import { toast } from './utils.js';

let unauthorizedHandler = null;

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

function getSessionId() {
  return sessionStorage.getItem('session_id') || '';
}

export async function api(path, opts = {}) {
  const sid = getSessionId();
  const sep = path.includes('?') ? '&' : '?';
  const url = sid ? `${path}${sep}session_id=${encodeURIComponent(sid)}` : path;

  const response = await fetch(url, {
    credentials: 'same-origin',
    ...opts,
  });

  if (response.status === 401) {
    if (unauthorizedHandler) {
      await unauthorizedHandler();
    }
    throw new Error('未登录');
  }

  if (response.status === 403) {
    toast('权限不足', 'error');
    throw new Error('权限不足');
  }

  // Handle non-JSON responses gracefully
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch (e) {
    if (!response.ok) {
      throw new Error(`服务器错误 (${response.status}): ${text.substring(0, 200)}`);
    }
    throw new Error('响应解析失败: ' + text.substring(0, 200));
  }
}
