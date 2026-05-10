export const roleTabs = {
  cs: ['sessions', 'desensitize'],
  rd: ['escalations', 'submit-solution', 'release-notes', 'rd-knowledge'],
  doc: ['submit-knowledge', 'review-knowledge'],
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
  escalations: '升级工单 (P4/P5)',
  'submit-solution': '提交方案 (P2)',
  'release-notes': '发布 Release Notes (P3)',
  'rd-knowledge': 'D2 知识库',
  'submit-knowledge': '提交知识 (P6)',
  'review-knowledge': '审核知识 (P6)',
  dashboard: '仪表盘 (P8)',
  'all-tickets': '全部工单',
};
