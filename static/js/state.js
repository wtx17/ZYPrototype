export const state = {
  role: null,
  username: null,
  currentTab: null,
  conversationId: null,
  chatHistory: [],

  // Session/workspace state
  activeSessionId: null,
  activeSession: null,
  sessionMessages: [],
  aiPanelVisible: false,
  aiQueryResult: null,
};

export function resetChatState() {
  state.chatHistory = [];
  state.conversationId = null;
}

export function resetSessionState() {
  state.activeSessionId = null;
  state.activeSession = null;
  state.sessionMessages = [];
  state.aiPanelVisible = false;
  state.aiQueryResult = null;
}

export function resetState() {
  state.role = null;
  state.username = null;
  state.currentTab = null;
  resetChatState();
  resetSessionState();
}
