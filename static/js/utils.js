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
