#!/usr/bin/env python3
"""从 Claude 会话记录（jsonl）里截一段给 Gemini 读，并去掉顾问往来。

  snapshot.py <会话.jsonl> [--from-byte B] [-o 输出.md]     截快照
  snapshot.py <会话.jsonl> --count [--from-byte B]           只数新开了几轮

按字节位置接着读：只读 B 之后新写的部分，不把整份记录读进内存。
lab 上一份会话记录有两亿多字节，大头是 api-request 之类的记账行，它们的 type 写在最前面，
看开头就能跳过，不用解析。

去掉的东西：gem/agy 命令、读写 gemini/ 目录的工具调用（连同结果）、调度员发来的 [gem] 消息、
app 自己的记账工具（任务清单、收尾框、ToolSearch）。思考块在会话记录里是空的，不处理。
读文件的结果不放进快照，只写路径：Gemini 自己能读那个文件。
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

GEM_CMD = re.compile(r"(^|[\s;&|(/])(gem|agy|agy_consult\.sh|agy_ro\.sh)(\s|$)")
# 顾问往来的路径：默认的 gemini/ 和 skill 目录，加上实际在用的状态目录和本脚本所在目录（试运行时在别处）
_extra = [p for p in (os.environ.get("GEM_ROOT"), str(Path(__file__).resolve().parent)) if p]
GEM_PATH = re.compile(r"/gemini(/|$)|/gemini-consult/|" + "|".join(re.escape(p) for p in _extra))
SECRET = re.compile(
    r"sk-ant-[\w-]{10,}|ghp_\w{20,}|gho_\w{20,}|AIza[\w-]{30,}|xox[bp]-[\w-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
)
REMINDER = re.compile(r"<system-reminder>[\s\S]*?</system-reminder>")


# ---------- 读 ----------

def entries(path, start=0):
    """从字节 start 开始，逐条给出 (读到的字节位置, 用户或 Claude 的记录)。
    最后一行如果还没写完（没有换行），不读，位置停在它前面。"""
    with open(path, "rb") as f:
        f.seek(start)
        pos = start
        for line in f:
            if not line.endswith(b"\n"):
                break
            pos += len(line)
            if line.startswith(b'{"type":'):      # 记账行：type 在最前面，用户和 Claude 的行不是
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("type") in ("user", "assistant") and not o.get("isSidechain"):
                yield pos, o
        yield pos, None                          # 收尾：报告读到哪了


def blocks(o):
    c = o.get("message", {}).get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return [b for b in c if isinstance(b, dict)] if isinstance(c, list) else []


# ---------- 判断 ----------

def is_advisor_message(text):
    """调度员发来的 [gem] 消息，以及 app 转来的调度会话汇报。"""
    return "[gem]" in text or "gem-broker" in text


def skip_tool(b):
    name, inp = b.get("name", ""), b.get("input") or {}
    if name.startswith("mcp__ccd_") or name == "ToolSearch":
        return True
    if GEM_PATH.search(json.dumps(inp, ensure_ascii=False)):   # 任何提到顾问目录的调用，比如开调度会话
        return True
    if name == "Bash":
        cmd = inp.get("command", "")
        return bool(GEM_CMD.search(cmd) or GEM_PATH.search(cmd))
    if name in ("Read", "Edit", "Write", "NotebookEdit"):
        return bool(GEM_PATH.search(inp.get("file_path", "")))
    if name in ("Grep", "Glob"):
        return bool(GEM_PATH.search(inp.get("path", "") or ""))
    if name == "SendMessage":
        return "[gem]" in json.dumps(inp, ensure_ascii=False)
    if name == "Skill":
        return inp.get("skill") == "gemini-consult"
    return False


ORIGIN_LABEL = {"human": "用户", "task_notification": "后台通知", "peer": "子代理或别的会话",
                "sdk": "系统消息"}


# ---------- 数轮次 ----------

def count(path, start=0):
    """数主会话新开了几轮：用户发的几轮，后台通知等别的几轮。调度员的 [gem] 消息不算。"""
    human = other = 0
    end = start
    for end, o in entries(path, start):
        if o is None:
            break
        if o["type"] == "user" and o.get("turnOrigin"):
            if is_advisor_message(" ".join(b.get("text", "") for b in blocks(o))):
                continue
            if o["turnOrigin"] == "human":
                human += 1
            else:
                other += 1
    return {"to_byte": end, "human": human, "other": other}


# ---------- 截快照 ----------

def clip(s, n):
    s = s.strip()
    if len(s) <= n:
        return s
    return s[: n * 2 // 3] + f"\n…（中间省略 {len(s) - n} 字）…\n" + s[-n // 3:]


def result_text(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(x.get("text", f"[{x.get('type')}]") for x in c if isinstance(x, dict))
    return str(c)


def render(path, start=0, max_result=1200):
    out, dropped, reads = [], set(), set()
    ts0 = ts1 = None
    end = start
    for end, o in entries(path, start):
        if o is None:
            break
        ts = o.get("timestamp", "")[:16].replace("T", " ")
        ts0, ts1 = ts0 or ts, ts
        for b in blocks(o):
            k = b.get("type")
            if k == "text" and o["type"] == "assistant":
                if b["text"].strip():
                    out.append(f"\n## Claude · {ts}\n{b['text'].strip()}")
            elif k == "text":
                if not is_advisor_message(b["text"]):
                    t = REMINDER.sub("", b["text"]).strip()
                    if t:
                        who = ORIGIN_LABEL.get(o.get("turnOrigin"), "用户")
                        out.append(f"\n## {who} · {ts}\n{clip(t, 4000)}")
            elif k == "tool_use":
                if skip_tool(b):
                    dropped.add(b["id"])
                    continue
                inp = b.get("input") or {}
                if b.get("name") == "Read":
                    reads.add(b["id"])
                    out.append(f"【读文件】{inp.get('file_path')}（要看内容请自己读）")
                    continue
                key = (inp.get("command") or inp.get("file_path") or inp.get("pattern")
                       or inp.get("description") or json.dumps(inp, ensure_ascii=False))
                out.append(f"【工具 {b.get('name')}】{clip(str(key), 600)}")
            elif k == "tool_result":
                tid = b.get("tool_use_id")
                if tid not in dropped and tid not in reads:
                    out.append("【结果】" + clip(result_text(b.get("content")), max_result))
    header = (f"<!-- snapshot path={path} bytes={start}-{end} time={ts0}~{ts1} -->\n"
              f"# Claude 会话快照（{ts0} ~ {ts1}）\n")
    text = SECRET.sub("[已遮]", header + "\n".join(out) + "\n")
    return text, {"to_byte": end, "dropped_tools": len(dropped), "chars": len(text)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl")
    ap.add_argument("--from-byte", type=int, default=0)
    ap.add_argument("--count", action="store_true")
    ap.add_argument("-o", "--out")
    ap.add_argument("--max-result", type=int, default=1200)
    a = ap.parse_args()
    if a.count:
        print(json.dumps(count(a.jsonl, a.from_byte)))
        return
    text, info = render(a.jsonl, a.from_byte, a.max_result)
    if a.out:
        Path(a.out).write_text(text)
    else:
        sys.stdout.write(text)
    print(json.dumps(info), file=sys.stderr)


if __name__ == "__main__":
    main()
