#!/usr/bin/env bash
# fanout.sh —— d-reach 并行铺开器（「全加全扩」落地件）
#
# 一条命令并发 9 路免费免 Key 通道；--deep 追加 LangSearch / Exa /
# Firecrawl-Research / BrightData-Google / V2EX。
# 轮 1 发现一律走它，别一条一条串行试：
#   实测 3 路串行 2.95s vs 并行 1.30s —— 铺开耗时 ≈ 最慢一路，与路数基本无关。
#
# 用法:
#   fanout.sh "<query>"              # 默认档：9 路免费通道（含中文/英文/学术/排障/长尾）
#   fanout.sh "<query>" --deep       # 深调研：追加 5 路付费/限 token 通道
#   fanout.sh "<query>" --n 8        # 每路最多列几条（默认 5）
#   fanout.sh "<query>" --on bing,hn,oalex   # 只跑指定通道（见下方 CHANNELS）
#   fanout.sh --list                 # 列出通道名
#
# 记账: 免费免 Key 通道不记账；deep 下 LangSearch/Exa/BrightData 调用前自动
#       `quota.py use`，退出码 1（越免费线）→ 自动跳过该路并在输出里标注，
#       不拖死其他路。百度千帆由它自己的计数器记账，这里不双扣。
#       tf（TinyFish）需 TINYFISH_API_KEY 但 search $0.00/次 → 只 gate key 不记账。
#
# 通道命名（--on 用）:
#   se hn jj oalex crossref segfault fcdev qianfan tf | deep: langsearch exa fcres bd
#
# 已退役通道（别往回加）：
#   · 博客园 zzk.cnblogs.com —— 302→zzkx 后返回 5.7KB 壳页、0 结果
#   · V2EX search —— /search?q= 302→/go/search，返回节点帖子列表、与 query 无关（假结果）
#   中文社区长尾现在靠 掘金 + SegmentFault + cn.bing 站内。

set -u

DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
QUOTA="$DIR/quota.py"
SKILLS="$HOME/.agents/skills"; [ -d "$SKILLS" ] || SKILLS=/var/minis/skills
BAIDU="$SKILLS/baiduaisearchwithquota/scripts"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"

# ---------- 参数 ----------
Q=""; DEEP=0; N=5; ON=""; FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --deep) DEEP=1 ;;
    --n) shift; N="${1:-5}" ;;
    --on) shift; ON="${1:-}" ;;
    --force) FORCE=1 ;;   # 忽略健康状态，强制跑（调试/复检用）
    --list) python3 - "$0" <<'PY'
import re, sys
src = open(sys.argv[1], encoding='utf-8').read()
body = src.split('SECTIONS = [', 1)[1].split('\n]', 1)[0]
for entry in re.split(r'\n(?=    \()', body):
    m = re.match(r'\s*\("([a-z]+)",\s*"([^"]+)"', entry)
    if not m:
        continue
    d = re.search(r',\s*(True|False)\s*\)', entry)
    deep = bool(d and d.group(1) == 'True')
    key, name = m.groups()
    print(f"  {key:10s} {'deep' if deep else 'base':4s}  {name}")
print("\n  用法: fanout.sh \"<query>\" [--deep] [--n N] [--on key1,key2]")
PY
      exit 0 ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) [ -z "$Q" ] && Q="$1" ;;
  esac
  shift
done
if [ -z "$Q" ]; then echo "usage: fanout.sh \"<query>\" [--deep] [--n N] [--on chans]"; exit 2; fi

# --on 拼写校验：静默全跑比报错更坑（本想只跑 2 路，结果震了 10 路还扣额度）
if [ -n "$ON" ]; then
  KNOWN="qianfan fcdev se hn jj segfault oalex crossref tf langsearch exa fcres bd"
  _bad=""
  for _c in $(echo "$ON" | tr ',' ' '); do
    case " $KNOWN " in *" $_c "*) ;; *) _bad="$_bad $_c" ;; esac
  done
  if [ -n "$_bad" ]; then
    echo "[fanout] 未知通道:$_bad" >&2
    echo "[fanout] 可用: $KNOWN" >&2
    exit 2
  fi
fi
case "$N" in ''|*[!0-9]*) echo "[fanout] --n 必须是正整数" >&2; exit 2 ;; esac

# --on 里点名了 deep 专属通道 → 自动按 deep 跑（省得再写一遍 --deep）
case ",$ON," in
  *,langsearch,*|*,exa,*|*,fcres,*|*,bd,*) DEEP=1 ;;
esac

# CJK 检测：Crossref / OpenAlex 对中文 query 相关性差（c2 实测：中文 query 返回「水质监测站 /
# 变电站 / 暖通」这类匹配到"配置/安装"字样的噪声）→ 中文 query 时自动跳过 Crossref
CJK=$(python3 -c 'import sys,re;print("1" if re.search(r"[\u4e00-\u9fff\u3400-\u4dbf]",sys.argv[1]) else "0")' "$Q" 2>/dev/null || echo 0)

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
HEALTH="${D_REACH_HEALTH:-$HOME/.agent-reach/channels.json}"
HEALTH_BAD=$(python3 - "$HEALTH" <<'PY' 2>/dev/null
import json, sys
bad = []
try:
    h = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    h = {}
for k, v in h.items():
    if isinstance(v, dict) and v.get("streak_fail", 0) >= 3:
        bad.append(k)
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
want() { [ -z "$ON" ] && return 0; case ",$ON," in *",$1,"*) return 0;; esac; return 1; }

# ---------- 免费免 Key 通道 ----------
f_se() {     # StackExchange 排障
  # q 是全词 AND 匹配：长句/长中文会 0 命中 → 只取前 5 个词
  # shellcheck disable=SC2086
  set -- $Q
  SEQ="${1:-} ${2:-} ${3:-} ${4:-} ${5:-}"
  curl -s --compressed --max-time 15 -G "https://api.stackexchange.com/2.3/search/advanced" \
    --data-urlencode "order=desc" --data-urlencode "sort=relevance" \
    --data-urlencode "q=$SEQ" --data-urlencode "site=stackoverflow" \
    --data-urlencode "pagesize=5" -o "$TMP/se.json" -w '%{http_code}' > "$TMP/se.http" 2>/dev/null
}
f_hn() {     # HN 深技术讨论
  curl -s --max-time 12 -G "https://hn.algolia.com/api/v1/search" \
    --data-urlencode "query=$Q" --data-urlencode "hitsPerPage=5" -o "$TMP/hn.json" -w '%{http_code}' > "$TMP/hn.http" 2>/dev/null
}
f_jj() {     # 掘金 中文技术长尾
  curl -s --max-time 12 -H 'Content-Type: application/json' -X POST \
    "https://api.juejin.cn/search_api/v1/search" \
    -d "$(python3 -c 'import json,sys;print(json.dumps({"key_word":sys.argv[1],"id_type":0,"cursor":"0","limit":5,"search_type":0}))' "$Q")" \
    -o "$TMP/jj.json" -w '%{http_code}' > "$TMP/jj.http" 2>/dev/null
}
f_oalex() {  # OpenAlex 学术
  curl -s --max-time 12 -G "https://api.openalex.org/works" \
    --data-urlencode "search=$Q" --data-urlencode "per-page=5" \
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
  curl -sL --compressed --max-time 14 -A "$UA" -G "https://segmentfault.com/search" \
    --data-urlencode "q=$Q" -o "$TMP/segfault.html" -w '%{http_code}' > "$TMP/segfault.http" 2>/dev/null
}
f_fcdev() {  # Firecrawl Developer Index（70M+ 一手源，⭐ 免 key）
  curl -s --max-time 18 -G "https://api.firecrawl.dev/v2/search/developer" \
    --data-urlencode "query=$Q" --data-urlencode "k=5" -o "$TMP/fcdev.json" -w '%{http_code}' > "$TMP/fcdev.http" 2>/dev/null
}
f_qianfan() { # 百度千帆：生成式综合答案（非来源链接！）
  [ -d "$BAIDU" ] || { echo "err" > "$TMP/skip.qianfan"; echo "千帆技能目录缺失（$BAIDU）" > "$TMP/qianfan.txt"; return; }
  timeout 50 python3 "$BAIDU/smart_search.py" search "$Q" \
    > "$TMP/qianfan.raw" 2> "$TMP/qianfan.err"
  _qrc=$?
  sed -e '/^--- 配额状态 ---/,$d' -e '/^\[调度\]/d' "$TMP/qianfan.raw" > "$TMP/qianfan.txt" 2>/dev/null
  # 千帆报错时绝不能把错误文本当「AI 答案」渲染：报错、空输出、或 stderr 有内容 → 标 err
  if [ "$_qrc" != "0" ] || [ ! -s "$TMP/qianfan.txt" ] || [ -s "$TMP/qianfan.err" ]; then
    echo "err" > "$TMP/skip.qianfan"
    head -c 300 "$TMP/qianfan.err" >> "$TMP/qianfan.txt" 2>/dev/null
  fi
}

f_tf() {   # TinyFish Search（官方 hosted MCP，$0/次；JSON-RPC tools/call search）
  gate tinyfish || return 0
  TF_KEY="$TF_KEY" python3 - "$Q" > "$TMP/tf.json" 2>"$TMP/tf.err" <<'PYEOF'
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
    -d "$(python3 -c 'import json,sys;print(json.dumps({"query":sys.argv[1],"count":20}))' "$Q")" \
    -o "$TMP/langsearch.json" -w '%{http_code}' > "$TMP/langsearch.http" 2>/dev/null
  [ "$(cat "$TMP/langsearch.http" 2>/dev/null)" = "200" ] && charge langsearch
}
f_exa() {
  gate exa || return 0
  curl -s --max-time 20 -X POST "https://api.exa.ai/search" \
    -H "x-api-key: $EXA_KEY" -H 'Content-Type: application/json' \
    -d "$(python3 -c 'import json,sys;print(json.dumps({"query":sys.argv[1],"numResults":10}))' "$Q")" \
    -o "$TMP/exa.json" -w '%{http_code}' > "$TMP/exa.http" 2>/dev/null
  [ "$(cat "$TMP/exa.http" 2>/dev/null)" = "200" ] && charge exa
}
f_fcres() {
  gate fcres || return 0
  curl -s --max-time 20 -H "Authorization: Bearer $FC_KEY" -G \
    "https://api.firecrawl.dev/v2/search/research/papers" \
    --data-urlencode "query=$Q" --data-urlencode "k=5" \
    -o "$TMP/fcres.json" -w '%{http_code}' > "$TMP/fcres.http" 2>/dev/null
}
f_bd() {
  gate brightdata || return 0
  # ⚠️ format 是必填（漏了返 400 validation）—— scrub.md 示例就是 format+data_format 两个都给
  # ⚠️ 超时压到 25s：c2 实测 5 次调用 1×400(漏format)/1×500/2×50s 超时，而它是 deep 里最不
  #    稳定的一路，一次超时就把整轮从 ~12s 拖到 50s+。要么快回，要么让位。
  curl -s --max-time 25 -X POST "https://api.brightdata.com/request" \
    -H "Authorization: Bearer $BD_KEY" -H 'Content-Type: application/json' \
    -d "$(python3 -c 'import json,sys,os,urllib.parse;print(json.dumps({"zone":os.environ.get("BRIGHTDATA_ZONE","mcp_unlocker"),"format":"raw","data_format":"parsed_light","url":"https://www.google.com/search?q="+urllib.parse.quote(sys.argv[1])+"&num=10&gl=cn"}))' "$Q")" \
    -o "$TMP/bd.json" -w '%{http_code}' > "$TMP/bd.http" 2>/dev/null
  [ "$(cat "$TMP/bd.http" 2>/dev/null)" = "200" ] && charge brightdata
}
# 已退役通道（2026-09-25 实测，别往回加）：
#   · V2EX /search?q= —— 302 → /go/search，返回「搜索引擎技术研究」节点帖子，与 query 无关
#     （会给假结果；假结果比无响应更毒，故整路移除）
#   · 博客园 zzk.cnblogs.com —— 302→zzkx 后返回 5.7KB 壳页、0 结果
#   中文社区长尾现在靠 掘金 + SegmentFault；cn.bing 已投毒、知乎 403、微博需登录 → 走千帆快照。

# ---------- 并发发射 ----------
launch() {   # $1 = 函数名；失败不拖垮整体
  fn="$1"; key="${fn#f_}"
  want "$key" || return 0
  # 健康状态：连续失败 ≥3 次的路默认不再发请求（除非 --force 或 --on 显式点名）
  if [ "$FORCE" != "1" ] && [ -z "$ON" ]; then
    case " $HEALTH_BAD " in
      *" $key "*) echo "health" > "$TMP/skip.$key"; return 0 ;;
    esac
  fi
  ( "$fn" ) &
}
for fn in f_se f_hn f_jj f_oalex f_crossref f_segfault f_fcdev f_qianfan f_tf; do launch "$fn"; done
if [ "$DEEP" = 1 ]; then
  for fn in f_langsearch f_exa f_fcres f_bd; do launch "$fn"; done
fi
wait

# ---------- 渲染 ----------
python3 - "$TMP" "$Q" "$N" "$DEEP" "$ON" <<'PY'
import json, os, re, sys, html, pathlib
from datetime import datetime, timezone

tmp, Q, N, DEEP, ON = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]
N = max(1, min(N, 20))
ONLY = {c for c in ON.split(",") if c} if ON else None   # None = 全跑

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

def r_bd():
    d = load_json("bd.json")
    if d is None:
        return None
    return rowify(walk_generic(d))

# (key, 通道名, 说明, 解析函数, 仅 deep)
SECTIONS = [
    ("qianfan",  "百度千帆（生成式综合答案）",
     "⚠️ AI 浓缩回答、非来源链接 —— 关键结论必须另找一手源验证",
     lambda: load_text("qianfan.txt"), False),
    ("fcdev",    "Firecrawl Developer Index（编程一手源 70M+）", "免 Key 不限量", r_fcdev, False),
    ("se",       "StackExchange（报错排障）", "免 Key 不限量", r_se, False),
    ("hn",       "Hacker News（深技术讨论）", "免 Key 不限量", r_hn, False),
    ("jj",       "掘金（中文技术长尾）", "免 Key 不限量", r_jj, False),
    ("segfault", "SegmentFault（中文技术长尾）", "免 Key 不限量", r_segfault, False),
    ("oalex",    "OpenAlex（学术 2.5 亿篇）", "免 Key 不限量", r_oalex, False),
    ("crossref", "Crossref（DOI 权威元数据）", "免 Key 不限量", r_crossref, False),
    ("tf",      "TinyFish Search（官方 hosted MCP，$0/次）", "需 TINYFISH_API_KEY", r_tf, False),
    ("langsearch", "LangSearch count=20（时效/限域）", "每日 token 额度；本技能自设 50/日保守线，已 quota.py use", r_langsearch, True),
    ("exa",      "Exa（语义/英文）", "已 quota.py use", r_exa, True),
    ("fcres",    "Firecrawl Research Index（学术论文全文）", "需 key、不记账（官方论文端点免费）", r_fcres, True),
    ("bd",       "BrightData Google（全网覆盖）", "已 quota.py use", r_bd, True),
    # V2EX 已退役（会返回与 query 无关的假结果），见文件头「已退役通道」
]
SKIPMAP = {"langsearch": "langsearch", "exa": "exa", "bd": "brightdata", "fcres": "fcres", "tf": "tinyfish"}

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

_default_n = sum(1 for _s in SECTIONS if not _s[4])
_label = (f"deep 深调研档（{len(SECTIONS)} 路）" if DEEP == "1" else f"默认档（{_default_n} 路）")
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

def mark(key, status):
    """ok / fail / skip。skip 不计失败，避免「本轮没请求」把通道判死。"""
    v = health.setdefault(key, {"ok": 0, "fail": 0, "streak_fail": 0})
    if status == "ok":
        v["ok"] = v.get("ok", 0) + 1
        v["streak_fail"] = 0
        v["last_ok"] = now_iso
    elif status == "fail":
        v["fail"] = v.get("fail", 0) + 1
        v["streak_fail"] = v.get("streak_fail", 0) + 1
        v["last_fail"] = now_iso
    else:
        v["last_skip"] = now_iso

total, okc, zero = 0, 0, 0
skipped, failed = [], []
for key, name, note, fn, deep_only in SECTIONS:
    if ONLY and key not in ONLY:
        continue                      # 本轮没请求这条路 → 不渲染（≠无响应）
    if deep_only and DEEP != "1" and not os.path.exists(os.path.join(tmp, "skip." + key)):
        continue
    skip = read_skip(key)
    if skip == "health":
        bad = (health.get(key) or {}).get("streak_fail", 0)
        print(f"### 🔇 {name} —— 连续失败 {bad} 次，已按健康状态跳过（`--force` 可强跑）\n")
        skipped.append(name); mark(key, "skip")
        continue
    if skip == "key":
        print(f"### 🔇 {name} —— 未配置 API key（写入 `~/.config/agents/env` 即解锁）\n")
        skipped.append(name); mark(key, "skip")
        continue
    if skip == "quota":
        print(f"### 🔇 {name} —— 已越免费线，本轮自动跳过\n")
        skipped.append(name); mark(key, "skip")
        continue
    if skip == "cjk":
        print(f"### 🔇 {name} —— 检测到中文 query，本轮自动跳过（Crossref 对中文相关性差："
              f"实测会返回「水质监测站 / 变电站 / 暖通」这类匹配上\"配置/安装\"字样的噪声）\n")
        skipped.append(name); mark(key, "skip")
        continue
    if skip == "err":
        detail = load_text(key + ".txt") or ""
        print(f"### ⚠️ {name} —— 本机依赖不可用：{detail.strip()[:200]}\n")
        failed.append(name); mark(key, "fail")
        continue
    try:
        rows = fn()
    except Exception as e:
        rows = None
        print(f"<!-- {key} 解析异常: {type(e).__name__}: {str(e)[:120]} -->", file=sys.stderr)
    code = http_code(key)
    if code and code not in ("200", "000") and (rows is None or rows == [] or isinstance(rows, tuple)):
        print(f"### ⚠️ {name} —— HTTP {code}（参数/凭据/限流问题，不是「没搜到」）\n")
        failed.append(name); mark(key, "fail")
        continue
    if isinstance(rows, str):                      # 千帆文本
        body = rows.strip()
        if body:
            okc += 1; mark(key, "ok")
            print(f"### 💬 {name}\n_{note}_\n\n{body[:1800]}\n")
        else:
            print(f"### ❌ {name} —— 无返回\n"); failed.append(name); mark(key, "fail")
    elif isinstance(rows, tuple):                  # ("ERR", msg)
        print(f"### ⚠️ {name} —— {rows[1]}\n"); failed.append(name); mark(key, "fail")
    elif rows is None:
        print(f"### ❌ {name} —— 通道无响应 / 超时\n"); failed.append(name); mark(key, "fail")
    elif not rows:
        zero += 1; mark(key, "ok")
        print(f"### ⚪ {name} —— 通道正常，0 命中\n")
    else:
        okc += 1; mark(key, "ok")
        total += len(rows)
        print(f"### ✅ {name}\n_{note}_\n")
        for t, u, x in rows:
            print(f"- [{t}]({u})" + (f" — {x}" if x else ""))
        print()

save_health(health)
weak = [f"{k}({v.get('streak_fail', 0)} 连败)" for k, v in health.items()
        if isinstance(v, dict) and v.get("streak_fail", 0) >= 3]
print(f"---\n**汇总**：{okc} 路有结果，共 {total} 条来源"
      + (f"；{zero} 路 0 命中" if zero else "")
      + (f"；{len(failed)} 路失败（{ '、'.join(failed) }）" if failed else "")
      + (f"；{len(skipped)} 路跳过（{ '、'.join(skipped) }）" if skipped else "") + "。\n")
if weak:
    print(f"**通道健康**：{'、'.join(weak)} —— 下次默认跳过，可用 `--force` 强跑复检。\n")
print("**下一步**：把上面冒出的人名/机构/版本号/术语回灌成第二轮（追深），"
      "再单独跑一轮反证（`<主题> 缺点/失败/不推荐/争议/vs 替代`）。"
      "要更全就 `fanout.sh \"<query>\" --deep`（追加 LangSearch / Exa / Firecrawl-Research / BrightData）。")
PY

# 跑完自动校准官方额度（本地计数 ≠ 厂商剩余；校准结果写入 quota.json 的 _official 段）
# 失败只写 stderr，不阻塞、不影响本轮结果。D_REACH_SKIP_PROBE=1 可关。
[ "${D_REACH_SKIP_PROBE:-0}" = "1" ] || python3 "$DIR/quota_probe.py" --quiet 2>&1 >/dev/null | sed 's/^/  /' || true
