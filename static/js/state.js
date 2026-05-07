export const state = {
  role: null,
  username: null,
  currentTab: null,
  conversationId: null,
  chatHistory: [],
};

export function resetChatState() {
  state.chatHistory = [];
  state.conversationId = null;
}

export function resetState() {
  state.role = null;
  state.username = null;
  state.currentTab = null;
  resetChatState();
}
