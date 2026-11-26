/** Locale bundles for the environment rail. */

/** Dictionary namespace owned by this plugin. */
export const NS = 'environment'

/** Locale keys the rail renders. */
export type EnvironmentKey =
  | 'title' | 'toggle' | 'close' | 'empty'
  | 'workspace' | 'workspaceNone' | 'branch' | 'context' | 'contextUsed'
  | 'tasks' | 'tasksFinished'

/** English copy. */
export const en: Record<EnvironmentKey, string> = {
  title: 'Environment',
  toggle: 'Environment',
  close: 'Close environment',
  empty: 'Select a session to see its environment.',
  workspace: 'Workspace',
  workspaceNone: 'No workspace',
  branch: 'Branch',
  context: 'Context',
  contextUsed: '{percent}% used',
  tasks: 'Background tasks',
  tasksFinished: '{count} finished',
}

/** Simplified Chinese copy. */
export const zh: Record<EnvironmentKey, string> = {
  title: '环境',
  toggle: '环境',
  close: '关闭环境',
  empty: '选择一个会话以查看其环境。',
  workspace: '工作区',
  workspaceNone: '无工作区',
  branch: '分支',
  context: '上下文',
  contextUsed: '已用 {percent}%',
  tasks: '后台任务',
  tasksFinished: '已完成 {count} 个',
}
