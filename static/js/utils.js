export function toast(msg, type = 'success') {
  const element = document.createElement('div');
  element.className = `toast ${type}`;
  element.textContent = msg;
  document.body.appendChild(element);
  setTimeout(() => element.remove(), 3000);
}

export function escHtml(value) {
  if (value === null || value === undefined) {
    return '';
  }
  const element = document.createElement('div');
  element.textContent = String(value);
  return element.innerHTML;
}

export function stripHtml(value) {
  if (!value) {
    return '';
  }
  const element = document.createElement('div');
  element.innerHTML = String(value);
  return element.textContent || element.innerText || '';
}

export function formatDate(value) {
  if (!value) {
    return '-';
  }
  return new Date(value).toLocaleString();
}

export function copyText(button) {
  navigator.clipboard.writeText(button.dataset.text).then(() => toast('已复制到剪贴板'));
}

export function showTextPreview(title, text) {
  window.alert(`${title}:\n${text}`);
}

export function formatDuration(start, end) {
  if (!start) return '-';
  const startDate = new Date(start);
  const endDate = end ? new Date(end) : new Date();
  const diffMs = endDate - startDate;
  if (diffMs < 0) return '-';
  const mins = Math.floor(diffMs / 60000);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);

  if (mins < 1) return '<1分钟';
  if (hours < 1) return `${mins}分钟`;
  if (days < 1) {
    const remMins = mins % 60;
    return remMins > 0 ? `${hours}小时${remMins}分` : `${hours}小时`;
  }
  const remHours = hours % 24;
  return remHours > 0 ? `${days}天${remHours}小时` : `${days}天`;
}
