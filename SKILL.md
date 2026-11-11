---
name: gemini-consult
description: 找 Gemini（Antigravity CLI）当外部顾问时用：开一个调度会话，尽早发帖说打算做什么，等它的回答，回应采纳与否。打算做计划、换方向、下结论，或要跑贵的、不可逆的任务之前用。
---

# Gemini 顾问

一个 Sonnet 调度会话替你管 Gemini：开新对话还是续旧对话、给它看到哪一刻、什么时候把回答递给你。你只做三件事：发帖、读回答、回应。

下面的 `$GEM` 指这个 skill 目录里的 `gem`，用完整路径调用。

## 开工（每个会话一次）

1. **登记自己。** 用 `mcp__ccd_session_mgmt__get_session` 查 `self`，拿到会话 ID（`local_` 开头），然后带上你的 scratchpad 路径（系统提示里写着）：

   ```bash
   $GEM main --scratchpad <你的 scratchpad 路径> --session <会话ID>
   ```

   会话记录的文件名是 scratchpad 路径里那段 UUID，不是会话 ID，gem 会自己认出来。

2. **开调度会话。** `$GEM board` 第二行如果写着"还没有调度员"，就用 `mcp__ccd_session__start_session` 开一个，参数：
   - `initiation`: `"user_asked"`，`context`: `"fresh"`，`use_worktree`: `false`
   - `model`: 一个 Sonnet 模型（如 `"claude-sonnet-5-5"`），`name`: `"gem-broker"`，`title`: `"Gemini 调度员"`
   - `prompt`：

     ```
     你是 Gemini 调度员。先读 <这个 skill 目录>/broker.md，按它做。GEM=<这个 skill 目录>/gem。
     先跑 $GEM board 确认主会话已登记，再在后台起 $GEM watch（Bash 的 run_in_background），
     有事件就处理，处理完再起一个。每处理一个事件，用一两句话写下你的决定和理由。
     ```

   - `background`：一两句话说清这个项目在做什么，再加一句：`主会话用 Gemini 当外部顾问；调度员负责什么时候问 Gemini、问哪个对话、什么时候把回答递回主会话。gem 管状态，调度员管判断。`

   开好后登记它：`$GEM broker <它的会话 ID>`。

调度员每结束一轮，app 都会把它的汇报转给你（"The session "Gemini 调度员" … finished a turn"）。那是它的流水账，不是 `[gem]` 消息：第一次收到时确认它起来了就行，之后不用回应、不在正文里提，直接结束这一轮。

## 发帖：尽早说

有了想法就发，不要等到动手前一刻。准备脚本和数据的时间，正好够 Gemini 想。

```bash
$GEM post "打算做什么；为什么；预期看到什么；大概什么时候动手"
$GEM post --dir -f 帖子.md     # 方向性的：改目标、新计划或 spec、把结果解读成结论、放弃一条线
```

- 写清预期，最好是数字或方向。结果出来才对得上。
- 修正自己先前的预期或结论，也算方向性，加 `--dir`。
- 用你自己的话，写短。命令会打印帖子编号，比如 `P0007`。

## 收回答

调度员会发来以 `[gem]` 开头的消息，里面有回答编号（如 `q-cache#002`）和文件路径。读原文，不要只看调度员附的那一句。

## 回应：每条回答都要回

```bash
$GEM reply q-cache#002 采纳 "一句话理由"
$GEM reply q-cache#002 不采纳 "差异在噪声内，先不改"
$GEM reply q-cache#002 暂缓 "等对照实验跑完再定"
```

这是 Gemini 唯一能看到的你对它的反应，理由要具体，不写客套。

## 需要等的时候

两种情况要先拿到回答：

- 不可逆或花钱多的一步之前：长时间的计算任务、上云、发布。
- 给用户下结论之前。等的是**承载这个结论的最新帖子**，不是更早的帖子。

等就放后台，别在前台空等：

```bash
$GEM wait P0007 --long      # 用 Bash 的 run_in_background 跑；回答到了会叫醒你
```

这段时间做别的。实在没别的可做，就告诉用户在等哪个帖子，然后结束这一轮。

回答也可能由调度员用 `[gem]` 消息先递到，两条路哪条先到都行。

## 几条规矩

- 找 Gemini 一律走 `gem`，不直接调 `agy`。
- 正文里不讨论 Gemini 的看法，也不写"等等 Gemini"。这些会进会话记录，Gemini 下一轮会读到，两边就互相带偏了。推理用你自己的话写。
- 给用户总结时，用到了 Gemini 的意见，标一句来源。
