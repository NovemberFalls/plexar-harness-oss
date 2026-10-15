/**
 * Locale bundles for the Plexar Features and Credits settings sections. Every
 * user-visible string in this package resolves through these dictionaries.
 */

/** Locale keys the Features section renders. */
export type FeaturesLocaleKey =
  | 'nav' | 'title' | 'intro' | 'empty' | 'loading' | 'unavailable'
  | 'settingUp'
  | 'feature.voiceInput.name' | 'feature.voiceInput.description'
  | 'feature.browserUse.name' | 'feature.browserUse.description'
  | 'feature.useMyChrome.name' | 'feature.useMyChrome.description'
  | 'feature.agentTeams.name' | 'feature.agentTeams.description'
  | 'feature.shell.name' | 'feature.shell.description'
  | 'feature.files.name' | 'feature.files.description'
  | 'feature.webSearch.name' | 'feature.webSearch.description'
  | 'feature.subagents.name' | 'feature.subagents.description'
  | 'feature.workflows.name' | 'feature.workflows.description'
  | 'feature.todos.name' | 'feature.todos.description'
  | 'feature.goals.name' | 'feature.goals.description'
  | 'feature.jobs.name' | 'feature.jobs.description'
  | 'feature.skills.name' | 'feature.skills.description'
  | 'group.coding' | 'group.web' | 'group.helpers' | 'group.planning' | 'group.background' | 'group.appearance' | 'group.input'
  | 'feature.aurora.name' | 'feature.aurora.description'
  | 'showDetails' | 'hideDetails'

/** Locale keys the sidebar update notice renders. */
export type UpdateLocaleKey =
  | 'available' | 'versions' | 'updateButton' | 'updating' | 'restartButton' | 'failed'

/** Locale keys the Models section renders. */
export type ModelsLocaleKey =
  | 'nav' | 'title' | 'intro' | 'unavailable'
  | 'group.chat' | 'group.classifiers'
  | 'servingPill' | 'notServingPill' | 'imagesTag' | 'contextTag' | 'classifierTag'

/** Locale keys the Account section renders. */
export type AccountLocaleKey =
  | 'nav' | 'title' | 'loading' | 'signedOut' | 'devKey'
  | 'signedInAs' | 'signOut' | 'confirmPrompt' | 'cancel'

/** Locale keys the Credits section renders. */
export type CreditsLocaleKey =
  | 'nav' | 'title' | 'thanksIntro' | 'thanksLink' | 'partsHeading'
  | 'part.cordis' | 'part.sensevoice' | 'part.playwright' | 'part.tauri'

/** English Features copy. */
export const featuresEn: Record<FeaturesLocaleKey, string> = {
  nav: 'Features',
  title: 'Features',
  intro: 'Turn Plexar features on or off. Open a feature for details.',
  empty: 'No optional features are available in this deployment.',
  loading: 'Loading features…',
  unavailable: 'Features are unavailable without a managed profile.',
  settingUp: 'Setting up…',
  'feature.voiceInput.name': 'Voice input',
  'feature.voiceInput.description': 'Adds a microphone beside Send. Speak, press Stop, and your words appear in the message box to edit before sending. Speech is transcribed on this computer by a small local model (about 240 MB, downloaded once); audio never leaves the machine.',
  'feature.browserUse.name': 'Browser',
  'feature.browserUse.description': 'Lets the agent open a real Chromium browser: visit pages, click, fill forms, take screenshots and read console output. Useful for testing web apps and checking what a page actually shows.',
  'feature.useMyChrome.name': 'Use my Chrome',
  'feature.useMyChrome.description': 'Lets the agent work in your own Chrome through the Plexar Browser Bridge extension. Off: it uses its own browser window.',
  'feature.agentTeams.name': 'Agent Teams',
  'feature.agentTeams.description': 'Experimental. Lets the agent start a small team of helper agents that share a task board and work on parts of a job in parallel. Uses more of the model and takes longer; best for large, splittable tasks.',
  'group.coding': 'Coding',
  'group.web': 'Web',
  'group.helpers': 'Helper agents',
  'group.planning': 'Planning',
  'group.background': 'Background work',
  'group.appearance': 'Appearance',
  'group.input': 'Input',
  'feature.aurora.name': 'Animated background',
  'feature.aurora.description': 'A soft, slowly breathing glow of northern-lights colour along the bottom of the window. It never covers text and pauses automatically when Windows asks for reduced motion. Remembered on this computer only.',
  'feature.shell.name': 'Terminal commands',
  'feature.shell.description': 'Lets the agent run commands in Bash (and PowerShell on Windows): builds, tests, git, package managers. In Ask mode every command waits for your approval; Full access runs them without asking.',
  'feature.files.name': 'Files',
  'feature.files.description': 'Lets the agent read, search, create and edit files in the workspace. Edits show as green and red diffs. Turning this off leaves the agent able to talk but not to change your code.',
  'feature.webSearch.name': 'Web search and fetch',
  'feature.webSearch.description': 'Lets the agent search the web and read pages by URL, for documentation, error messages and current information.',
  'feature.subagents.name': 'Helper agents',
  'feature.subagents.description': 'Lets the agent hand a self-contained piece of work, like a code search or a review, to a helper agent that reports back. Keeps the main conversation focused on long tasks.',
  'feature.workflows.name': 'Workflows',
  'feature.workflows.description': 'Lets the agent write a short script that runs several helper agents in order or in parallel, for repeatable multi-step jobs.',
  'feature.todos.name': 'To-do list',
  'feature.todos.description': 'Lets the agent keep a visible checklist of the steps in a task and tick them off as it works.',
  'feature.goals.name': 'Goals',
  'feature.goals.description': 'Lets you set a goal the agent keeps working toward over several rounds, checking its own progress until the goal is met or it needs you.',
  'feature.jobs.name': 'Background jobs',
  'feature.jobs.description': 'Lets the agent start long-running commands, like dev servers or watch builds, in the background and check on them later.',
  'feature.skills.name': 'Skills',
  'feature.skills.description': 'Lets the agent load skill guides from your workspace and profile: step-by-step instructions for specific jobs, used only when relevant.',
  showDetails: 'Show details',
  hideDetails: 'Hide details',
}

/** Simplified Chinese Features copy. */
export const featuresZh: Record<FeaturesLocaleKey, string> = {
  nav: '功能',
  title: '功能',
  intro: '打开或关闭 Plexar 功能。展开功能可查看详情。',
  empty: '此部署没有可用的可选功能。',
  loading: '正在加载功能…',
  unavailable: '没有受管配置文件时无法使用功能。',
  settingUp: '正在设置…',
  'feature.voiceInput.name': '语音输入',
  'feature.voiceInput.description': '在发送按钮旁添加麦克风。说话后点击停止，文字会出现在输入框中供编辑后发送。语音由本机上的小型本地模型转写（约 240 MB，只下载一次），音频不会离开本机。',
  'feature.browserUse.name': '浏览器',
  'feature.browserUse.description': '允许代理打开真实的 Chromium 浏览器：访问页面、点击、填写表单、截图并读取控制台输出。适合测试网页应用，查看页面实际显示的内容。',
  'feature.useMyChrome.name': '使用我的 Chrome',
  'feature.useMyChrome.description': '让代理通过 Plexar Browser Bridge 扩展在你自己的 Chrome 中工作。关闭时，它使用自己的浏览器窗口。',
  'feature.agentTeams.name': '代理团队',
  'feature.agentTeams.description': '实验功能。允许代理启动一个小型助手团队，共享任务看板，并行处理任务的不同部分。会消耗更多模型用量、耗时更长，适合大型、可拆分的任务。',
  'group.coding': '编程',
  'group.web': '网络',
  'group.helpers': '助手代理',
  'group.planning': '规划',
  'group.background': '后台工作',
  'group.appearance': '外观',
  'group.input': '输入',
  'feature.aurora.name': '动态背景',
  'feature.aurora.description': '窗口底部柔和、缓慢呼吸的极光色光晕。不会遮挡文字；当 Windows 要求减少动态效果时会自动暂停。仅在本机记住。',
  'feature.shell.name': '终端命令',
  'feature.shell.description': '允许代理在 Bash（Windows 上也可用 PowerShell）中运行命令：构建、测试、git、包管理器。在询问模式下每条命令都需你批准；完全访问模式下直接运行。',
  'feature.files.name': '文件',
  'feature.files.description': '允许代理读取、搜索、创建和编辑工作区中的文件。修改以绿色和红色差异显示。关闭后代理只能对话，无法修改代码。',
  'feature.webSearch.name': '网页搜索与抓取',
  'feature.webSearch.description': '允许代理搜索网络并按网址读取页面，用于查阅文档、错误信息和最新资料。',
  'feature.subagents.name': '助手代理',
  'feature.subagents.description': '允许代理把独立的工作（如代码搜索或审查）交给助手代理完成并汇报，使长任务中的主对话保持专注。',
  'feature.workflows.name': '工作流',
  'feature.workflows.description': '允许代理编写简短脚本，按顺序或并行运行多个助手代理，处理可重复的多步骤任务。',
  'feature.todos.name': '待办清单',
  'feature.todos.description': '允许代理维护可见的任务步骤清单，并在工作时逐项勾选。',
  'feature.goals.name': '目标',
  'feature.goals.description': '允许你设定一个目标，代理会多轮持续推进并自查进度，直到目标完成或需要你介入。',
  'feature.jobs.name': '后台任务',
  'feature.jobs.description': '允许代理在后台启动长时间运行的命令（如开发服务器或监视构建），稍后再查看。',
  'feature.skills.name': '技能',
  'feature.skills.description': '允许代理加载工作区和配置文件中的技能指南：针对特定工作的分步说明，仅在相关时使用。',
  showDetails: '显示详情',
  hideDetails: '隐藏详情',
}

/** English sidebar update notice copy. */
export const updateEn: Record<UpdateLocaleKey, string> = {
  available: 'Update available',
  versions: 'v{current} → v{latest}',
  updateButton: 'Update',
  updating: 'Updating…',
  restartButton: 'Restart to finish',
  failed: 'Update failed',
}

/** Simplified Chinese sidebar update notice copy. */
export const updateZh: Record<UpdateLocaleKey, string> = {
  available: '有可用更新',
  versions: 'v{current} → v{latest}',
  updateButton: '更新',
  updating: '正在更新…',
  restartButton: '重启以完成',
  failed: '更新失败',
}

/** English Models copy. */
export const modelsEn: Record<ModelsLocaleKey, string> = {
  nav: 'Plexar models',
  title: 'Models',
  intro: "The models your Plexar account can use. Pick a chat model in the composer; classifiers run inside Plexar and can't be chosen as a chat model.",
  unavailable: "Model details aren't available right now. Sign in, or check your connection to Plexar.",
  'group.chat': 'Chat models',
  'group.classifiers': 'Classifiers',
  servingPill: 'Serving',
  notServingPill: 'Not serving',
  imagesTag: 'Images',
  contextTag: '{n}K context',
  classifierTag: 'Classifier',
}

/** Simplified Chinese Models copy. */
export const modelsZh: Record<ModelsLocaleKey, string> = {
  nav: 'Plexar 模型',
  title: '模型',
  intro: '你的 Plexar 账户可使用的模型。在输入框中选择对话模型；分类模型在 Plexar 内部运行，不能作为对话模型选择。',
  unavailable: '暂时无法获取模型详情。请登录，或检查与 Plexar 的连接。',
  'group.chat': '对话模型',
  'group.classifiers': '分类模型',
  servingPill: '服务中',
  notServingPill: '未服务',
  imagesTag: '支持图片',
  contextTag: '{n}K 上下文',
  classifierTag: '分类模型',
}

/** English Account copy. */
export const accountEn: Record<AccountLocaleKey, string> = {
  nav: 'Account',
  title: 'Account',
  loading: 'Loading account…',
  signedOut: "You're signed out.",
  devKey: 'Signed in with a developer key',
  signedInAs: 'Signed in as {email}',
  signOut: 'Sign out',
  confirmPrompt: 'Sign out of Plexar on this computer?',
  cancel: 'Cancel',
}

/** Simplified Chinese Account copy. */
export const accountZh: Record<AccountLocaleKey, string> = {
  nav: '账户',
  title: '账户',
  loading: '正在加载账户…',
  signedOut: '你已退出登录。',
  devKey: '已使用开发者密钥登录',
  signedInAs: '当前登录：{email}',
  signOut: '退出登录',
  confirmPrompt: '要在本机退出 Plexar 登录吗？',
  cancel: '取消',
}

/** English Credits copy. */
export const creditsEn: Record<CreditsLocaleKey, string> = {
  nav: 'Credits',
  title: 'Credits',
  thanksIntro: 'Plexar Harness is built on DeepSeek Harness, open source and MIT licensed. Thank you to DeepSeek for open-sourcing it:',
  thanksLink: 'github.com/deepseek-ai',
  partsHeading: 'Plexar also ships these open-source parts:',
  'part.cordis': 'Cordis — the plugin framework the harness composes on',
  'part.sensevoice': 'SenseVoice — on-device speech recognition',
  'part.playwright': 'Playwright — browser automation',
  'part.tauri': 'Tauri — the desktop app shell',
}

/** Simplified Chinese Credits copy. */
export const creditsZh: Record<CreditsLocaleKey, string> = {
  nav: '鸣谢',
  title: '鸣谢',
  thanksIntro: 'Plexar Harness 构建于开源且 MIT 许可的 DeepSeek Harness 之上。感谢 DeepSeek 将其开源：',
  thanksLink: 'github.com/deepseek-ai',
  partsHeading: 'Plexar 还集成了以下开源组件：',
  'part.cordis': 'Cordis — harness 所构建的插件框架',
  'part.sensevoice': 'SenseVoice — 本地语音识别',
  'part.playwright': 'Playwright — 浏览器自动化',
  'part.tauri': 'Tauri — 桌面应用外壳',
}
