# Trellis Skills 汉化大白话版（13 个 Codex 技能包）

这是一套给 **Codex（以及兼容 Codex skill 规范的 AI 编程工具）** 用的技能包。装好之后，AI 干活会自动按一套固定流程走：先想清楚再动手、写完代码先做质量检查、发布说明用人话写、收尾自动存档。还有一键安装脚本，下载后跑一条命令就装好。

## 这是干什么用的

简单说：**这是给 AI 立规矩的。**

平时你让 AI 改代码，它想怎么干就怎么干，改完直接扔给你。装了这套技能包之后，它会按固定流程干活：

| 序号 | 流程 | 大白话解释 |
|---|---|---|
| 1 | 开任务前先写方案 | 先把"要做什么、怎么验证"写清楚，你确认了才动手 |
| 2 | 写代码前先查规范 | 先看项目已有的规矩和代码习惯，不瞎写 |
| 3 | 写完代码必须做质量检查 | 自动跑代码检查和测试，不过关不算完成 |
| 4 | 发版说明必须写大白话 | GitHub Release 说明必须让不懂编程的人也看得懂 |
| 5 | 收尾自动存档 | 任务记录、改动说明自动存进项目档案，以后能翻旧账 |

## 有什么用

| 序号 | 好处 |
|---|---|
| 1 | AI 不会想到哪改到哪，每个任务都有方案、有检查、有记录 |
| 2 | 代码改完自动过质量检查，改坏了能当场发现 |
| 3 | 发版说明不再是"feat: xxx"这种黑话，你和用户都能看懂这次更新了什么 |
| 4 | 每个任务的方案、改动、测试结果都留在项目里，隔几个月也能查 |
| 5 | 技能装一次全局生效，所有项目都能用，不用每个项目单独装 |

## 包含哪 12 个技能

| 序号 | 技能名 | 干什么用 |
|---|---|---|
| 1 | trellis-start | 开新任务：帮你把需求整理成任务文档 |
| 2 | trellis-brainstorm | 想方案：需求不清楚时，先帮你把思路理清楚 |
| 3 | trellis-before-dev | 写码前准备：动手前先查项目规范和现有代码 |
| 4 | trellis-check | 质量检查：改完代码做全面检查（含"发版说明和 README 必须大白话"检查） |
| 5 | trellis-update-spec | 更新规范：把这次学到的东西写进项目规范 |
| 6 | trellis-continue | 继续任务：接着上次的任务继续干 |
| 7 | trellis-finish-work | 收尾：存档任务、记录改动（含"发版说明大白话"规则） |
| 8 | trellis-break-loop | 跳出死循环：AI 反复改不好时换思路 |
| 9 | trellis-channel | 多模型协作：多个 AI 工具之间传话 |
| 10 | trellis-meta | 元信息：查看和管理这套流程本身 |
| 11 | trellis-session-insight | 会话记录：查看以前干过什么 |
| 12 | trellis-spec-bootstrap | 规范起步：新项目第一次生成项目规范 |
| 13 | trellis-setup | 一键初始化：检查环境、装档案柜，新项目第一次用先喊它 |

## 怎么下载

### 方法一：用 git 下载（推荐）

打开命令行，输入：

```bash
git clone https://github.com/ssqaq/trellis-skills.git
```

### 方法二：下载压缩包

1. 打开本仓库页面
2. 点绿色的 **Code** 按钮
3. 点 **Download ZIP**
4. 解压到任意文件夹

## 怎么安装（Windows）

### 方法一：一键安装（推荐）

下载仓库后，在仓库文件夹里打开命令行，跑一条命令：

```powershell
pwsh -File install.ps1
```

它会自动完成：把 13 个技能装到你的全局目录 + 检查 Trellis 主程序装没装 + 告诉你下一步做什么。

### 方法二：手动安装

### 第 1 步：把技能复制到全局目录

把下载下来的 `skills` 文件夹里的 **13 个 trellis 开头的文件夹**，全部复制到：

```text
C:\Users\你的用户名\.agents\skills\
```

如果这个文件夹不存在，自己建一个就行。复制完长这样：

```text
C:\Users\你的用户名\.agents\skills\
├── trellis-before-dev\
├── trellis-brainstorm\
├── trellis-break-loop\
├── trellis-channel\
├── trellis-check\
├── trellis-continue\
├── trellis-finish-work\
├── trellis-meta\
├── trellis-session-insight\
├── trellis-spec-bootstrap\
├── trellis-setup\
├── trellis-start\
└── trellis-update-spec\
```

装好后，**你所有的 Codex 会话都能自动识别这 13 个技能**，不管在哪个项目里。

### 第 2 步：安装 Trellis 主程序

这套技能需要一个叫 Trellis 的工具配合（技能是"说明书"，Trellis 是"档案柜"）。在命令行输入：

```bash
npm install -g @mindfoldhq/trellis
```

装完验证一下：

```bash
trellis --version
```

能显示版本号就说明装好了。

### 第 3 步：给你的项目建档案柜（每个项目只做一次）

进入你的项目文件夹，跟 AI 说一句"初始化 Trellis"（会自动触发 trellis-setup 技能），或者自己跑一次初始化：

```bash
cd 你的项目文件夹
trellis init
```

跑完后项目里会多一个 `.trellis` 文件夹，这就是这个项目自己的档案柜（任务记录、项目规范都存这里）。**每个项目只需要跑一次，以后不用再跑。**

## 怎么使用

安装完成后，你不需要输入任何特殊命令。**正常跟 AI 说话就行**，技能会自动被触发：

| 序号 | 你说什么 | 会发生什么 |
|---|---|---|
| 1 | "帮我加一个登录功能" | AI 会先用 trellis-start 帮你建任务、写方案，你确认后才动手 |
| 2 | （AI 改完代码后） | 自动触发 trellis-check 做质量检查 |
| 3 | "这次改动发到 GitHub 上" | AI 会按 trellis-finish-work 的规矩，把 Release 说明写成大白话 |
| 4 | "收尾吧" | 自动存档任务、记录这次改动 |
| 5 | "初始化 Trellis" | 自动触发 trellis-setup，检查环境并给项目建档案柜 |

### 想手动指定用某个技能也可以

在对话里用 `$技能名` 的写法：

```text
$trellis-check 帮我检查一下刚才的改动
```

```text
$trellis-brainstorm 我想给软件加个导出功能，帮我理理思路
```

## 两个要点（必读）

| 序号 | 要点 | 说明 |
|---|---|---|
| 1 | 技能是全局的，档案柜是每个项目一份 | 技能（说明书）装一次所有项目共用；`.trellis` 文件夹（档案柜）每个项目自己一个，互不干扰。所以每个新项目第一次用之前，记得跑一次 `trellis init` |
| 2 | 质量检查在正常任务流程里自动触发 | 只要你是按任务流程干活（不是让 AI 随手改几行），收尾时质量检查会自动跑。但如果你绕过任务流程直接改代码，检查就不会触发 |

## 卸载方法

### 方法一：一键卸载（推荐）

在仓库文件夹里跑一条命令：

```powershell
pwsh -File uninstall.ps1
```

它会自动删掉全局目录里 13 个 trellis 开头的技能文件夹。项目里的 `.trellis` 档案柜不会被碰。

### 方法二：手动卸载

把 `C:\Users\你的用户名\.agents\skills\` 下 13 个 trellis 开头的文件夹删掉即可。项目里的 `.trellis` 文件夹删不删都行，删了就是丢掉这个项目的任务档案。

## 常见问题

| 序号 | 问题 | 答案 |
|---|---|---|
| 1 | 装完技能，AI 说找不到 | 技能列表是会话开始时加载的。**关掉当前 Codex 会话，重新开一个**，新会话就能识别了 |
| 2 | `trellis init` 报"命令不存在" | 先装主程序：`npm install -g @mindfoldhq/trellis`，装完跑 `trellis --version` 验证，再回去 init |
| 3 | 新项目第一次用，要不要再装一遍技能 | 不用。技能是全局的，装一次就行。新项目只需要跑一次 `trellis init` 建档案柜（或直接说"初始化 Trellis"） |
| 4 | 没建 Trellis 任务，AI 直接改了几行代码，质量检查会跑吗 | 不会。质量检查是在任务流程里触发的。想让检查必跑，就走正常流程：先说"开一个任务" |
| 5 | 在跟 Trellis 无关的项目里，技能被误触发了 | 直接跟 AI 说"这个项目不用 Trellis"即可。或者用一键卸载删掉全局技能，只在需要的项目里保留 |
| 6 | 升级后旧项目要不要重新 init | 不要。升级只覆盖技能（说明书），项目的 `.trellis` 档案柜（任务记录、规范）不受影响 |
| 7 | macOS / Linux 能用吗 | 技能文件夹本身通用，复制到 `~/.agents/skills/` 即可。但 README 里的安装脚本和路径写的是 Windows 版，其他系统需手动安装 |

## 怎么升级（老用户看这里）

| 序号 | 步骤 | 操作 |
|---|---|---|
| 1 | 下载最新版 | 重新 git clone 或下载 ZIP（或在自己克隆的文件夹里跑 git pull） |
| 2 | 重跑安装脚本 | 在仓库文件夹里再跑一次 `pwsh -File install.ps1`，它会自动覆盖旧版技能 |
| 3 | 完成 | 不需要重新 `trellis init`，项目档案柜不受影响 |

想看每版改了什么，去仓库根目录的 [CHANGELOG.md](CHANGELOG.md)（更新记录）。

## 怎么查自己装的是哪个版本

| 序号 | 方法 |
|---|---|
| 1 | 看安装时的输出：安装脚本最后一行会显示 `Installed version: x.x.x` |
| 2 | 对比 GitHub 仓库最新的 [VERSION 文件](VERSION)：把仓库里的 VERSION 和你装的时候记下的版本号一比就知道落了几版 |

## 版本说明

| 序号 | 内容 |
|---|---|
| 1 | 基于 Trellis 0.7.0-beta.3 的 13 个技能 |
| 2 | 新增：GitHub Release 发版说明和 README 必须写大白话的规则（在 trellis-check 和 trellis-finish-work 两个技能里） |
| 3 | 新增：一键安装脚本 install.ps1 |
| 4 | 新增：trellis-setup 总管技能，一句"初始化 Trellis"完成环境检查和项目初始化 |
