#!/usr/bin/env bash
# fanout.sh —— d-reach 并行铺开器（「全加全扩」落地件）
#
# 一条命令并发运行启用清单里的通道；--deep 追加 enabledForDeep 清单里的 deep 通道。
# 轮 1 发现一律走它，别一条一条串行试：
#   实测 3 路串行 2.95s vs 并行 1.30s —— 铺开耗时 ≈ 最慢一路，与路数基本无关。
#
# 用法:
#   fanout.sh "<query>"              # 运行 enabledByDefault 正向清单
#   fanout.sh "<query>" --deep       # 追加 enabledForDeep 清单
#   fanout.sh "<query>" --n 8        # 每路最多列几条（默认 5）
#   fanout.sh "<query>" --on hn,oalex # 本轮白名单
#   fanout.sh --list                 # 列出通道与默认启用状态
# 默认清单：~/.agent-reach/fanout-defaults.json；D_REACH_DEFAULTS_FILE 可覆盖路径。
#
# 记账: 免费免 Key 通道不记账；deep 下 LangSearch/Exa 调用前自动
#       `quota.py use`，退出码 1（越免费线）→ 自动跳过该路并在输出里标注，
#       不拖死其他路。百度千帆由它自己的计数器记账，这里不双扣。
#       tf（TinyFish）需 TINYFISH_API_KEY 但 search $0.00/次 → 只 gate key 不记账。
#
# 通道命名（--on 用）:
#   se hn jj zhihu zhihuall oalex crossref segfault fcdev qianfan tf xhs bili | deep: langsearch exa fcres zhihuhot zhida
#
# 已退役通道（别往回加）：
#   · 博客园 zzk.cnblogs.com —— 302→zzkx 后返回 5.7KB 壳页、0 结果
#   · V2EX search —— /search?q= 302→/go/search，返回节点帖子列表、与 query 无关（假结果）
#   中文社区长尾现在靠 掘金 + SegmentFault + 知乎。

set -u

DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
QUOTA="$DIR/quota.py"
DEFAULTS_FILE="${D_REACH_DEFAULTS_FILE:-$HOME/.agent-reach/fanout-defaults.json}"
SKILLS="$HOME/.agents/skills"; [ -d "$SKILLS" ] || SKILLS=/var/minis/skills
# 千帆配套技能目录名有两版：历史/本机 baiduaisearchwithquota，viking 分发版按 slug 落成
# baidu-ai-search。两个都探，先命中先用；都没有时 qianfan 标记未配置并跳过。
BAIDU=""
for _bd in "$SKILLS/baiduaisearchwithquota/scripts" "$SKILLS/baidu-ai-search/scripts"; do
  [ -f "$_bd/smart_search.py" ] && { BAIDU="$_bd"; break; }
done
[ -n "$BAIDU" ] || BAIDU="$SKILLS/baiduaisearchwithquota/scripts"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"

# ---------- 参数 ----------
Q=""; ENQ=""; DEEP=0; N=5; ON=""; DEFAULT_DISABLED=""; ON_SET=0; FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --deep) DEEP=1 ;;
    --n) shift; N="${1:-5}" ;;
    --on) shift; ON="${1:-}"; ON_SET=1 ;;
    --en) shift; ENQ="${1:-}" ;;   # 英文检索词：LLM 把中文 query 译好后传进来，英文通道用它
    --force) FORCE=1 ;;   # 忽略健康状态，强制跑（调试/复检用）
    --list) python3 - "$0" "$DEFAULTS_FILE" <<'PY'
import json, os, re, sys
src = open(sys.argv[1], encoding='utf-8').read()
body = src.split('SECTIONS = [', 1)[1].split('\n]', 1)[0]
entries = []
for entry in re.split(r'\n(?=    \()', body):
    m = re.match(r'\s*\("([a-z]+)",\s*"([^"]+)"', entry)
    if not m:
        continue
    d = re.search(r',\s*(True|False)\s*\)', entry)
    entries.append((m.group(1), bool(d and d.group(1) == 'True'), m.group(2)))
base_on = {key for key, deep, _ in entries if not deep}
deep_on = {key for key, deep, _ in entries if deep}
config_error = ""
try:
    if os.path.exists(sys.argv[2]):
        config = json.load(open(sys.argv[2], encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("配置顶层必须是对象")
        base, deep = config.get("enabledByDefault"), config.get("enabledForDeep")
        base_keys = {key for key, is_deep, _ in entries if not is_deep}
        deep_keys = {key for key, is_deep, _ in entries if is_deep}
        if not isinstance(base, list) or any(not isinstance(v, str) or v not in base_keys for v in base):
            raise ValueError("enabledByDefault 必须是有效 base 通道名数组")
        if not isinstance(deep, list) or any(not isinstance(v, str) or v not in deep_keys for v in deep):
            raise ValueError("enabledForDeep 必须是有效 deep 通道名数组")
        base_on, deep_on = set(base), set(deep)
except Exception as e:
    config_error = str(e)
    base_on, deep_on = set(), set()
for key, deep, name in entries:
    enabled = key in (deep_on if deep else base_on)
    state = (" [deep-on]" if enabled else " [not-deep]") if deep else (" [default-on]" if enabled else " [not-default]")
    print(f"  {key:10s} {'deep' if deep else 'base':4s}  {name}{state}")
if config_error:
    print(f"\n  默认启用配置有误：{config_error}")
print("\n  用法: fanout.sh \"<query>\" [--deep] [--n N] [--on key1,key2] [--en \"<english>\"]")
if config_error:
    sys.exit(2)
PY
      exit $? ;;
    -h|--help) sed -n '2,30p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'; exit 0 ;;
    --*) echo "[fanout] 未知参数：$1" >&2; exit 2 ;;
    *) [ -z "$Q" ] && Q="$1" ;;
  esac
  shift
done
ENQ="${ENQ:-$Q}"   # 没给 --en 时英文通道退回原 query，行为与改动前一致
if [ -z "$Q" ]; then echo "usage: fanout.sh \"<query>\" [--deep] [--n N] [--on chans] [--en \"<english>\"]"; exit 2; fi

BASE_CHANNELS="qianfan gh fcdev se hn jj zhihu zhihuall brave segfault oalex crossref tf serper tavily parallel youcom anysearch fcs wiki xhs bili"
DEEP_CHANNELS="zhihuhot zhida langsearch exa fcres"
KNOWN="$BASE_CHANNELS $DEEP_CHANNELS"
if [ -f "$DEFAULTS_FILE" ]; then
  DEFAULT_LISTS=$(python3 - "$DEFAULTS_FILE" "$BASE_CHANNELS" "$DEEP_CHANNELS" <<'PY'
import json, sys
path, base_arg, deep_arg = sys.argv[1:]
base_allowed, deep_allowed = set(base_arg.split()), set(deep_arg.split())
try:
    config = json.load(open(path, encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("配置顶层必须是对象")
    def read_list(key, allowed):
        values = config.get(key)
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise ValueError(f"{key} 必须是字符串数组")
        out = []
        for value in values:
            value = value.strip()
            if not value or "," in value:
                raise ValueError(f"{key} 每项必须是一个通道名")
            if value not in allowed:
                raise ValueError(f"{key} 含不适用的通道：{value}")
            if value not in out:
                out.append(value)
        return out
    base = read_list("enabledByDefault", base_allowed)
    deep = read_list("enabledForDeep", deep_allowed)
    print(",".join(base) + "|" + ",".join(deep))
except Exception as e:
    print(str(e), file=sys.stderr)
    raise SystemExit(2)
PY
  ) || { echo "[fanout] 默认启用配置无法读取或格式错误：$DEFAULTS_FILE" >&2; exit 2; }
  DEFAULT_LISTS_BASE="${DEFAULT_LISTS%%|*}"
  DEFAULT_LISTS_DEEP="${DEFAULT_LISTS#*|}"
else
  DEFAULT_LISTS_BASE="$BASE_CHANNELS"
  DEFAULT_LISTS_DEEP="$DEEP_CHANNELS"
fi

# --on 是本轮白名单；未知项剔除，若没有有效项则报错，避免意外跑全量。
if [ "$ON_SET" = "1" ]; then
  [ -n "$ON" ] || { echo "[fanout] --on 需要通道名" >&2; exit 2; }
  _bad=""; _good=""
  for _c in $(echo "$ON" | tr ',' ' '); do
    case " $KNOWN " in *" $_c "*) _good="$_good,$_c" ;; *) _bad="$_bad $_c" ;; esac
  done
  if [ -n "$_bad" ]; then
    echo "[fanout] 忽略未知 --on 通道:$_bad（可用: $KNOWN）" >&2
  fi
  ON="${_good#,}"
  [ -n "$ON" ] || { echo "[fanout] --on 没有匹配到可用通道" >&2; exit 2; }
fi
case "$N" in ''|*[!0-9]*) echo "[fanout] --n 必须是正整数" >&2; exit 2 ;; esac

# --on 里点名了 deep 专属通道 → 自动按 deep 跑（省得再写一遍 --deep）
case ",$ON," in
  *,langsearch,*|*,exa,*|*,fcres,*|*,zhihuhot,*|*,zhida,*) DEEP=1 ;;
esac

# Default runs use the positive allowlist; --on supplies a one-call override.
if [ "$ON_SET" != "1" ]; then
  _default_scope="$BASE_CHANNELS"
  _default_active="$DEFAULT_LISTS_BASE"
  if [ "$DEEP" = "1" ]; then
    _default_scope="$BASE_CHANNELS $DEEP_CHANNELS"
    _default_active="${DEFAULT_LISTS_BASE:+$DEFAULT_LISTS_BASE,}$DEFAULT_LISTS_DEEP"
  fi
  _defaults_disabled=""
  for _c in $(echo "$_default_scope" | tr ' ' '\n'); do
    case ",$_default_active," in
      *,"$_c",*) ;;
      *) _defaults_disabled="$_defaults_disabled,$_c" ;;
    esac
  done
  _defaults_disabled="${_defaults_disabled#,}"
  DEFAULT_DISABLED="$_defaults_disabled"
fi

# CJK 检测：Crossref / OpenAlex 对中文 query 相关性差（c2 实测：中文 query 返回「水质监测站 /
# 变电站 / 暖通」这类匹配到"配置/安装"字样的噪声）→ 中文 query 时自动跳过 Crossref
CJK=$(python3 -c 'import sys,re;print("1" if re.search(r"[\u4e00-\u9fff\u3400-\u4dbf]",sys.argv[1]) else "0")' "$Q" 2>/dev/null || echo 0)

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
HEALTH="${D_REACH_HEALTH:-$HOME/.agent-reach/channels.json}"
HEALTH_BAD=$(python3 - "$HEALTH" <<'PY' 2>/dev/null
import json, sys
from datetime import datetime, timezone
bad = []
try:
    h = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    h = {}
now = datetime.now(timezone.utc)
for k, v in h.items():
    if not isinstance(v, dict):
        continue
    until = v.get("suspend_until")
    if not until:
        continue                      # 没有到期时间 = 该放行一次，让 mark 补上退避
    # 挂起现在按「失败性质」写：确定性结论（要登录/限流）首败就挂，
    # 自愈类连败 3 次才挂 —— 所以这里只看有没有未到期的挂起，不再看连败次数。
    try:
        if datetime.fromisoformat(until) > now:
            bad.append(k)             # 还在挂起期内
    except Exception:
        continue                      # 时间戳坏了也放行，别把通道永久判死
print(" ".join(bad))
PY
)

# ---------- 记账闸门（两段式）----------
# gate 只 check 不扣；请求成功后才 charge 真扣（失败由调用方 refund 或干脆不扣）。
# 返回 0=可跑；1=越免费线/key 缺失（写好 skip 原因）
gate() {
  svc="$1"
  if [ "$svc" = "fcres" ]; then
    # Firecrawl Research Index 论文端点官方免费 → 只验 key，不记账（2026-10-26 定价页核实）
    FC_KEY=$(sh "$DIR/load_key.sh" FIRECRAWL_API_KEY https://firecrawl.dev 2>/dev/null) || { echo "key" > "$TMP/skip.$svc"; return 1; }
    return 0
  elif [ "$svc" = "exa" ]; then
    EXA_KEY=$(sh "$DIR/load_key.sh" EXA_API_KEY https://dashboard.exa.ai 2>/dev/null) || { echo "key" > "$TMP/skip.$svc"; return 1; }
  elif [ "$svc" = "langsearch" ]; then
    LS_KEY=$(sh "$DIR/load_key.sh" LANGSEARCH_API_KEY https://langsearch.com 2>/dev/null) || { echo "key" > "$TMP/skip.$svc"; return 1; }
  elif [ "$svc" = "tinyfish" ]; then
    TF_KEY=$(sh "$DIR/load_key.sh" TINYFISH_API_KEY https://agent.tinyfish.ai/api-keys 2>/dev/null) || { echo "key" > "$TMP/skip.tinyfish"; return 1; }
    return 0   # TinyFish search $0.00/次 → 不走 quota 记账
  elif [ "$svc" = "brightdata" ]; then
    BD_KEY=$(sh "$DIR/load_key.sh" BRIGHTDATA_APITOKEN https://brightdata.com 2>/dev/null) || { echo "key" > "$TMP/skip.$svc"; return 1; }
  elif [ "$svc" = "serper" ]; then
    # Serper = Google 结果，2,500 次一次性赠送（不是每月重置），之后 $1/1000
    # 实测 1.85s 回 5 条，比 BrightData 快 5 倍、便宜得多 → 本地生活/电商首选
    SP_KEY=$(sh "$DIR/load_key.sh" SERPER_API_KEY https://serper.dev 2>/dev/null) || { echo "key" > "$TMP/skip.$svc"; return 1; }
  elif [ "$svc" = "firecrawl_search" ]; then
    # Firecrawl /search 走同一个 key，消耗 firecrawl credits（1 credit/次左右）
    FC_KEY=$(sh "$DIR/load_key.sh" FIRECRAWL_API_KEY https://firecrawl.dev 2>/dev/null) || { echo "key" > "$TMP/skip.$svc"; return 1; }
    svc="firecrawl"
  elif [ "$svc" = "wiki" ]; then
    return 0   # Wikipedia REST API 完全免费无限量，不验 key 不记账
  fi
  python3 "$QUOTA" check "$svc" >/dev/null 2>&1; _qrc=$?
  # 0=正常，2=已过裕度线（仍可跑）；1=越免费线 → 跳过
  if [ "$_qrc" = "1" ]; then
    echo "quota" > "$TMP/skip.$svc"; return 1
  fi
  return 0
}

# 成功后真扣额度（失败不扣：宁少记不多记）
charge() {
  python3 "$QUOTA" use "$1" >/dev/null 2>&1 || true
}
want() {
  local channel="$1"
  if [ "$ON_SET" = "1" ]; then
    case ",$ON," in *",$channel,"*) ;; *) return 1 ;; esac
  fi
  case " $DEEP_CHANNELS " in *" $channel "*) [ "$DEEP" = "1" ] || return 1 ;; esac
  case ",$DEFAULT_DISABLED," in *",$channel,"*) return 1 ;; esac
  return 0
}

# ---------- 免费免 Key 通道 ----------
f_gh() {     # GitHub 仓库搜索（免 key，10 次/分钟）
  # GitHub 只认英文且整句是 AND 匹配：「Home Assistant 3D floorplan dashboard card github」
  # 整句传过去 total_count=0。所以抽 ASCII 词、剔掉 github/the/for 这类噪声、取前 4 个。
  GQ=$(echo "$ENQ" | grep -oE '[A-Za-z0-9][A-Za-z0-9._+-]*' \
       | grep -viE '^(github|repo|repository|the|a|an|of|for|and|to|in|on|with|how|what|best|ui|ux|api|app|web|ai|ml|ios|os)$' \
       | head -4 | tr '\n' ' ')
  # 抽不出英文词不是失败（中文 query 很正常）——写 skip 而不是空结果，
  # 否则每轮都会显示「GitHub：0 命中」并计入「1 路 0 命中」，看着像通道坏了。
  [ -z "$GQ" ] && { echo "no-english" > "$TMP/skip.gh"; return; }
  curl -s --max-time 12 -G "https://api.github.com/search/repositories" \
    -H "Accept: application/vnd.github+json" \
    --data-urlencode "q=$GQ" --data-urlencode "sort=stars" \
    --data-urlencode "order=desc" --data-urlencode "per_page=5" \
    -o "$TMP/gh.json" -w '%{http_code}' > "$TMP/gh.http" 2>/dev/null
}

# 登录态社交通道按平台使用独立冷却；冷却期内跳过，减少连续请求触发风控。
social_gate() {   # $1=平台 $2=冷却秒数；0=放行，1=冷却中（stdout 给剩余分钟）
  python3 - "$HOME/.agent-reach/social-last.json" "$1" "$2" <<'PY'
import json, os, sys, time
f, p, cd = sys.argv[1], sys.argv[2], int(sys.argv[3])
try:
    d = json.load(open(f))
except Exception:
    d = {}
left = cd - (time.time() - d.get(p, 0))
if left > 0:
    print(int(left // 60) + 1)
    sys.exit(1)
d[p] = int(time.time())
os.makedirs(os.path.dirname(f), exist_ok=True)
json.dump(d, open(f, "w"))
PY
}

run_command_with_timeout() {
  local seconds="$1" output="$2" error="$3"
  shift 3
  python3 -c '
import subprocess, sys
seconds, output, error = float(sys.argv[1]), sys.argv[2], sys.argv[3]
with open(output, "wb") as out, open(error, "wb") as err:
    try:
        result = subprocess.run(sys.argv[4:], stdout=out, stderr=err, timeout=seconds)
    except subprocess.TimeoutExpired:
        sys.exit(124)
sys.exit(result.returncode)
' "$seconds" "$output" "$error" "$@"
}

f_xhs() {    # 国内版小红书（需 xhs CLI 登录态；冷却 2 分钟）
  local left rc
  command -v xhs >/dev/null 2>&1 || {
    echo "not-configured" > "$TMP/skip.xhs"
    echo "未安装可选依赖 xhs CLI，国内版 XHS 路线已跳过。" > "$TMP/xhs.txt"
    return 0
  }
  left=$(social_gate xhs 120) || { echo "cooldown:$left" > "$TMP/skip.xhs"; return 0; }
  if timeout 22 xhs search "$Q" --json > "$TMP/xhs.json" 2> "$TMP/xhs.err"; then
    rc=0
  else
    rc=$?
  fi
  if grep -qi 'verification_required\|captcha' "$TMP/xhs.json" "$TMP/xhs.err" 2>/dev/null; then
    echo captcha > "$TMP/skip.xhs"
    rm -f "$TMP/xhs.json" "$TMP/xhs.err"
    return 0
  fi
  if [ "$rc" != "0" ]; then
    echo err > "$TMP/skip.xhs"
    if [ "$rc" = "124" ]; then
      echo "国内版 XHS 搜索超时（22 秒）。" > "$TMP/xhs.txt"
    else
      echo "国内版 XHS 搜索失败（退出码 $rc）。" > "$TMP/xhs.txt"
    fi
  fi
  [ -s "$TMP/xhs.json" ] || rm -f "$TMP/xhs.json"
}

f_bili() {   # B 站视频搜索（需登录态；冷却 90 秒）
  local left
  left=$(social_gate bili 90) || { echo "cooldown:$left" > "$TMP/skip.bili"; return; }
  # B 站搜索是多词 AND：「智能家居 值得买 评测」0 条、「智能家居」3 条。
  # 中文 query 没空格，`set -- $Q` 会切出「研究下」这种动词当首词，搜出来全是
  # 无关视频（实测「研究下 家庭平面图 有什么好方案」→ 捞出「研究下政策力度」）。
  # 所以先把口语前缀剥掉再截断。截断必须按字符不能用 cut -c（那是按字节，
  # 中文会被切出半个字变成乱码）。
  BQ=$(printf '%s' "$Q" | python3 -c "import sys,re; s=re.sub(r'^(研究下|研究一下|研究|看看|看一下|看下|帮我|帮忙|帮忙看|查一下|查下|搜一下|搜下|找一下|找下|请问|想知道|有没有|有什么|什么|怎么|如何|能不能)\\s*','',sys.stdin.read().strip()); print(s[:20] or s)")
  timeout 22 bilibili video search --keyword "$BQ" --num 6 --json > "$TMP/bili.json" 2>/dev/null \
    || { rm -f "$TMP/bili.json"; return; }
  case "$(python3 -c "import json;print(json.load(open('$TMP/bili.json')).get('result',{}).get('count',0))" 2>/dev/null)" in
    0) BQ2=$(printf '%s' "$BQ" | python3 -c "import sys; print(sys.stdin.read().strip()[:8])")
       timeout 15 bilibili video search --keyword "$BQ2" --num 6 --json > "$TMP/bili.json" 2>/dev/null \
         || rm -f "$TMP/bili.json" ;;
  esac
}

f_se() {     # StackExchange 排障
  # 中文 query（调用方没给 --en）打 SO 恒 0 命中：q 是全词 AND，中文词组在 SO 上
  # 几乎无索引。实测 8 天里 23 轮中文 query 送去 se，全部 0 命中 → 直接跳过省 15s。
  if [ "$CJK" = "1" ] && [ "$ENQ" = "$Q" ]; then
    echo "cjk" > "$TMP/skip.se"
    return 0
  fi
  # q 是全词 AND 匹配：长句/长中文会 0 命中 → 只取前 5 个词
  # shellcheck disable=SC2086
  set -- $ENQ
  SEQ="${1:-} ${2:-} ${3:-} ${4:-} ${5:-}"
  curl -s --compressed --max-time 15 -G "https://api.stackexchange.com/2.3/search/advanced" \
    --data-urlencode "order=desc" --data-urlencode "sort=relevance" \
    --data-urlencode "q=$SEQ" --data-urlencode "site=stackoverflow" \
    --data-urlencode "pagesize=5" -o "$TMP/se.json" -w '%{http_code}' > "$TMP/se.http" 2>/dev/null
}
f_hn() {     # HN 深技术讨论
  # 同 f_se：HN 只认英文，中文 query 恒 0 命中（实测 8 天 6 次空转）
  if [ "$CJK" = "1" ] && [ "$ENQ" = "$Q" ]; then
    echo "cjk" > "$TMP/skip.hn"
    return 0
  fi
  curl -s --max-time 12 -G "https://hn.algolia.com/api/v1/search" \
    --data-urlencode "query=$ENQ" --data-urlencode "hitsPerPage=5" -o "$TMP/hn.json" -w '%{http_code}' > "$TMP/hn.http" 2>/dev/null
}
f_jj() {     # 掘金 中文技术长尾
  curl -s --max-time 12 -H 'Content-Type: application/json' -X POST \
    "https://api.juejin.cn/search_api/v1/search" \
    -d "$(python3 -c 'import json,sys;print(json.dumps({"key_word":sys.argv[1],"id_type":0,"cursor":"0","limit":5,"search_type":0}))' "$Q")" \
    -o "$TMP/jj.json" -w '%{http_code}' > "$TMP/jj.http" 2>/dev/null
}
f_oalex() {  # OpenAlex 学术
  curl -s --max-time 12 -G "https://api.openalex.org/works" \
    --data-urlencode "search=$ENQ" --data-urlencode "per-page=5" \
    --data-urlencode 'mailto=d-reach@local' -o "$TMP/oalex.json" -w '%{http_code}' > "$TMP/oalex.http" 2>/dev/null
}
f_crossref() { # DOI 权威元数据（⚠️ 中文 query 会跑偏 → CJK 时跳过）
  if [ "$CJK" = "1" ]; then
    echo "cjk" > "$TMP/skip.crossref"
    return 0
  fi
  curl -s --max-time 12 -G "https://api.crossref.org/works" \
    --data-urlencode "query=$Q" --data-urlencode "rows=5" \
    --data-urlencode 'select=title,DOI,URL,published' -o "$TMP/crossref.json" -w '%{http_code}' > "$TMP/crossref.http" 2>/dev/null
}
f_segfault() { # SegmentFault 中文技术长尾（-L 跟跳转；博客园已废弃）
  # 实测同站响应 2.3–11.4s 波动（q=rust 2.8s，q="rust tokio" 11.4s），
  # 14s 上限在并发时会被掐掉，放宽到 20s 让它跑完。
  curl -sL --compressed --max-time 20 -A "$UA" -G "https://segmentfault.com/search" \
    --data-urlencode "q=$Q" -o "$TMP/segfault.html" -w '%{http_code}' > "$TMP/segfault.http" 2>/dev/null
}
f_fcdev() {  # Firecrawl Developer Index（70M+ 一手源）
  # 有 key 走 key：keyless 是 IP 级免费额度，耗尽后 429 要等十几小时（实测 retry_after 40699s）
  # 没 key 才落 keyless 免费档，仍能跑但随时可能被限
  _fck=$(sh "$DIR/load_key.sh" FIRECRAWL_API_KEY https://firecrawl.dev 2>/dev/null) || _fck=""
  if [ -n "$_fck" ]; then
    curl -s --max-time 18 -G "https://api.firecrawl.dev/v2/search/developer" -H "Authorization: Bearer $_fck" \
      --data-urlencode "query=$ENQ" --data-urlencode "k=5" -o "$TMP/fcdev.json" -w '%{http_code}' > "$TMP/fcdev.http" 2>/dev/null
    [ "$(cat "$TMP/fcdev.http" 2>/dev/null)" = "200" ] && charge firecrawl
  else
    curl -s --max-time 18 -G "https://api.firecrawl.dev/v2/search/developer" \
      --data-urlencode "query=$ENQ" --data-urlencode "k=5" -o "$TMP/fcdev.json" -w '%{http_code}' > "$TMP/fcdev.http" 2>/dev/null
  fi
}
f_qianfan() { # 百度千帆：生成式综合答案（非来源链接！）
  [ -f "$BAIDU/smart_search.py" ] || { echo "not-configured" > "$TMP/skip.qianfan"; echo "千帆配套技能未安装；本轮按未配置跳过，不计为渠道故障。" > "$TMP/qianfan.txt"; return 0; }
  run_command_with_timeout 50 "$TMP/qianfan.raw" "$TMP/qianfan.err" \
    python3 "$BAIDU/smart_search.py" search "$Q"
  _qrc=$?
  sed -e '/^--- 配额状态 ---/,$d' -e '/^\[调度\]/d' "$TMP/qianfan.raw" > "$TMP/qianfan.txt" 2>/dev/null
  # 千帆报错时绝不能把错误文本当「AI 答案」渲染：报错、空输出、或 stderr 有内容 → 标 err
  if [ "$_qrc" != "0" ] || [ ! -s "$TMP/qianfan.txt" ] || [ -s "$TMP/qianfan.err" ]; then
    echo "err" > "$TMP/skip.qianfan"
    head -c 300 "$TMP/qianfan.err" >> "$TMP/qianfan.txt" 2>/dev/null
  fi
  # 免费额度降到 ≤20% 时 smart_search.py 会自动切备用 API，此时它吐的是裸 JSON
  # （[⚠️ 自动跳过] ... 加一个 JSON 数组）。直接渲染就是把 JSON 当答案塞给用户。
  # 识别出来转成正常条目，并标明这是降档结果而不是 AI 摘要。
  if grep -qE '^\[\s*$' "$TMP/qianfan.txt" 2>/dev/null; then
    python3 - "$TMP/qianfan.txt" > "$TMP/qianfan.md" <<'PYQ'
import json, re, sys
raw = open(sys.argv[1], encoding="utf-8", errors="replace").read()
m = re.search(r"\[\s*\{.*\}\s*\]", raw, re.S)
rows = []
if m:
    try:
        rows = json.loads(m.group(0))
    except Exception:
        rows = []
if not rows:
    print(raw.strip()[:600])
else:
    out = []
    for r in rows[:8]:
        t = (r.get("title") or "").strip()
        u = (r.get("url") or "").strip()
        d = (r.get("date") or "").strip()[:10]
        if not t:
            continue
        meta = " · ".join(x for x in (d, "百度降档结果") if x)
        out.append(f"- [{t}]({u}) — {meta}" if u else f"- {t} — {meta}")
    print("\n".join(out))
PYQ
    mv "$TMP/qianfan.md" "$TMP/qianfan.txt"
  fi
}

f_tf() {   # TinyFish Search（官方 hosted MCP，$0/次；JSON-RPC tools/call search）
  gate tinyfish || return 0
  TF_KEY="$TF_KEY" python3 - "$ENQ" > "$TMP/tf.json" 2>"$TMP/tf.err" <<'PYEOF'
import json, os, sys, urllib.request

q = sys.argv[1]
key = os.environ["TF_KEY"]
URL = "https://agent.tinyfish.ai/mcp"

def rpc(payload, session=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "X-API-Key": key}
    if session:
        h["Mcp-Session-Id"] = session
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        # hosted 强制：initialize 响应头下发 mcp-session-id，后续请求必须回带
        return r.headers.get("mcp-session-id"), r.read().decode("utf-8", "replace")

sid, _ = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "d-reach-fanout", "version": "1.0"}}})
rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
sys.stdout.write(rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
     "params": {"name": "search",
                "arguments": {"query": q,
                              "purpose": "d-reach parallel multi-channel web fanout"}}}, sid)[1])
PYEOF
}

# ---------- deep 追加通道 ----------
f_langsearch() {
  gate langsearch || return 0
  curl -s --max-time 30 -X POST "https://api.langsearch.com/v1/web-search" \
    -H "Authorization: Bearer $LS_KEY" -H 'Content-Type: application/json' \
    -d "$(python3 -c 'import json,sys;print(json.dumps({"query":sys.argv[1],"count":20}))' "$ENQ")" \
    -o "$TMP/langsearch.json" -w '%{http_code}' > "$TMP/langsearch.http" 2>/dev/null
  [ "$(cat "$TMP/langsearch.http" 2>/dev/null)" = "200" ] && charge langsearch
}
f_exa() {
  gate exa || return 0
  curl -s --max-time 20 -X POST "https://api.exa.ai/search" \
    -H "x-api-key: $EXA_KEY" -H 'Content-Type: application/json' \
    -d "$(python3 -c 'import json,sys;print(json.dumps({"query":sys.argv[1],"numResults":10}))' "$ENQ")" \
    -o "$TMP/exa.json" -w '%{http_code}' > "$TMP/exa.http" 2>/dev/null
  [ "$(cat "$TMP/exa.http" 2>/dev/null)" = "200" ] && charge exa
}
f_fcres() {
  gate fcres || return 0
  curl -s --max-time 20 -H "Authorization: Bearer $FC_KEY" -G \
    "https://api.firecrawl.dev/v2/search/research/papers" \
    --data-urlencode "query=$ENQ" --data-urlencode "k=5" \
    -o "$TMP/fcres.json" -w '%{http_code}' > "$TMP/fcres.http" 2>/dev/null
}
f_serper() {
  gate serper || return 0
  curl -s --max-time 20 -X POST "https://google.serper.dev/search" \
    -H "X-API-KEY: $SP_KEY" -H 'Content-Type: application/json' \
    -d "$(python3 -c 'import json,sys,re;q=sys.argv[1];print(json.dumps({"q":q,"num":10,"gl":"cn" if re.search(r"[\u4e00-\u9fff]",q) else "us","hl":"zh-cn" if re.search(r"[\u4e00-\u9fff]",q) else "en"}))' "$Q")" \
    -o "$TMP/serper.json" -w '%{http_code}' > "$TMP/serper.http" 2>/dev/null
  [ "$(cat "$TMP/serper.http" 2>/dev/null)" = "200" ] && charge serper
}
f_tavily() {   # Tavily keyless：无账号无 key，结果带 1400 字级正文摘录
  # 免费档按 IP 限速（官方称约 30 次/IP 后 429 hourly_cap_reached），不记账。
  # 与 serper 的区别：serper 只给标题+两行 snippet，它给整段正文，中文 query 实测 5/5 命中。
  curl -s --max-time 20 -X POST "https://api.tavily.com/search" \
    -H 'Content-Type: application/json' -H 'X-Tavily-Access-Mode: keyless' \
    -d "$(python3 -c 'import json,sys;print(json.dumps({"query":sys.argv[1],"max_results":8}))' "$ENQ")" \
    -o "$TMP/tavily.json" -w '%{http_code}' > "$TMP/tavily.http" 2>/dev/null
}
f_parallel() {   # Parallel 免费 MCP（web_search）：无 key 无账号，结果带 excerpts + 发布日期
  # 走 MCP 握手（initialize → notifications/initialized → tools/call），交给 mcp_call.py。
  python3 "$DIR/mcp_call.py" https://mcp.parallel.ai/mcp web_search \
    "$(python3 -c 'import json,sys;q=sys.argv[1];print(json.dumps({"objective":q,"search_queries":[q]}))' "$ENQ")" \
    > "$TMP/parallel.json" 2>/dev/null
  # 失败时脚本打 MCP_ERROR 行（不是 JSON），标 skip 而不是让解析器报「无响应」
  if [ "$(head -c 11 "$TMP/parallel.json" 2>/dev/null)" = "MCP_ERROR: " ]; then
    head -c 300 "$TMP/parallel.json" > "$TMP/skip.parallel"
    : > "$TMP/parallel.json"
  fi
}
f_youcom() {   # You.com 免 key MCP（you-search）：100 次/天，官方称 p50 0.4s
  # 官方定价页明确「No API key, no account, no credit card」，走 ?profile=free 档。
  # 注意：该网关会 403 掉 Python-urllib 默认 UA，mcp_call.py 里已固定 d-reach/1.0。
  python3 "$DIR/mcp_call.py" "https://api.you.com/mcp?profile=free" you-search \
    "$(python3 -c 'import json,sys;print(json.dumps({"query":sys.argv[1],"count":6}))' "$ENQ")" \
    > "$TMP/youcom.json" 2>/dev/null
  if [ "$(head -c 11 "$TMP/youcom.json" 2>/dev/null)" = "MCP_ERROR: " ]; then
    head -c 300 "$TMP/youcom.json" > "$TMP/skip.youcom"
    : > "$TMP/youcom.json"
  fi
}
f_anysearch() {   # AnySearch：1000 次/天免费，20+ 垂直领域（法律/医疗/金融专库）
  # 带 key 与匿名共享同一个 daily free quota，但带 key 不按 IP 算 —— 共享出口 IP 更稳。
  # zone 按 query 语言自动切 cn / intl。
  _ask=$(sh "$DIR/load_key.sh" ANYSEARCH_API_KEY https://anysearch.com 2>/dev/null) || _ask=""
  _abody=$(python3 -c 'import json,re,sys
q=sys.argv[1]
z="cn" if re.search(r"[\u4e00-\u9fff]", q) else "intl"
print(json.dumps({"query":q,"max_results":6,"zone":z}))' "$Q")
  if [ -n "$_ask" ]; then
    curl -s --max-time 22 -X POST "https://api.anysearch.com/v1/search" \
      -H "Authorization: Bearer $_ask" -H 'Content-Type: application/json' \
      -d "$_abody" -o "$TMP/anysearch.json" -w '%{http_code}' > "$TMP/anysearch.http" 2>/dev/null
  else
    curl -s --max-time 22 -X POST "https://api.anysearch.com/v1/search" \
      -H 'Content-Type: application/json' \
      -d "$_abody" -o "$TMP/anysearch.json" -w '%{http_code}' > "$TMP/anysearch.http" 2>/dev/null
  fi
}
f_zhihu() {   # 知乎开放平台站内搜索：需 ZHIHU_SEARCH_API_KEY（官方 API，非爬虫）
  # 返回标题/摘要/赞同数/评论数；免费额度按开放平台控制台发放规则。
  _zk=$(sh "$DIR/load_key.sh" ZHIHU_SEARCH_API_KEY https://developer.zhihu.com 2>/dev/null) || { echo "key" > "$TMP/skip.zhihu"; return 1; }
  curl -s --max-time 20 -G 'https://developer.zhihu.com/api/v1/content/zhihu_search' \
    --data-urlencode "Query=$Q" -d "Count=8" \
    -H "Authorization: Bearer $_zk" \
    -H "X-Request-Timestamp: $(date +%s)" \
    -o "$TMP/zhihu.json" -w '%{http_code}' > "$TMP/zhihu.http" 2>/dev/null
}
f_zhihuall() {   # 知乎开放平台全网搜索：5000 次/日限免，中文全网（权威分级），需 ZHIHU_SEARCH_API_KEY
  _zk=$(sh "$DIR/load_key.sh" ZHIHU_SEARCH_API_KEY https://developer.zhihu.com 2>/dev/null) || { echo "key" > "$TMP/skip.zhihuall"; return 1; }
  curl -s --max-time 20 -G 'https://developer.zhihu.com/api/v1/content/global_search' \
    --data-urlencode "Query=$Q" -d 'Count=8' \
    -H "Authorization: Bearer $_zk" \
    -H "X-Request-Timestamp: $(date +%s)" \
    -o "$TMP/zhihuall.json" -w '%{http_code}' > "$TMP/zhihuall.http" 2>/dev/null
}
f_zhihuhot() {   # 知乎热榜：全站热点，与查询词无关（100 次/日限免），deep 档或 --on 时跑
  _zk=$(sh "$DIR/load_key.sh" ZHIHU_SEARCH_API_KEY https://developer.zhihu.com 2>/dev/null) || { echo "key" > "$TMP/skip.zhihuhot"; return 1; }
  curl -s --max-time 15 -G 'https://developer.zhihu.com/api/v1/content/hot_list' \
    -d 'Limit=15' \
    -H "Authorization: Bearer $_zk" \
    -H "X-Request-Timestamp: $(date +%s)" \
    -o "$TMP/zhihuhot.json" -w '%{http_code}' > "$TMP/zhihuhot.http" 2>/dev/null
}
f_zhida() {   # 知乎直答（OpenAI 兼容 /v1/chat/completions）：AI 摘要，非来源（100 次/日）
  _zk=$(sh "$DIR/load_key.sh" ZHIHU_SEARCH_API_KEY https://developer.zhihu.com 2>/dev/null) || { echo "key" > "$TMP/skip.zhida"; return 1; }
  _zbody=$(python3 -c 'import json,sys;print(json.dumps({"model":"zhida-fast-1p5","messages":[{"role":"user","content":sys.argv[1]}],"stream":False}))' "$Q")
  curl -s --max-time 45 -X POST 'https://developer.zhihu.com/v1/chat/completions' \
    -H "Authorization: Bearer $_zk" \
    -H "X-Request-Timestamp: $(date +%s)" \
    -H 'Content-Type: application/json' -d "$_zbody" \
    -o "$TMP/zhida.json" -w '%{http_code}' > "$TMP/zhida.http" 2>/dev/null
}
f_brave() {   # Brave Search API：自有索引（不经 Google/Bing），每月 $5 免费 credits ≈ 1000 次
  gate brave || return 0
  _bk=$(sh "$DIR/load_key.sh" BRAVE_API_KEY https://api-dashboard.search.brave.com/app/keys 2>/dev/null) || { echo "key" > "$TMP/skip.brave"; return 1; }
  curl -s --max-time 20 -G 'https://api.search.brave.com/res/v1/web/search' \
    --data-urlencode "q=$Q" -d 'count=8' -d 'safesearch=moderate' \
    -H "X-Subscription-Token: $_bk" -H 'Accept: application/json' \
    -o "$TMP/brave.json" -w '%{http_code}' > "$TMP/brave.http" 2>/dev/null
  [ "$(cat "$TMP/brave.http" 2>/dev/null)" = "200" ] && charge brave
}
f_fcs() {   # Firecrawl /search：全站搜索 + 可选抓正文，结果质量高（GitHub issue/官方文档/论文都能中）
  gate firecrawl_search || return 0
  curl -s --max-time 25 -X POST "https://api.firecrawl.dev/v1/search" \
    -H "Authorization: Bearer $FC_KEY" -H 'Content-Type: application/json' \
    -d "$(python3 -c 'import json,sys;print(json.dumps({"query":sys.argv[1],"limit":8}))' "$ENQ")" \
    -o "$TMP/fcs.json" -w '%{http_code}' > "$TMP/fcs.http" 2>/dev/null
  [ "$(cat "$TMP/fcs.http" 2>/dev/null)" = "200" ] && charge firecrawl
}
f_wiki() {   # Wikipedia REST summary：概念/人物/术语/地名，0.7s、完全免费、无限量
  gate wiki || return 0
  # 「紫砂壶是什么」这种疑问句直接搜 opensearch 会返回空数组（没有条目叫这个名字），
  # 要先剥掉疑问词再搜，否则回退成整个 query 去取 summary 必然 404
  STRIP='import re,sys
q=sys.argv[1]
q=re.sub(r"(是什么|是谁|什么是|的定义是什么|的定义|的原理是什么|的原理|的历史|的由来|怎么用|如何使用|有什么用|介绍一下|是什么意思)[？?。，,]*$","",q.strip())
q=re.sub(r"^(什么是|介绍一下|讲讲)", "", q)
print(q.strip() or sys.argv[1])'
  BASEQ=$(python3 -c "$STRIP" "$Q" 2>/dev/null || echo "$Q")
  os_search() {
    curl -s --max-time 12 -A "d-reach/1.0 (+https://github.com/DuanZGit/D-reach)" -G \
      "https://zh.wikipedia.org/w/api.php" \
      --data-urlencode "action=opensearch" --data-urlencode "search=$1" \
      --data-urlencode "limit=1" --data-urlencode "format=json" \
      | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); print(d[1][0] if d[1] else "")
except Exception: print("")' 2>/dev/null
  }
  # 多词 query（「杭州 西湖 门票」）opensearch 常返空；再用 list=search 兜底取首条标题。
  # 两轮都空说明维基确实没有对应条目 —— 此时记 0 命中，不能留 404（会被误判成通道故障）。
  ls_search() {
    curl -s --max-time 12 -A "d-reach/1.0 (+https://github.com/DuanZGit/D-reach)" -G \
      "https://zh.wikipedia.org/w/api.php" \
      --data-urlencode "action=query" --data-urlencode "list=search" \
      --data-urlencode "srsearch=$1" --data-urlencode "srlimit=1" \
      --data-urlencode "format=json" \
      | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); s=(d.get("query") or {}).get("search") or []; print(s[0]["title"] if s else "")
except Exception: print("")' 2>/dev/null
  }
  TITLE=$(os_search "$Q")
  [ -z "$TITLE" ] && TITLE=$(os_search "$BASEQ")
  [ -z "$TITLE" ] && TITLE=$(ls_search "$BASEQ")
  [ -z "$TITLE" ] && TITLE=$(ls_search "$Q")
  if [ -z "$TITLE" ]; then
    printf '{"type":"none"}' > "$TMP/wiki.json"
    printf '200' > "$TMP/wiki.http"
    return 0
  fi
  # REST summary 端点自己会跟随繁简重定向（/w/api.php?redirects=1 对中文维基的繁简重定向不生效，
  # 「紫砂壶」会拿到「簡繁重定向」那段说明文字而不是正文）
  ENC=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1].replace(" ","_")))' "$TITLE" 2>/dev/null)
  curl -s --max-time 12 -A "d-reach/1.0 (+https://github.com/DuanZGit/D-reach)" "https://zh.wikipedia.org/api/rest_v1/page/summary/$ENC" \
    -o "$TMP/wiki.json" -w '%{http_code}' > "$TMP/wiki.http" 2>/dev/null

  # 中文条目常常只有一句话（实测「小米手环」64 字符、「RAG」174 字符，
  # 而英文同条目 689 字符）。内容太短就用英文 query 再查一遍英文维基，取长的那个。
  ZH_LEN=$(python3 -c 'import json,sys
try: print(len(json.load(open(sys.argv[1])).get("extract") or ""))
except Exception: print(0)' "$TMP/wiki.json" 2>/dev/null || echo 0)
  if [ "${ZH_LEN:-0}" -lt 300 ] && [ -n "$ENQ" ] && [ "$ENQ" != "$Q" ]; then
    EN_TITLE=$(curl -s --max-time 12 -A "d-reach/1.0 (+https://github.com/DuanZGit/D-reach)" -G \
      "https://en.wikipedia.org/w/api.php" \
      --data-urlencode "action=query" --data-urlencode "list=search" \
      --data-urlencode "srsearch=$ENQ" --data-urlencode "srlimit=1" \
      --data-urlencode "format=json" \
      | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); s=(d.get("query") or {}).get("search") or []; print(s[0]["title"] if s else "")
except Exception: print("")' 2>/dev/null)
    if [ -n "$EN_TITLE" ]; then
      EN_ENC=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1].replace(" ","_")))' "$EN_TITLE" 2>/dev/null)
      curl -s --max-time 12 -A "d-reach/1.0 (+https://github.com/DuanZGit/D-reach)" \
        "https://en.wikipedia.org/api/rest_v1/page/summary/$EN_ENC" -o "$TMP/wiki_en.json" 2>/dev/null
      python3 - "$TMP/wiki.json" "$TMP/wiki_en.json" <<'PYPICK'
import json, sys
zh_f, en_f = sys.argv[1], sys.argv[2]
def load(f):
    try: return json.load(open(f))
    except Exception: return {}
zh, en = load(zh_f), load(en_f)
if len(en.get("extract") or "") > len(zh.get("extract") or ""):
    json.dump(en, open(zh_f, "w"))
    print("en", file=sys.stderr)
else:
    print("zh", file=sys.stderr)
PYPICK
    fi
  fi
}
# 已退役通道（2026-09-25 实测，别往回加）：
#   · V2EX /search?q= —— 302 → /go/search，返回「搜索引擎技术研究」节点帖子，与 query 无关
#     （会给假结果；假结果比无响应更毒，故整路移除）
#   · 博客园 zzk.cnblogs.com —— 302→zzkx 后返回 5.7KB 壳页、0 结果
#   中文社区长尾现在靠 掘金 + SegmentFault + 知乎开放平台 API；cn.bing 已投毒。

# ---------- 并发发射 ----------
launch() {   # $1 = 函数名；失败不拖垮整体
  fn="$1"; key="${fn#f_}"
  want "$key" || return 0
  if [ "$key" = "qianfan" ] && [ ! -f "$BAIDU/smart_search.py" ]; then
    echo "not-configured" > "$TMP/skip.qianfan"
    echo "千帆配套技能未安装；本轮按未配置跳过，不计为渠道故障。" > "$TMP/qianfan.txt"
    return 0
  fi
  # 健康状态：连续失败 ≥3 次的路默认不再发请求（除非 --force 或 --on 显式点名）
  if [ "$FORCE" != "1" ] && [ -z "$ON" ]; then
    case " $HEALTH_BAD " in
      *" $key "*) echo "health" > "$TMP/skip.$key"; return 0 ;;
    esac
  fi
  ( "$fn" ) &
}
for fn in f_se f_hn f_jj f_zhihu f_zhihuall f_zhihuhot f_zhida f_oalex f_crossref f_segfault f_fcdev f_gh f_qianfan f_tf f_serper f_fcs f_wiki f_tavily f_parallel f_youcom f_anysearch f_brave f_xhs f_bili; do launch "$fn"; done
# --on 显式点名时也要跑 deep 档通道，否则 deep 通道的结果会丢掉
if [ "$DEEP" = 1 ] || [ -n "$ON" ]; then
  for fn in f_langsearch f_exa f_fcres; do launch "$fn"; done
fi
wait

# ---------- 渲染 ----------
# 本轮起始时间：给 history.jsonl 算耗时用（调用方已给就沿用，比如插件那边能算得更准）
[ -n "${D_REACH_T0:-}" ] || D_REACH_T0=$(date +%s)
export D_REACH_T0
# 脚本指纹：通道的「这路坏了/要登录」结论绑定它。改了脚本旧结论自动作废，
# 不用手删 channels.json（照 Agent-Reach 的 fingerprint 失效机制）。
D_REACH_FP=$(md5sum "$DIR/fanout.sh" 2>/dev/null | cut -c1-8)
export D_REACH_FP

python3 - "$TMP" "$Q" "$N" "$DEEP" "$ON" "$DEFAULT_DISABLED" <<'PY'
import json, os, re, sys, html, pathlib, time
from datetime import datetime, timezone, timedelta

# 收集本轮全部输出，历史详情（网关点一条看全文）要用 —— 覆盖 print 而不是到处插 buf.append
_REAL_PRINT = print
_OUT = []
def print(*a, **k):
    import io as _io
    _b = _io.StringIO()
    k2 = dict(k); k2["file"] = _b
    _REAL_PRINT(*a, **k2)
    _OUT.append(_b.getvalue())
    if k.get("file") is sys.stdout or "file" not in k:
        _REAL_PRINT(*a)

tmp, Q, N, DEEP, ON, DEFAULT_DISABLED = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5], sys.argv[6]
N = max(1, min(N, 20))
ONLY = {c for c in ON.split(",") if c} if ON else None   # None = 按默认启用清单
DISABLED = {c for c in DEFAULT_DISABLED.split(",") if c}

def load_text(name):
    p = os.path.join(tmp, name)
    if not os.path.exists(p) or os.path.getsize(p) == 0:
        return None
    raw = pathlib.Path(p).read_bytes()
    if not raw.strip():
        return None
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", "replace")

def load_json(name):
    t = load_text(name)
    if t is None:
        return None
    try:
        return json.loads(t)
    except Exception:
        return None

def clean(s):
    out = str(s if s is not None else "")
    out = re.sub(r"<[^>]+>", " ", out)
    for _ in range(3):          # Crossref 有双重转义记录（&amp;amp;），解到底
        new = html.unescape(out)
        if new == out:
            break
        out = new
    return re.sub(r"\s+", " ", out).strip()

def trunc(s, n=110):
    s = clean(s)
    return s[:n] + ("…" if len(s) > n else "")

def rowify(pairs):
    """去重 + 截断；URL 必须是 http(s) 才算来源。"""
    out, seen = [], set()
    for t, u, x in pairs:
        t, u, x = clean(t), str(u or "").strip(), clean(x)
        if not t or not u.startswith("http") or u in seen:
            continue
        seen.add(u)
        out.append((t[:170], u, x[:120]))
        if len(out) >= N:
            break
    return out

def walk_generic(d):
    """兜底：递归抓 {title/name, url/link} 对（结构未知的通道用它）。"""
    out = []
    def walk(o):
        if isinstance(o, dict):
            u = o.get("url") or o.get("link") or o.get("html_url") or o.get("landing_page_url")
            t = o.get("title") or o.get("name")
            if isinstance(u, str) and u.startswith("http") and t:
                out.append((t, u, trunc(o.get("snippet") or o.get("description")
                                        or o.get("summary") or o.get("text"), 100)))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(d)
    return out

# ---------- 每路专用解析（字段名各通道不同，别合并） ----------
def _query_tokens(q):
    """把 query 切成可比对的 token：西文 ≥4 字母词 + 中文二字片段。"""
    q = clean(q).lower()
    toks = set(re.findall(r"[a-z]{4,}", q))
    cjk = re.sub(r"[^\u4e00-\u9fff]", "", q)
    toks.update(cjk[i:i + 2] for i in range(len(cjk) - 1))
    return toks

def r_bing():
    t = load_text("bing.html")
    if not t:
        return None
    out = []
    for m in re.finditer(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', t, re.S | re.I):
        u, ti = m.group(1), clean(m.group(2))
        if ti and u.startswith("http"):
            out.append((ti, u, ""))
    rows = rowify(out)
    # 🕳️ 投毒闸门（2026-10-05 实测）：cn.bing 对本机 HTTP 200 + 页面结构正常，但返回与 query
    # 完全无关的填充页（「意式咖啡豆 中深烘 拿铁」→ 法语「巴西米饭做法」；同 query 稳定复现；
    # 随机参数 / no-cache 头 / 换 UA / 换 mkt 全部无效）→ 服务端反爬投毒，非缓存串号也非解析 bug。
    # 假结果比无响应更毒（同 V2EX 教训）：标题与 query 无 ≥2 个 token 重合的条目一律剔除，
    # 全被剔除则报 ⚠️ 而不是 ✅。
    if rows:
        toks = _query_tokens(Q)
        if toks:
            need = 2 if len(toks) >= 3 else 1
            keep = [r for r in rows if sum(k in r[0].lower() for k in toks) >= need]
            if not keep:
                return ("ERR", f"返回 {len(rows)} 条但与查询完全无关（疑似反爬投毒：本机实测 "
                               f"cn.bing 返回法语食谱/乌尔都语诗歌等填充页，同 query 稳定复现；"
                               f"加随机参数 / no-cache / 换 UA 均无效）")
            rows = keep
    return rows

def r_se():
    d = load_json("se.json")
    if d is None:
        return None
    out = []
    for i in d.get("items") or []:
        x = f"score {i.get('score', '-')} · {i.get('answer_count', 0)} 答"
        if i.get("is_answered"):
            x += " · ✅已采纳"
        out.append((i.get("title", ""), i.get("link", ""), x))
    return rowify(out)

def r_hn():
    d = load_json("hn.json")
    if d is None:
        return None
    out = []
    for h in d.get("hits") or []:
        u = h.get("url") or (f"https://news.ycombinator.com/item?id={h['objectID']}"
                             if h.get("objectID") else "")
        out.append((h.get("title", ""), u,
                    f"{h.get('points', 0)} 分 · {h.get('num_comments', 0)} 评论"))
    return rowify(out)

def r_jj():
    d = load_json("jj.json")
    if d is None:
        return None
    out = []
    def walk(o):   # 标题埋在 article_info 里，article_id 要拼 URL
        if isinstance(o, dict):
            ai = o.get("article_info")
            if isinstance(ai, dict) and ai.get("title"):
                aid = ai.get("article_id") or o.get("article_id")
                out.append((ai.get("title", ""),
                            f"https://juejin.cn/post/{aid}" if aid else "",
                            trunc(ai.get("brief_content", ""), 90)))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(d)
    return rowify(out)

def r_oalex():
    d = load_json("oalex.json")
    if d is None:
        return None
    return rowify([(w.get("display_name") or w.get("title") or "",
                    w.get("id") or w.get("doi") or "",
                    f"被引 {w.get('cited_by_count', 0)}")
                   for w in d.get("results") or []])

def r_crossref():
    d = load_json("crossref.json")
    if d is None:
        return None
    out = []
    for it in (d.get("message") or {}).get("items") or []:
        ti = it.get("title") or []
        ti = ti[0] if isinstance(ti, list) and ti else (ti if isinstance(ti, str) else "")
        yr = ""
        try:
            yr = str(it["published"]["date-parts"][0][0])
        except Exception:
            pass
        out.append((ti, it.get("URL") or it.get("DOI") or "", yr))
    return rowify(out)

def r_segfault():
    t = load_text("segfault.html")
    if not t:
        return None
    return rowify([(clean(m.group(2)), "https://segmentfault.com" + m.group(1), "")
                   for m in re.finditer(
                       r'<a[^>]+href="(/a/[0-9A-Za-z_-]+)"[^>]*>(.*?)</a>', t, re.S | re.I)
                   if len(clean(m.group(2))) > 4])

def r_gh():
    d = load_json("gh.json")
    if d is None:
        return None
    items = d.get("items")
    if not isinstance(items, list):
        return None
    return rowify([("%s ★%s" % (it.get("full_name", ""), it.get("stargazers_count", 0)),
                    it.get("html_url", ""),
                    trunc(it.get("description") or "", 100))
                   for it in items])

def r_xhs():
    d = load_json("xhs.json")
    if not isinstance(d, dict):
        return None
    items = (d.get("data") or {}).get("items")
    if not isinstance(items, list):
        return None
    rows = []
    for it in items[:6]:
        nc = it.get("note_card") or {}
        title = nc.get("display_title") or nc.get("desc") or ""
        note_id = it.get("id") or ""
        if not title or not note_id:
            continue
        author = ((nc.get("user") or {}).get("nickname") or "").strip()
        likes = ((nc.get("interact_info") or {}).get("liked_count") or "").strip()
        meta = " · ".join(value for value in (author, (likes + " 赞") if likes else "") if value) or "小红书笔记"
        rows.append((trunc(title, 80), "https://www.xiaohongshu.com/explore/" + note_id, meta))
    return rowify(rows)

def r_bili():
    d = load_json("bili.json")
    if not isinstance(d, dict):
        return None
    vs = (d.get("result") or {}).get("videos")
    if not isinstance(vs, list):
        return None
    return rowify([(trunc(v.get("title", ""), 80),
                    "https://www.bilibili.com/video/" + v.get("bvid", ""),
                    "%s · %s 播放 · %s" % (v.get("author", ""), v.get("play", ""), v.get("duration", "")))
                   for v in vs[:6] if v.get("bvid")])

def r_fcdev():
    d = load_json("fcdev.json")
    if d is None:
        return None
    items = d.get("data") if isinstance(d.get("data"), list) else None
    if items is None:
        return rowify(walk_generic(d))
    return rowify([(it.get("title", ""), it.get("url", ""),
                    trunc(it.get("description") or it.get("snippet") or "", 100))
                   for it in items])

def r_tf():
    """TinyFish search：hosted MCP tools/call 的 JSON-RPC 响应。
    hosted 返回可能是裸 JSON 或 SSE data: 行；results 可能在 structuredContent
    或 content[0].text 内嵌 JSON 里，逐个兼容，最后 walk_generic 兜底。"""
    t = load_text("tf.json")
    if not t:
        return None
    r = None
    if t.lstrip().startswith("{"):
        r = json.loads(t)
    else:
        for line in t.splitlines():
            if line.startswith("data:"):
                d = line[5:].strip()
                if d.startswith("{"):
                    r = json.loads(d)
                    break
    if not isinstance(r, dict):
        return None
    if r.get("error"):
        return ("ERR", "TinyFish API 错误：" + str(r["error"].get("message", r["error"]))[:120])
    res = r.get("result") or {}
    results = None
    sc = res.get("structuredContent")
    if isinstance(sc, dict):
        results = sc.get("results") or sc.get("data")
    if results is None:
        for block in (res.get("content") or []):
            txt = block.get("text") if isinstance(block, dict) else None
            if not txt:
                continue
            try:
                inner = json.loads(txt)
            except Exception:
                continue
            results = inner.get("results") or inner.get("data")
            if results is not None:
                break
    if results is None:
        rows = rowify(walk_generic(res))
    else:
        rows = rowify([(it.get("title", ""), it.get("url", ""),
                        trunc(it.get("snippet") or it.get("description") or "", 100))
                       for it in results])
    if not rows:
        return ("ERR", "TinyFish 返回 0 条（凭据无效或限流时也会 0 条；看 tf.err）")
    return rows

def r_langsearch():
    d = load_json("langsearch.json")
    if d is None:
        return None
    if d.get("code") not in (None, 200):
        return ("ERR", f"body code={d.get('code')} {trunc(d.get('msg', ''), 160)}")
    vals = ((d.get("data") or {}).get("webPages") or {}).get("value") or []
    out = []
    for v in vals:
        x = trunc(v.get("snippet") or v.get("text") or "", 100)
        if v.get("datePublished"):
            x = (x + " · " + v["datePublished"][:10])
        out.append((v.get("name", ""), v.get("url", ""), x))
    return rowify(out)

def r_exa():
    d = load_json("exa.json")
    if d is None:
        return None
    if d.get("error"):
        return ("ERR", trunc(d.get("error"), 200))
    return rowify([(x.get("title", ""), x.get("url", ""),
                    trunc(x.get("snippet") or x.get("text") or "", 100))
                   for x in d.get("results") or []])

def r_tavily():
    d = load_json("tavily.json")
    if d is None:
        return None
    if d.get("error") or d.get("detail"):
        return ("ERR", trunc(str(d.get("error") or d.get("detail")), 200))
    items = d.get("results") if isinstance(d.get("results"), list) else None
    if items is None:
        return rowify(walk_generic(d))
    # content 是整段正文（实测 1300–1500 字），截到 120 字作摘要
    return rowify([(it.get("title", ""), it.get("url", ""), trunc(it.get("content") or "", 120))
                   for it in items])

def r_parallel():
    d = load_json("parallel.json")
    if d is None:
        return None
    items = d.get("results") if isinstance(d.get("results"), list) else None
    if items is None:
        return rowify(walk_generic(d))
    rows = []
    for it in items:
        ex = it.get("excerpts") or []
        snip = trunc(" ".join(str(e) for e in ex), 120) if ex else ""
        # 发布日期对「最新/时效」类问题有用，拼进摘要最前面
        if it.get("publish_date"):
            snip = f"[{it['publish_date']}] {snip}"
        rows.append((it.get("title", ""), it.get("url", ""), snip))
    return rowify(rows)

def r_serper():
    d = load_json("serper.json")
    if d is None:
        return None
    if d.get("message") or d.get("error"):
        return ("ERR", trunc(str(d.get("message") or d.get("error")), 200))
    rows = list(d.get("organic") or [])
    # knowledgeGraph（实体卡：门店/品牌/景点）常常是本地生活最准的那条，排在最前
    kg = d.get("knowledgeGraph") or {}
    if kg.get("title") and kg.get("descriptionLink"):
        rows.insert(0, {"title": kg.get("title"), "link": kg.get("descriptionLink"),
                        "snippet": kg.get("description", "")})
    return rowify([(x.get("title", ""), x.get("link", ""),
                    trunc(x.get("snippet") or "", 100)) for x in rows])

def r_youcom():
    d = load_json("youcom.json")
    if d is None:
        return None
    web = (d.get("results") or {}).get("web") if isinstance(d.get("results"), dict) else None
    if not isinstance(web, list):
        return rowify(walk_generic(d))
    rows = []
    for it in web:
        hl = ((it.get("contents") or {}).get("highlights") or [])
        snip = trunc(str(hl[0]), 120) if hl else trunc(it.get("description") or "", 120)
        # page_age 对「最新/时效」类问题有用
        if it.get("page_age"):
            snip = f"[{str(it['page_age'])[:10]}] {snip}"
        rows.append((it.get("title", ""), it.get("url", ""), snip))
    return rowify(rows)

def r_anysearch():
    d = load_json("anysearch.json")
    if d is None:
        return None
    # 成功是 code==0；402 是额度耗尽，403 是 key 过期
    if d.get("code") not in (0, None):
        return ("ERR", trunc(str(d.get("message") or "code != 0"), 200))
    items = (d.get("data") or {}).get("results") if isinstance(d.get("data"), dict) else None
    if not isinstance(items, list):
        return rowify(walk_generic(d))
    # 实测 snippet 常是站点侧栏推荐语（与 query 无关），content 才是正文 —— 优先 content。
    rows = []
    for it in items:
        body = it.get("content") or ""
        # content 是一整行压平的 markdown（"# 标题 # 站点名 > 栏目 ..."），
        # 按 # 切开取第一段够长的实义文字，否则摘要会全是标题和面包屑
        if body:
            parts = [x.strip() for x in re.split(r"#+", body) if len(x.strip()) > 20]
            body = parts[0] if parts else body.strip()
        rows.append((it.get("title", ""), it.get("url", ""),
                     trunc(body or it.get("snippet") or "", 120)))
    return rowify(rows)

def _zhihu_rows(fname):
    """知乎开放平台 zhihu_search / global_search 共用：Data.Items[] 同构。"""
    d = load_json(fname)
    if d is None:
        return None
    code = d.get("Code")
    if code not in (0, None):
        return ("ERR", trunc(f'{code}: {d.get("Message") or "zhihu error"}', 160))
    data = d.get("Data") or {}
    items = data.get("Items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return rowify(walk_generic(d))
    rows = []
    for it in items:
        meta = f'[赞{it.get("VoteUpCount", 0)}·评{it.get("CommentCount", 0)}] '
        ts = it.get("EditTime") or it.get("CreateTime")
        if isinstance(ts, (int, float)) and ts > 0:
            meta += time.strftime("%Y-%m-%d", time.localtime(ts)) + " "
        rows.append((it.get("Title", ""), it.get("Url", ""),
                     meta + trunc(it.get("ContentText") or "", 100)))
    return rowify(rows)

def r_zhihu():
    return _zhihu_rows("zhihu.json")

def r_zhihuall():
    return _zhihu_rows("zhihuall.json")

def r_zhihuhot():
    d = load_json("zhihuhot.json")
    if d is None:
        return None
    code = d.get("Code")
    if code not in (0, None):
        return ("ERR", trunc(f'{code}: {d.get("Message") or "hot_list error"}', 160))
    items = (d.get("Data") or {}).get("Items") or []
    return rowify([(it.get("Title", ""), it.get("Url", ""),
                    trunc(it.get("Summary") or "", 100)) for it in items])

def r_zhida():
    """直答是 OpenAI 兼容对话：没有来源链接，返回纯文本（走 txt_only 分支）。"""
    d = load_json("zhida.json")
    if d is None:
        return None
    err = d.get("error")
    if isinstance(err, dict):
        return ("ERR", trunc(str(err.get("message") or err.get("code") or "zhida error"), 160))
    ch = (d.get("choices") or [{}])[0]
    txt = ((ch.get("message") or {}).get("content") or "").strip()
    return txt or None

def r_brave():
    """Brave Web Search：web.results[] 里 title/url/description，description 是 1-2 句摘要。"""
    d = load_json("brave.json")
    if d is None:
        return None
    if d.get("error") or d.get("type") == "ErrorResponse":
        msg = d.get("message") or (d.get("error") or {}).get("detail") or "brave error"
        return ("ERR", trunc(str(msg), 160))
    rows = []
    for it in ((d.get("web") or {}).get("results") or []):
        if not isinstance(it, dict):
            continue
        rows.append((it.get("title") or "", it.get("url") or "",
                     it.get("description") or it.get("snippet") or ""))
    return rowify(rows)

def r_fcs():
    d = load_json("fcs.json")
    if d is None:
        return None
    if d.get("success") is False:
        return ("ERR", trunc(str(d.get("error") or "firecrawl search failed"), 200))
    return rowify([(x.get("title") or "", x.get("url") or "",
                    trunc(x.get("description") or x.get("markdown") or "", 100))
                   for x in (d.get("data") or [])])

def r_wiki():
    d = load_json("wiki.json")
    if d is None:
        return None
    if d.get("type") == "none":
        return []                                  # 无对应条目 = 0 命中，不是通道故障
    if d.get("type") == "disambiguation" or d.get("title") is None:
        return ("ERR", "维基百科没有这个条目（或只有消歧义页）")
    title = d.get("title") or ""
    ex = (d.get("extract") or "").strip()
    if not title or not ex:
        return ("ERR", "维基百科条目没有正文")
    url = ((d.get("content_urls") or {}).get("desktop") or {}).get("page") \
        or "https://zh.wikipedia.org/wiki/" + title.replace(" ", "_")
    return rowify([(title, url, trunc(ex, 100))])

def r_fcres():
    d = load_json("fcres.json")
    if d is None:
        return None
    for k in ("results", "data", "papers"):     # 顶层是 results（不是 data）
        rows = d.get(k)
        if not isinstance(rows, list):
            continue
        out = []
        for x in rows:
            u = x.get("url") or x.get("pdf_url") or ""
            pid = str(x.get("primaryId") or "")
            if not u and pid.startswith("arxiv:"):
                u = "https://arxiv.org/abs/" + pid[6:]
            elif not u and pid.startswith("DOI:"):
                u = "https://doi.org/" + pid[4:]
            out.append((x.get("title", ""), u, trunc(x.get("abstract") or "", 110)))
        return rowify(out)
    return rowify(walk_generic(d))

# (key, 通道名, 说明, 解析函数, 仅 deep)
SECTIONS = [
    ("qianfan",  "百度千帆（生成式综合答案）",
     "⚠️ AI 浓缩回答、非来源链接 —— 关键结论必须另找一手源验证",
     lambda: load_text("qianfan.txt"), False),
    ("gh",       "GitHub 仓库搜索（★ 排序，免 Key）", "免 Key 10 次/分钟；只认英文关键词", r_gh, False),
    ("fcdev",    "Firecrawl Developer Index（编程一手源 70M+）", "免 Key 不限量", r_fcdev, False),
    ("se",       "StackExchange（报错排障）", "免 Key 不限量", r_se, False),
    ("hn",       "Hacker News（深技术讨论）", "免 Key 不限量", r_hn, False),
    ("jj",       "掘金（中文技术长尾）", "免 Key 不限量", r_jj, False),
    ("zhihu",    "知乎站内搜索（开放平台官方 API）", "需 ZHIHU_SEARCH_API_KEY；结果带赞同/评论数", r_zhihu, False),
    ("zhihuall", "知乎全网搜索（开放平台官方 API）", "需 ZHIHU_SEARCH_API_KEY；5000 次/日，中文全网带权威分级", r_zhihuall, False),
    ("zhihuhot", "知乎热榜（全站热点，与查询词无关）", "需 ZHIHU_SEARCH_API_KEY；100 次/日，deep 档才跑", r_zhihuhot, True),
    ("zhida",    "知乎直答（AI 摘要，非来源链接）", "需 ZHIHU_SEARCH_API_KEY；100 次/日，deep 档才跑", r_zhida, True),
    ("brave",   "Brave Search（自有索引，不经 Google/Bing）", "需 BRAVE_API_KEY；每月 $5 免费 credits≈1000 次，用完自动停", r_brave, False),
    ("segfault", "SegmentFault（中文技术长尾）", "免 Key 不限量", r_segfault, False),
    ("oalex",    "OpenAlex（学术 2.5 亿篇）", "免 Key 不限量", r_oalex, False),
    ("crossref", "Crossref（DOI 权威元数据）", "免 Key 不限量", r_crossref, False),
    ("tf",      "TinyFish Search（官方 hosted MCP，$0/次）", "需 TINYFISH_API_KEY", r_tf, False),
    ("serper",  "Serper Google（本地生活/电商最强）", "2,500 次一次性赠送，已 quota.py use", r_serper, False),
    ("tavily",  "Tavily keyless（无账号，正文摘录）", "免费无 key；约 30 次/IP 后 429，不记账", r_tavily, False),
    ("parallel", "Parallel MCP（无 key，excerpts + 日期）", "免费无 key；匿名限流，不记账", r_parallel, False),
    ("youcom",   "You.com 免 key MCP（100 次/天，0.4s）", "免 key 无账号；每天 100 次", r_youcom, False),
    ("anysearch","AnySearch（1000 次/天，20+ 垂直域）", "带 key 额度不按 IP；每天 1000 次", r_anysearch, False),
    ("fcs",     "Firecrawl /search（全文搜索，质量高）", "消耗 firecrawl credits，已 quota.py use", r_fcs, False),
    ("wiki",    "Wikipedia（概念/人物/地名）", "完全免费无限量", r_wiki, False),
    ("xhs",      "国内版小红书（真实体验/种草/避坑）", "可选 xhs CLI；缺少时按未配置跳过；需登录态；冷却 2 分钟", r_xhs, False),
    ("bili",     "B 站视频（实测/教程/评测）", "需登录态；冷却 90 秒", r_bili, False),
    ("langsearch", "LangSearch count=20（时效/限域）", "每日 token 额度；本技能自设 50/日保守线，已 quota.py use", r_langsearch, True),
    ("exa",      "Exa（语义/英文）", "已 quota.py use", r_exa, True),
    ("fcres",    "Firecrawl Research Index（学术论文全文）", "需 key、不记账（官方论文端点免费）", r_fcres, True),
    # V2EX 已退役（会返回与 query 无关的假结果），见文件头「已退役通道」
]
SKIPMAP = {"langsearch": "langsearch", "exa": "exa", "fcres": "fcres", "tf": "tinyfish", "serper": "serper", "fcs": "firecrawl", "wiki": "wiki", "tavily": "tavily", "parallel": "parallel"}

def read_skip(key):
    for c in [key] + ([SKIPMAP[key]] if key in SKIPMAP else []):
        p = os.path.join(tmp, f"skip.{c}")
        if os.path.exists(p):
            return pathlib.Path(p).read_text().strip()
    return None

def http_code(key):
    """付费通道的 HTTP 状态码；没有记录返回 None。"""
    t = load_text(key + ".http")
    return t.strip() if t else None

_default_n = sum(1 for _s in SECTIONS if not _s[4] and _s[0] not in DISABLED)
if ON:
    _selected = (ONLY or set()) - DISABLED
    _label = f"指定通道（{len(_selected)} 路）"
elif DEEP == "1":
    _deep_n = sum(1 for _s in SECTIONS if _s[0] not in DISABLED)
    _label = f"deep 深调研档（{_deep_n} 路）"
else:
    _label = f"默认档（{_default_n} 路）"
if DISABLED:
    _label += f"；未运行 {', '.join(sorted(DISABLED))}"
print(f"## fanout「{Q}」— {_label}\n")
# ---------- 通道健康状态（跨轮记忆）----------
HEALTH = pathlib.Path(os.environ.get("D_REACH_HEALTH") or os.path.expanduser("~/.agent-reach/channels.json"))

def load_health():
    try:
        return json.loads(HEALTH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_health(h):
    try:
        HEALTH.parent.mkdir(parents=True, exist_ok=True)
        tmpf = HEALTH.with_suffix(".tmp")
        tmpf.write_text(json.dumps(h, indent=2, ensure_ascii=False), encoding="utf-8")
        tmpf.replace(HEALTH)
    except Exception:
        pass

health = load_health()
now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

# 挂起退避阶梯（秒）：第 3 次连败挂 10 分钟，第 4 次 30 分钟，第 5 次起 2 小时封顶。
# 取小值是为了「坏通道别永久静默」——挂起到期会自动重试一次，通了就清零。
BACKOFF = [600, 1800, 7200]

# 失败的「性质」决定要不要等它自己好。照 Agent-Reach 的错误码分层：
#   自愈类（timeout/upstream/empty）—— 连败 3 次才进退避阶梯；
#   确定性结论（登录墙/风控/凭据/限流/端点没了）—— 重试只会撞同一堵墙，
#   首次就挂起，并且文案要说清「谁该出手」，而不是干巴巴一句「连败 N 次」。
NEEDS = {
    "login": "站点要登录：浏览器里登录过一次，或换公开来源",
    "antibot": "撞了风控验证码：等几小时或换检索词",
    "auth": "key 失效或被拒：换 key 后自动恢复",
    "ratelimit": "平台限流：冷却窗口内不再打",
    "notfound": "端点 404：脚本里的地址要更新",
    "setup": "本机依赖不可用：先修依赖",
}
NEEDS_TITLE = {
    "login": "要登录", "antibot": "要过验证码", "auth": "凭据失效",
    "ratelimit": "限流中", "notfound": "端点失效", "setup": "依赖缺失",
}
NEEDS_TTL = 6 * 3600        # 确定性结论挂 6 小时，到期给一次自愈机会，不永久静默
FP = os.environ.get("D_REACH_FP") or ""

# 脚本改过 → 旧的「这路坏了」结论可能已不成立，作废重测
for _k, _v in health.items():
    if isinstance(_v, dict) and _v.get("fp") and FP and _v["fp"] != FP:
        for _f in ("suspend_until", "suspend_secs", "code", "streak_fail"):
            _v.pop(_f, None)

ROUND = []          # 本轮每路的结果，最后写进 history.jsonl
def mark(key, status, code=None):
    """记「失败性质 + 连败次数 + 成败时间 + 挂起到期」。skip 不计失败，避免本轮没请求把通道判死。

    自愈类连败 ≥3 进退避：10 分钟 → 30 分钟 → 2 小时封顶；
    确定性类（NEEDS）首次失败就挂 6 小时，并在输出里点名该做什么。
    到期自动重试一次：成功清零、失败继续升级。通道不会「跳过→不跑→永不成功」死锁。
    """
    v = health.setdefault(key, {"streak_fail": 0})
    ROUND.append({"key": key, "status": status})
    if FP:
        v["fp"] = FP
    if status == "ok":
        v["streak_fail"] = 0
        v["last_ok"] = now_iso
        for f in ("suspend_until", "suspend_secs", "code"):   # 成功即解除挂起
            v.pop(f, None)
    elif status == "fail":
        v["last_fail"] = now_iso
        code = code or "upstream"
        v["code"] = code
        if code in NEEDS:
            secs = NEEDS_TTL
        else:
            v["streak_fail"] = v.get("streak_fail", 0) + 1
            n = v["streak_fail"]
            secs = BACKOFF[min(n - 3, len(BACKOFF) - 1)] if n >= 3 else 0
        if secs:
            v["suspend_until"] = (
                datetime.now(timezone.utc) + timedelta(seconds=secs)
            ).isoformat(timespec="seconds")
            v["suspend_secs"] = secs

total, okc, zero = 0, 0, 0
txt_only = 0        # 只给 AI 摘要、没有来源链接的路数（千帆），不能算「有结果」

# ---------- 跨源合并：先把每路输出缓冲住，最后统一排序 ----------
# 同一 URL 在 3 个源都出现就重复 3 遍，读者得自己判可信度。SearXNG 的做法是全局合并：
# 同 URL 只留一条，按「被几个源同时排到前面」打分（score = 命中源数 × Σ 权重/名次）。
# 多个独立源都排前面的才是真信号。分节视图保留在合并段之后，不缺信息。
CHAN_OUT = []       # 各通道的 markdown 块（缓冲区）
MERGE_ROWS = []     # (key, name, title, url, snippet, rank)
CH_W = {            # 通道权重：直接给正文的源比只给标题的高
    "serper": 1.0, "tavily": 1.0, "fcs": 1.0, "fcdev": 1.0, "tf": 1.0,
    "exa": 1.0, "qianfan": 1.0, "fcres": 1.0,
    "langsearch": 0.9, "parallel": 0.9, "youcom": 0.9, "anysearch": 1.0,
    "oalex": 0.8, "crossref": 0.8, "se": 0.8,
    "hn": 0.7,
    "jj": 0.6, "wiki": 0.6, "segfault": 0.6, "zhihu": 0.8, "zhihuall": 0.9, "zhihuhot": 0.4,
    "brave": 1.0,
}
DW = 0.7

_orig_print = print

def cprint(*a, **k):
    """循环内的 print：写进缓冲区，不立即上屏（等合并段算完再统一输出）。"""
    if k.get("file") not in (None, sys.stdout):
        _orig_print(*a, **k)          # stderr 等旁路，不缓冲
        return
    import io as _io
    _b = _io.StringIO()
    k2 = dict(k); k2["file"] = _b
    _REAL_PRINT(*a, **k2)
    CHAN_OUT.append(_b.getvalue())
    _OUT.append(_b.getvalue())        # 历史详情仍要完整

print = cprint
skipped, failed = [], []
for key, name, note, fn, deep_only in SECTIONS:
    if ONLY and key not in ONLY:
        continue                      # 本轮没请求这条路 → 不渲染（≠无响应）
    if key in DISABLED:
        continue                      # 不在本轮启用清单
    # --on 显式点名时，deep 档通道也要渲染，否则点名结果会被丢掉
    if deep_only and DEEP != "1" and key not in [c for c in (ON or "").split(",") if c] \
            and not os.path.exists(os.path.join(tmp, "skip." + key)):
        continue
    skip = read_skip(key)
    if skip == "health":
        v = health.get(key) or {}
        bad = v.get("streak_fail", 0)
        _code = v.get("code") or ""
        until = v.get("suspend_until")
        left = ""
        if until:
            try:
                delta = (datetime.fromisoformat(until) - datetime.now(timezone.utc)).total_seconds()
                if delta > 0:
                    left = f"，{int(delta // 60) + 1} 分钟后自动重试"
            except Exception:
                pass
        if _code in NEEDS:
            print(f"### 🔇 {name} —— {NEEDS_TITLE.get(_code, '通道异常')}，先不打了{left}"
                  f"（{NEEDS[_code]}；`--force` 可强跑）\n")
        else:
            print(f"### 🔇 {name} —— 连续失败 {bad} 次，挂起中{left}（`--force` 可强跑）\n")
        skipped.append(key); mark(key, "skip")
        continue
    if skip == "key":
        print(f"### 🔇 {name} —— 未配置 API key（写入 `~/.config/agents/env` 即解锁）\n")
        skipped.append(key); mark(key, "skip")
        continue
    if skip == "quota":
        print(f"### 🔇 {name} —— 已越免费线，本轮自动跳过\n")
        skipped.append(key); mark(key, "skip")
        continue
    if skip == "cjk":
        print(f"### 🔇 {name} —— 检测到中文 query，本轮自动跳过（这个通道只认英文词："
              f"中文打过去恒 0 命中，或只匹配上\"配置/安装\"这类字面词返回噪声；"
              f"调用方给出英文检索词就会自动放行）\n")
        skipped.append(key); mark(key, "skip")
        continue
    if skip and skip.startswith("cooldown:"):
        print(f"### 🔇 {name} —— {skip.split(':', 1)[1]} 分钟内刚搜过"
              f"（这类通道连打会触发风控验证码，所以设了最小间隔）\n")
        skipped.append(key); mark(key, "skip")
        continue
    if skip == "no-english":
        # 插件侧会包一层「跳过（note）」，这里不要再写「本轮跳过」否则双重嵌套
        print(f"### 🔇 {name} —— query 里没有英文关键词（GitHub 只认英文，中文搜不到）\n")
        skipped.append(key); mark(key, "skip")
        continue
    if skip == "captcha":
        print(f"### 🔇 {name} —— 平台风控要验证码（等几小时或换个词；不影响其余通道）\n")
        skipped.append(key); mark(key, "skip")
        continue
    if skip == "not-configured":
        v = health.get(key)
        if isinstance(v, dict):
            v["streak_fail"] = 0
            v.pop("suspend_until", None)
            v.pop("suspend_secs", None)
            v.pop("code", None)
        detail = load_text(key + ".txt") or "本机未配置此渠道。"
        print(f"### 🔇 {name} —— 未配置，已跳过且不计失败：{detail.strip()[:180]}\n")
        skipped.append(key); mark(key, "skip")
        continue
    if skip == "err":
        detail = load_text(key + ".txt") or ""
        if key == "xhs":
            print(f"### ⚠️ {name} —— xhs CLI 搜索失败：{detail.strip()[:200]}\n")
            failed.append(key); mark(key, "fail")
        else:
            print(f"### ⚠️ {name} —— 本机依赖不可用：{detail.strip()[:200]}\n")
            failed.append(key); mark(key, "fail", "setup")
        continue
    try:
        rows = fn()
    except Exception as e:
        rows = None
        print(f"<!-- {key} 解析异常: {type(e).__name__}: {str(e)[:120]} -->", file=sys.stderr)
    code = http_code(key)
    if code and code not in ("200", "000") and (rows is None or rows == [] or isinstance(rows, tuple)):
        # 状态码本身就是结论：429 是限流（再打更糟）、401/403 是凭据、404 是端点没了，
        # 这三类都算确定性失败；5xx 才当上游抖动、靠退避自愈。
        _cls = ("ratelimit" if code == "429" else
                "auth" if code in ("401", "403") else
                "notfound" if code == "404" else "upstream")
        print(f"### ⚠️ {name} —— HTTP {code}（{NEEDS_TITLE.get(_cls, '上游异常')}，不是「没搜到」）\n")
        failed.append(key); mark(key, "fail", _cls)
        continue
    if isinstance(rows, str):                      # 千帆文本
        body = rows.strip()
        if body:
            okc += 1; txt_only += 1; mark(key, "ok")
            print(f"### 💬 {name}\n_{note}_\n\n{body[:1800]}\n")
        else:
            print(f"### ❌ {name} —— 无返回\n"); failed.append(key); mark(key, "fail", "empty")
    elif isinstance(rows, tuple):                  # ("ERR", msg)
        _msg = str(rows[1])
        _low = _msg.lower()
        _cls = "timeout" if ("超时" in _msg or "timed out" in _low or "timeout" in _low) else "upstream"
        print(f"### ⚠️ {name} —— {_msg}\n"); failed.append(key); mark(key, "fail", _cls)
    elif rows is None:
        print(f"### ❌ {name} —— 通道无响应 / 超时\n"); failed.append(key); mark(key, "fail", "timeout")
    elif not rows:
        zero += 1; mark(key, "ok")
        print(f"### ⚪ {name} —— 通道正常，0 命中\n")
    else:
        okc += 1; mark(key, "ok")
        total += len(rows)
        print(f"### ✅ {name}\n_{note}_\n")
        for rank, (t, u, x) in enumerate(rows):
            print(f"- [{t}]({u})" + (f" — {x}" if x else ""))
            MERGE_ROWS.append((key, name, t, u, x, rank))
        print()

# ---------- 恢复直输出：先出合并段，再放分节 ----------
print = _orig_print

def norm_url(u):
    """URL 归一化：去 fragment / utm 类参数 / www 前缀 / 尾斜杠，用于跨源判重。"""
    try:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        s = urlsplit(str(u).strip())
        host = (s.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        q = [(k, v) for k, v in parse_qsl(s.query)
             if not k.lower().startswith(("utm_", "ref", "fbclid", "gclid", "spm"))
             and k.lower() not in ("rankingid", "ranking_id")]
        path = s.path.rstrip("/") or "/"
        return urlunsplit(((s.scheme or "https").lower(), host, path, urlencode(q), ""))
    except Exception:
        return str(u).strip().lower()

agg = {}
for key, name, t, u, x, rank in MERGE_ROWS:
    nu = norm_url(u)
    d = agg.get(nu)
    if d is None:
        # url 存归一化后的：判重靠它，展示也靠它（原 URL 常带 utm/rankingId 这类跟踪参数）
        d = agg[nu] = {"title": t, "url": nu, "snippet": x or "", "hits": []}
    d["hits"].append((key, rank))
    if not d["snippet"] and x:
        d["snippet"] = x

for d in agg.values():
    n = len(d["hits"])
    d["score"] = n * sum(CH_W.get(k, DW) / (r + 1) for k, r in d["hits"])

multi = sorted((d for d in agg.values() if len(d["hits"]) >= 2),
               key=lambda d: -d["score"])

if len(multi) >= 3:      # 少于 3 条说明各路本来就各说各话，合并段没信息量
    print(f"### 🔀 跨源共识（{len(multi)} 条被 ≥2 个源同时排到前面）\n")
    for d in multi[:10]:
        srcs = " · ".join(f"{k}#{r + 1}" for k, r in sorted(d["hits"], key=lambda h: h[1]))
        print(f"- **[{d['title']}]({d['url']})** — {len(d['hits'])} 源（{srcs}）"
              + (f" — {d['snippet']}" if d["snippet"] else ""))
    print()

# 分节视图（保留「哪路出的」这个维度，合并段看不到的细节靠它）
for _blk in CHAN_OUT:
    _REAL_PRINT(_blk, end="")

save_health(health)
def _left(v):
    """挂起还剩几秒；None = 没挂起（含已到期）。"""
    u = v.get("suspend_until")
    if not u:
        return None
    try:
        d = (datetime.fromisoformat(u) - datetime.now(timezone.utc)).total_seconds()
        return int(d) if d > 0 else None
    except Exception:
        return None

weak, need = [], []
_active_keys = {_s[0] for _s in SECTIONS}
for k, v in health.items():
    if k not in _active_keys:      # 已从档位移除的通道（如 bd）不再报
        continue
    if not isinstance(v, dict):
        continue
    left = _left(v)
    _code = v.get("code") or ""
    if _code in NEEDS:
        # 确定性结论：不是「次数到了」，是「这条路需要人处理」，措辞必须不同
        need.append(f"{k}（{NEEDS_TITLE.get(_code, '异常')}"
                    + (f"，{left // 60 + 1} 分钟后重试" if left else "") + "）")
    elif v.get("streak_fail", 0) >= 3:
        weak.append(
            f"{k}({v['streak_fail']} 连败，挂起 {left // 60 + 1} 分钟)" if left
            else f"{k}({v['streak_fail']} 连败，已到期下次会重试)"
        )
_head = (
    f"{okc - txt_only} 路有结果，共 {total} 条来源"
    if total
    else "0 条来源" + (f"（{txt_only} 路只给了 AI 摘要，没有来源链接）" if txt_only else "")
)
print(f"---\n**汇总**：{_head}"
      + (f"；{zero} 路 0 命中" if zero else "")
      + (f"；{len(failed)} 路失败（{ '、'.join(failed) }）" if failed else "")
      + (f"；{len(skipped)} 路跳过（{ '、'.join(skipped) }）" if skipped else "") + "。\n")
if weak:
    print(f"**通道健康**：{'、'.join(weak)}。\n")
if need:
    print(f"**要你出手**：{'、'.join(need)}。\n")
print("**下一步**：把上面冒出的人名/机构/版本号/术语回灌成第二轮（追深），"
      "再单独跑一轮反证（`<主题> 缺点/失败/不推荐/争议/vs 替代`）。"
      "要更全就 `fanout.sh \"<query>\" --deep`（追加 LangSearch / Exa / Firecrawl-Research）。")

# ---------- 历史记录 ----------
# 网关和插件都靠它显示「最近查了什么、谁发起的、哪几路给了结果」。
# 写失败不影响本轮输出：历史只是附加物。
try:
    hist = pathlib.Path(os.path.expanduser("~/.agent-reach/history.jsonl"))
    hist.parent.mkdir(parents=True, exist_ok=True)
    try:
        secs = round(time.time() - float(os.environ.get("D_REACH_T0") or 0), 1)
    except Exception:
        secs = 0.0
    rec = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "query": Q,
        "on": ON or "",
        "deep": DEEP == "1",
        "source": os.environ.get("D_REACH_SOURCE") or "cli",
        "secs": secs,
        "ok": okc, "zero": zero, "fail": len(failed), "skip": len(skipped),
        "results": ROUND,
    }
    with hist.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    # 只留最近 200 条，别让文件无限长
    keep = hist.read_text(encoding="utf-8").splitlines()[-200:]
    hist.write_text("\n".join(keep) + "\n", encoding="utf-8")
    # 每轮的完整 markdown 落一份，网关「点历史看详情」用
    # 文件名用 ts 前缀（精度到秒，与 rec.ts 对得上）；留 30 份
    rdir = pathlib.Path(os.path.expanduser("~/.agent-reach/rounds"))
    rdir.mkdir(parents=True, exist_ok=True)
    stamp = rec["ts"].replace("-", "").replace(":", "").replace("T", "-").split("+")[0]
    (rdir / f"{stamp}.md").write_text("".join(_OUT), encoding="utf-8")
    olds = sorted(rdir.glob("*.md"))
    for o in olds[:-30]:
        o.unlink(missing_ok=True)
except Exception:
    pass
PY

# 跑完自动校准官方额度（本地计数 ≠ 厂商剩余；校准结果写入 quota.json 的 _official 段）
# 失败只写 stderr，不阻塞、不影响本轮结果。D_REACH_SKIP_PROBE=1 可关。
[ "${D_REACH_SKIP_PROBE:-0}" = "1" ] || python3 "$DIR/quota_probe.py" --quiet 2>&1 >/dev/null | sed 's/^/  /' || true
