#!/usr/bin/env bash
# 顾问专用沙箱（Linux，bubblewrap）：家目录和项目全部只读，只有 agy 自己的状态和缓存可写。
# 遮住：常见凭据目录、Claude 原始会话记录（Gemini 只看过滤后的快照）、其他 Gemini 对话，
#       以及 config.json 里 "mask" 列出的路径（gem 通过 GEM_MASK 传进来）。
# skill 目录本身再露出来（只读）：装在 ~/.claude/skills 下时，它会跟着 ~/.claude 一起被遮住。
# 用法: agy_consult.sh <对话名> [agy 参数...]      由 gem 调用，不手动调。
# 自检: gem selftest                             不调 agy，只验证挂载
# 没有 bwrap 时可设 GEM_SANDBOX=off：不进沙箱，agy 只放行读文件类工具（不能跑命令）。
set -euo pipefail
H="$HOME"
SKILL="$(cd "$(dirname "$0")" && pwd)"
PROJECT="${GEM_PROJECT:?由 gem 调用}"
GEM="${GEM_ROOT:-$PROJECT/.gemini-consult}"

# 默认遮住的凭据：存在才遮。目录用空 tmpfs 盖住，文件用 /dev/null 盖住。
MASKS=("$H/.ssh" "$H/.claude" "$H/.codex" "$H/.config/gh" "$H/.aws" "$H/.config/gcloud"
       "$H/.azure" "$H/.kube" "$H/.docker" "$H/.gnupg" "$H/.netrc" "$H/.git-credentials"
       "$H/.npmrc" "$H/.pypirc")
IFS=: read -r -a EXTRA <<< "${GEM_MASK:-}"
MASKS+=(${EXTRA[@]+"${EXTRA[@]}"})

mask_args() {
  local p
  for p in "${MASKS[@]}"; do
    [[ -z "$p" ]] && continue
    if [[ -d "$p" ]]; then echo "--tmpfs"; echo "$p"
    elif [[ -e "$p" ]]; then echo "--ro-bind"; echo "/dev/null"; echo "$p"
    fi
  done
}

jail() {   # $1 = 对外露出的那个 in/ 目录，其余参数是要跑的命令
  local in="$1"; shift
  local rw=() m=()
  for d in "$H/.gemini" "$H/.cache"; do [[ -d "$d" ]] && rw+=(--bind "$d" "$d"); done
  mapfile -t m < <(mask_args)
  bwrap \
    --bind / / \
    --dev-bind /dev /dev \
    --proc /proc \
    --ro-bind "$H" "$H" \
    --ro-bind "$PROJECT" "$PROJECT" \
    ${rw[@]+"${rw[@]}"} \
    ${m[@]+"${m[@]}"} \
    --ro-bind "$SKILL" "$SKILL" \
    --tmpfs "$GEM" \
    --ro-bind "$in" "$in" \
    --chdir "$PROJECT" \
    --die-with-parent \
    -- "$@"
}

if [[ "${1:-}" == "--selftest" ]]; then
  command -v bwrap >/dev/null || { echo "没有 bwrap（bubblewrap），沙箱用不了"; exit 1; }
  mkdir -p "$GEM/convs/_selftest/in" "$GEM/convs/_other/out"
  echo "能看到" > "$GEM/convs/_selftest/in/probe.md"
  echo "不该看到" > "$GEM/convs/_other/out/001.md"
  IN="$GEM/convs/_selftest/in"
  ok() { echo "  ✓ $1"; }; bad() { echo "  ✗ $1"; FAIL=1; }; FAIL=0
  leaks() {   # 被遮住的目录里还露着什么（通往 skill 目录的那条路不算）
    jail "$IN" find "$1" -mindepth 1 2>/dev/null | while read -r f; do
      [[ "$f" == "$SKILL" || "$f" == "$SKILL"/* || "$SKILL" == "$f"/* ]] || echo "$f"
    done
  }
  jail "$IN" test -r "$PROJECT"                                  && ok "能读项目"          || bad "读不到项目"
  jail "$IN" sh -c "echo x > '$PROJECT/.gem_probe'" 2>/dev/null   && bad "项目能写"          || ok "项目写不进"
  jail "$IN" sh -c "echo x > '$H/.gem_probe'" 2>/dev/null         && bad "家目录能写"        || ok "家目录写不进"
  mapfile -t m < <(mask_args)
  for ((i = 0; i < ${#m[@]}; i++)); do
    case "${m[$i]}" in
      --tmpfs)   p="${m[$((i+1))]}"; [[ -z "$(leaks "$p")" ]] && ok "遮住 $p" || bad "$p 露着" ;;
      --ro-bind) p="${m[$((i+2))]}"; [[ -z "$(jail "$IN" cat "$p" 2>/dev/null)" ]] && ok "遮住 $p" || bad "$p 露着" ;;
    esac
  done
  jail "$IN" test -r "$IN/probe.md"                             && ok "本对话的 in/ 能读"  || bad "本对话的 in/ 读不到"
  jail "$IN" test -e "$GEM/convs/_other/out/001.md"             && bad "别的对话露着"      || ok "别的对话遮住"
  jail "$IN" sh -c "echo x > '$IN/w'" 2>/dev/null               && bad "in/ 能写"          || ok "in/ 只读"
  [[ -d "$H/.gemini" ]] && { jail "$IN" sh -c "touch '$H/.gemini/.gem_probe' && rm '$H/.gemini/.gem_probe'" && ok "~/.gemini 可写" || bad "~/.gemini 写不进"; }
  jail "$IN" test -r "$SKILL/gemini.md"                         && ok "能读 gemini.md"     || bad "读不到 gemini.md"
  rm -rf "$GEM/convs/_selftest" "$GEM/convs/_other"
  rm -f "$PROJECT/.gem_probe" "$H/.gem_probe" 2>/dev/null || true
  [[ $FAIL == 0 ]] && echo "自检通过" || { echo "自检没过"; exit 1; }
  exit 0
fi

CONV="$1"; shift
IN="$GEM/convs/$CONV/in"
[[ -d "$IN" ]] || { echo "没有对话 $CONV" >&2; exit 2; }
if [[ "${GEM_SANDBOX:-on}" == "off" ]]; then
  echo "警告：没有沙箱，agy 只放行读文件类工具" >&2
  cd "$PROJECT" && exec agy --settings "$SKILL/agy_settings_nosandbox.json" "$@"
fi
command -v bwrap >/dev/null || { echo "没有 bwrap（bubblewrap）。装上它，或设 GEM_SANDBOX=off" >&2; exit 3; }
jail "$IN" agy --settings "$SKILL/agy_settings.json" "$@"
