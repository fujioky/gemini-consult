# gemini-consult

Claude Code skill：让 Gemini（Antigravity CLI `agy`）给 Claude 当外部顾问，由一个 Sonnet 调度会话异步调度。

```
 用户 ──► Claude 主会话 ──gem post──► 帖子板 ◄──watch── Sonnet 调度会话
              ▲   │                                   │
              │   └─gem reply（采纳/不采纳/暂缓）──────┤ open / say（带会话快照）
              │                                       ▼
              └────────[gem] 消息（回答路径）──── Gemini 对话（只读沙箱里读项目）
```

- 主会话有打算就 `gem post` 尽早说，然后接着干活，不等。
- 调度会话决定交给哪个 Gemini 对话（续旧的还是新开）、给它看会话记录的哪一段、什么时候把回答递回去。
- Gemini 在只读沙箱里自己读项目文件、看过滤后的会话快照，按固定格式给意见。
- 主会话对每条回答 `gem reply`，这条回应会带回给 Gemini。

## 要求

- Linux + bubblewrap（`bwrap`）。没有的话可设 `GEM_SANDBOX=off`：不进沙箱，Gemini 只能读文件、不能跑命令。
- Antigravity CLI `agy`，已登录。
- Python 3.9+（只用标准库）。
- Claude Code 桌面版：调度会话用 `start_session` 开，回答用 `SendMessage` 递。

## 安装

```bash
# 项目级：装在哪个项目，就给哪个项目用
git clone <这个仓库> <项目>/.claude/skills/gemini-consult
# 或者用户级：项目目录取当前目录
git clone <这个仓库> ~/.claude/skills/gemini-consult
```

然后：

1. 把 `<项目>/.gemini-consult/` 加进 `.gitignore`（状态目录）。
2. 可选：`<项目>/.gemini-consult/config.json`，写模型、并发上限、额外要遮住的路径，格式见 `config.example.json`。
3. 可选：`<项目>/.gemini-consult/brief.md`，给 Gemini 的项目背景。没有的话它会自己去读 README、CLAUDE.md 或 AGENTS.md。
4. 跑一次 `<skill 目录>/gem selftest`，检查沙箱。

## 用法

在主会话里说"用 gemini-consult 问 Gemini"，或者在 CLAUDE.md / 记忆里写一条"计划、方案、结论都先问 Gemini（gemini-consult skill）"。主会话会按 `SKILL.md` 开工：登记自己、开调度会话，之后发帖、读回答、回应。

## 文件

| 文件 | 给谁 | 作用 |
|---|---|---|
| `SKILL.md` | 主会话 | 开工、发帖、回应、等待 |
| `broker.md` | 调度会话 | 能决定什么、不能做什么、续还是新开、事件循环 |
| `gemini.md` | Gemini | 角色、回答格式、来源标注 |
| `gem` | 都用 | 唯一入口：帖子、对话、快照、递送记录都在这里 |
| `snapshot.py` | gem | 从 Claude 会话记录里截一段给 Gemini，去掉顾问往来 |
| `agy_consult.sh` | gem | 只读沙箱，遮住凭据和 Claude 原始会话记录 |

## 设计取舍

- **时限不按钟点。** gem 只记录 Gemini 读过的位置之后，主会话又发生了多少（用户发了几轮、后台通知几轮、新帖几个、过了多久）。催不催、等多久，由调度员判断。训练时后台通知刷屏、Claude 没动，就不该催 Gemini。
- **一个决策一个对话。** 方向性的问题新开对话，保持独立视角；细节续在 `follow` 里；建议的结果回到提建议的那个对话。
- **防带偏。** 快照里去掉 `gem` 命令、调度员消息和顾问目录的读写；主会话正文里不讨论 Gemini 的看法。从 Claude 流回 Gemini 的只有"采纳 / 不采纳 / 暂缓 + 一句理由"。
- **快照够快。** 按字节位置接着读、先按开头跳过记账行再解析。两亿字节的会话记录从头截约 0.3 秒，增量截零点几秒。读文件的结果不放进快照，只给路径，Gemini 自己去读。
- **催促可靠。** 不用 `timeout` 包 agy（它会把 agy 放进自己的进程组，停不干净）。实测：一轮被中途停掉后，它在下一轮还记得之前读过的文件。
- **不在终端起 `claude`。** 那按 API 计费，不走订阅额度。

## 已知限制

- 依赖 Claude Code 会话记录（jsonl）的格式，比如 `turnOrigin` 字段。版本变了可能要改 `snapshot.py`。
- Gemini 对话 ID 靠比对 `~/.gemini/antigravity-cli/conversations/` 里新出现的 `.db` 认出来。
- 只在一台 Linux 机器上实测过。
