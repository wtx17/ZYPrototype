const WS_URL_BASE = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host;

let agentWs = null;
let messageHandlers = {};
let _statusCallback = null;

export function onConnectionChange(fn) {
  _statusCallback = fn;
  if (fn) {
    fn(isConnected());
  }
}

export function connectAgentWs(sessionId) {
  if (agentWs && agentWs.readyState === WebSocket.OPEN) {
    return agentWs;
  }

  const url = `${WS_URL_BASE}/ws/agent?session_id=${encodeURIComponent(sessionId)}`;

  agentWs = new WebSocket(url);

  agentWs.onopen = () => {
    console.log('Agent WS connected');
    _statusCallback?.(true);
    if (messageHandlers.connected) messageHandlers.connected();
  };

  agentWs.onmessage = (event) => {
    const data = JSON.parse(event.data);
    const handler = messageHandlers[data.type];
    if (handler) {
      handler(data.payload);
    }
  };

  agentWs.onclose = () => {
    console.log('Agent WS disconnected');
    _statusCallback?.(false);
    if (messageHandlers.disconnected) messageHandlers.disconnected();
    agentWs = null;
  };

  agentWs.onerror = (err) => {
    console.error('Agent WS error', err);
    _statusCallback?.(false);
  };

  return agentWs;
}

let retryTimer = null;
let retrySessionId = null;

export function connectAgentWsWithRetry(sessionId, delay = 3000) {
  retrySessionId = sessionId;
  const ws = connectAgentWs(sessionId);

  if (!messageHandlers.disconnected) {
    setHandler('disconnected', () => {
      if (retrySessionId) {
        retryTimer = setTimeout(() => connectAgentWsWithRetry(retrySessionId, delay), delay);
      }
    });
  }

  return ws;
}

export function disconnectAgentWs() {
  retrySessionId = null;
  if (retryTimer) {
    clearTimeout(retryTimer);
    retryTimer = null;
  }
  if (agentWs) {
    agentWs.close();
    agentWs = null;
  }
}

export function setHandler(type, fn) {
  messageHandlers[type] = fn;
}

export function removeHandler(type) {
  delete messageHandlers[type];
}

export function clearAllHandlers() {
  messageHandlers = {};
}

export function sendMessage(data) {
  if (agentWs && agentWs.readyState === WebSocket.OPEN) {
    agentWs.send(JSON.stringify(data));
  }
}

export function isConnected() {
  return agentWs !== null && agentWs.readyState === WebSocket.OPEN;
}

export function getSessionId() {
  return sessionStorage.getItem('session_id') || null;
}
