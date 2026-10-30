#!/bin/sh
# D-Reach 凭据查找链 —— 技能与密钥来源解耦（接口不碰内容）
# 用法:  EXA=$(sh "$SKILL_DIR/scripts/load_key.sh" EXA_API_KEY https://dashboard.exa.ai) || exit 1
# 查找顺序: 1) $NAME 环境变量  2) ~/.config/agents/env  3) <skill目录>/.env  4) ~/.secrets/console_cookies.txt
# （第 4 项是 cookie-getter 推送到面板后落的盘，登录态 cookie 走这条路）
# 找不到 → stderr 输出四要素引导(变量名/申请URL/写入位置/降级说明), exit 1
# 安全: 本脚本永不 echo key 值; 调用方也不得 echo/cat 结果
NAME="$1"
URL="$2"
SKILL_DIR="${SKILL_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"

val=""
# 1) 环境变量
eval "val=\${$NAME:-}"
# 2)+3) env 文件候选
if [ -z "$val" ]; then
  for f in "$HOME/.config/agents/env" "$SKILL_DIR/.env" "$HOME/.secrets/console_cookies.txt"; do
    [ -f "$f" ] || continue
    v=$(sed -n "s/^${NAME}=//p" "$f" | head -1 | tr -d '\r\n"')
    if [ -n "$v" ]; then val="$v"; break; fi
  done
fi

if [ -n "$val" ]; then
  printf '%s' "$val"
  exit 0
fi

cat >&2 <<EOF
[load_key] 缺少 $NAME
  1. 申请: ${URL:-见 SKILL.md 路由表对应服务}（多数有免费额度）
  2. 写入(推荐): echo "$NAME=你的key" >> ~/.config/agents/env  (该文件权限设为 600)
     或写入本技能目录 .env（已在 .gitignore 内，永不提交）
  3. 不想配: 本次自动降级到路由表备选通道（免费但结果可能差些）
EOF
exit 1
