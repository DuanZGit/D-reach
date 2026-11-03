#!/usr/bin/env bash
# d-reach 冒烟测试 —— 改通道后跑一遍，5 个关键断言全过才算没炸。
#
# 用法：bash scripts/smoke.sh [-v]
#   -v  打印每轮 fanout 的完整输出（默认只打断言结果）
#
# 设计原则（学 Morphic 的 evals）：断言跑在**真实输出**上，不复制实现逻辑来对照。
# 复制一份 norm_url 去测副本，测的是副本不是真的 —— 那种测试看着绿，改坏了照样绿。
#
# 依赖网络（3 个断言要真跑 fanout）。单轮约 6-10 秒，总时长约 30 秒。
set -u
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VERBOSE=0
[ "${1:-}" = "-v" ] && VERBOSE=1

PASS=0
FAIL=0
FAILED_NAMES=""

ok()   { PASS=$((PASS+1)); printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); FAILED_NAMES="$FAILED_NAMES\n    - $1"; printf '  \033[31m✗\033[0m %s\n' "$1"; }

# 断言：输出里必须出现某段文字
has() {
  name="$1"; out="$2"; pat="$3"
  if printf '%s' "$out" | grep -qF -- "$pat"; then ok "$name"; else bad "$name（缺少「$pat」）"; fi
}
# 断言：输出里必须**不**出现某段文字
hasnt() {
  name="$1"; out="$2"; pat="$3"
  if printf '%s' "$out" | grep -qF -- "$pat"; then bad "$name（不该出现「$pat」）"; else ok "$name"; fi
}

run() {  # $@ = fanout 参数；stdout 落到 $OUT，退出码落 $RC
  OUT=$(bash "$DIR/fanout.sh" "$@" 2>/dev/null); RC=$?
  [ "$VERBOSE" = "1" ] && printf '%s\n' "$OUT"
  return 0
}

printf '\n\033[1md-reach 冒烟测试\033[0m\n\n'

# ---------- 1. 默认档能跑通 ----------
printf '[1/5] 默认档跑通\n'
run "杭州 西湖 门票 2026"
[ "$RC" = "0" ] && ok "退出码 0" || bad "退出码 $RC"
has "有标题行" "$OUT" "## fanout「"
has "有汇总段" "$OUT" "**汇总**"

# ---------- 2. 跨源合并段存在且带源计数 ----------
printf '\n[2/5] 跨源合并段\n'
has "有合并段标题" "$OUT" "### 🔀 跨源共识"
if printf '%s' "$OUT" | grep -qE '源（[a-z]+#[0-9]+'; then
  ok "条目带源名次标注"
else
  bad "条目缺源名次标注（期望形如 3 源（serper#1 · tavily#2））"
fi

# ---------- 3. 合并段的 URL 已归一化（不带跟踪参数） ----------
printf '\n[3/5] 合并段 URL 归一化\n'
MERGE=$(printf '%s' "$OUT" | sed -n '/### 🔀 跨源共识/,/^### /p' | head -40)
hasnt "合并段无 utm_source" "$MERGE" "utm_source="
hasnt "合并段无 rankingId" "$MERGE" "rankingId="

# ---------- 4. 超长 query 不崩 ----------
printf '\n[4/5] 超长 query（300 字）\n'
# 用 python 按字符截断：cut -c 会切断多字节中文，产出非法 UTF-8（surrogates）反而测不出真问题
LONG=$(python3 -c 'print(("如何提高分布式系统的可观测性和故障定位效率 " * 15)[:300])')
run "$LONG"
[ "$RC" = "0" ] && ok "退出码 0" || bad "退出码 $RC"
has "仍输出汇总段" "$OUT" "**汇总**"

# ---------- 5. 健康挂起：未到期跳过、已到期放行 ----------
printf '\n[5/5] 健康挂起与到期恢复\n'
HTMP=$(mktemp)
trap 'rm -f "$HTMP"' EXIT
python3 - "$HTMP" <<'PY'
import json, sys
from datetime import datetime, timezone, timedelta
now = datetime.now(timezone.utc)
json.dump({
    # 未到期 → 本轮必须跳过
    "hn": {"streak_fail": 3, "suspend_until": (now + timedelta(hours=1)).isoformat(timespec="seconds"), "suspend_secs": 600},
    # 已到期 → 本轮必须放行
    "jj": {"streak_fail": 5, "suspend_until": (now - timedelta(hours=1)).isoformat(timespec="seconds"), "suspend_secs": 7200},
}, open(sys.argv[1], "w", encoding="utf-8"))
PY
OUT=$(D_REACH_HEALTH="$HTMP" bash "$DIR/fanout.sh" "rust tokio" 2>/dev/null); RC=$?
[ "$VERBOSE" = "1" ] && printf '%s\n' "$OUT"
has "未到期通道被跳过并给出重试时间" "$OUT" "挂起中，"
hasnt "已到期通道没被跳过" "$OUT" "掘金（中文技术长尾） —— 连续失败"

# ---------- 结果 ----------
printf '\n'
if [ "$FAIL" = "0" ]; then
  printf '\033[32m全部通过：%d 项\033[0m\n\n' "$PASS"
  exit 0
else
  printf '\033[31m失败 %d 项\033[0m（通过 %d 项）:%b\n\n' "$FAIL" "$PASS" "$FAILED_NAMES"
  exit 1
fi
