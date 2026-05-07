import { api } from './api.js';
import { roleUsernames } from './config.js';
import { resetState, state } from './state.js';

let renderApp = () => {};

export function setRenderApp(handler) {
  renderApp = handler;
}

export async function login(role) {
  const username = roleUsernames[role];
  const data = await api('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role, username }),
  });

  state.role = data.role;
  state.username = data.username;
  state.currentTab = null;
  state.chatHistory = [];
  state.conversationId = null;
  renderApp();
}

export async function logout() {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'same-origin',
    });
  } catch (error) {
    // Ignore logout network failures and clear local state anyway.
  }

  resetState();
  renderApp();
}

export async function handleUnauthorized() {
  resetState();
  renderApp();
}

export async function checkAuth() {
  try {
    const data = await api('/api/auth/me');
    if (data.authenticated) {
      state.role = data.role;
      state.username = data.username;
    }
  } catch (error) {
    // Ignore auth probe failures and fall back to login screen.
  }

  renderApp();
}

export function switchRole(event) {
  const role = event.target.value;
  if (role) {
    void login(role);
  }
}
