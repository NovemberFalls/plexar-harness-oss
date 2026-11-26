---
description: "dsh Web 客户端的环境栏：右侧边栏右边一列可收起的栏，显示当前会话的工作区、git 分支、上下文用量和后台任务。"
kind: "package-reference"
---

# @deepseek-ai/dsh-client-ui-environment

[English](README.md) | 中文

## 概述

会话标题栏里的**环境**按钮会在窗口最右侧、右侧边栏的右边打开一条 280px 的栏。栏里显示当前会话的情况：工作区名称和文件夹、该文件夹的 git 分支、上下文窗口已用多少，以及会话正在运行的后台任务和已完成任务的数量。显示还是隐藏这条栏，会按浏览器记住。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [进一步探索](#further-exploration)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

按会话标题栏里的**环境**显示或隐藏这条栏；栏标题行的关闭按钮也能隐藏它。各节自上而下为：**工作区**（总是显示；路径过长时省略中间部分，悬停显示完整路径）、**分支**、**上下文**、**后台任务**，没有内容的节不显示。未选中会话时，栏里只显示一行提示。窗口太窄、放下这条栏后会话区达不到最小宽度时，栏会让开，但仍记得用户要它显示；右侧边栏全屏时它也会让开。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

浏览器半边用这条栏占据框架的 `envbar` 插槽（由 `ui-layout` 声明；只有在被占用时，框架才在 `rightbar` 列右边给它一条真实的网格轨道），栏的主体是 `session-maybe` 子插槽 `envbar.session`。标题栏开关注册到 `conversation.session.header.actions`，调用 `ctx.layout.toggleEnvbar()`；显示状态同时记在本地快照里（供开关的 `aria-pressed` 使用）和 `localStorage` 的 `plexar.envbar.shown` 下（`'1'`/`'0'`，每次读写都包在 try/catch 里，缺省视为隐藏），启动时应用。工作区数据来自可选的 `workspaces` 服务，后台任务来自可选的 `jobs` 服务（只在栏显示时订阅任务列表），上下文用量来自 `contextPressure` 投影，经 token-meter 的 `contextOccupancy` 折算——与输入框下方的用量环是同一份计算。

Host 半边是挂在 `ctx.remote.environmentRail` 上的 `TypertRemoteService`。它唯一的方法 `branch(sessionId)` 在 Host 自己的 `workspaceRegistry` 里找到该会话的工作区（调用方从不提供路径），用 `execFile` 在那里运行 `git rev-parse --abbrev-ref HEAD`（不经 shell，2 秒超时，隐藏窗口），返回 `{ branch }`；出错、不在仓库内或处于游离 HEAD 时为 null。栏在会话切换时、以及显示期间每 30 秒询问一次，隐藏时从不询问。

</details>

-----

<a id="further-exploration"></a>
## 进一步探索

- [ui-layout](../ui-layout/README.zh.md)——框架、它的 `envbar` 轨道和 `ctx.layout`。
- [ui-jobs](../ui-jobs/README.zh.md)——基于同一个 `jobs` 服务的标题栏任务列表。
- [ui-workspace](../ui-workspace/README.zh.md)——基于同一个 `workspaces` 服务的工作区浏览器。
- [token-meter](../../llm/token-meter/README.zh.md)——`contextPressure` 投影及其用量折算。

-----

<a id="model-experience"></a>
## 模型体验

无。本包是浏览器侧界面，外加一个供界面使用的 Host 读取；不注册任何面向模型的内容。

#### KV 缓存影响

无；本包既不组装也不发送任何模型请求。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

- **没有改动摘要和产出** — 当前会话最近一轮的改动摘要和已呈现的产出，并没有放在共享的客户端 store 里，所以栏里不设这两节，也不为此新建 Host 汇总。
- **分支靠定时刷新** — 栏显示期间每 30 秒重读一次分支，而不是在每轮结束后读。
- **运行时不变量：** 不发布配套内容。栏自己不持有任何关系：记住的选择只是浏览器偏好，显示的内容都来自其他服务。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者工作上下文——点击展开</summary>

无。

</details>
