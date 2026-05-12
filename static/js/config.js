export const roleTabs = {
  cs: ['sessions', 'desensitize', 'wiki-browser'],
  rd: ['escalations', 'wiki-browser'],
  doc: ['wiki-browser', 'review-knowledge'],
  manager: ['dashboard', 'all-tickets'],
};

export const roleLabels = {
  cs: '客服',
  rd: '二线研发',
  doc: '文档团队',
  manager: '管理层',
};

export const roleUsernames = {
  cs: '小陈',
  rd: '王工',
  doc: '李婷',
  manager: '林总',
};

export const statusLabels = {
  pending: '待处理',
  ai_processing: 'AI处理中',
  resolved: '已解决',
  escalated: '已升级',
  closed: '已关闭',
};

export const tabLabels = {
  sessions: '在线服务',
  tickets: '工单管理 (P7)',
  desensitize: '脱敏工具 (P6)',
  escalations: '升级工单',
  'review-knowledge': '审核知识',
  'wiki-browser': '浏览知识库',
  dashboard: '仪表盘 (P8)',
  'all-tickets': '全部工单',
};
