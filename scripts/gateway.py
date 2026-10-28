#!/usr/bin/env python3
"""d-reach 本地可视化网关（标准库，零依赖）。

  python3 scripts/gateway.py                 # 只绑 127.0.0.1，无需 key
  python3 scripts/gateway.py --lan           # 绑 0.0.0.0，局域网可访问，要 ?k=<key>
                                             # 且请求源 IP 必须在 127/192.168.5/10.7 段内

  GET  /                页面
  GET  /api/state       通道 + 额度状态
  POST /api/search      {"q":"...","deep":true,"on":"hn,exa"}

--lan 模式下 key 存在 ~/.agent-reach/gateway.key（首次自动生成，600）。
"""
import ipaddress
import json
import os
import re
import secrets
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SKILL = Path(__file__).resolve().parent.parent
FANOUT = SKILL / "scripts" / "fanout.sh"
DATA = Path.home() / ".agent-reach"
QUOTA = DATA / "quota.json"
HEALTH = DATA / "channels.json"
KEYFILE = DATA / "gateway.key"
PORT = int(os.environ.get("D_REACH_GATEWAY_PORT", "3426"))

LAN = False
KEY = ""

NO_KEY_PAGE = """<!doctype html><meta charset="utf-8"><title>需要访问 key</title>
<body style="background:#0b1220;color:#e2e8f0;font:14px/1.7 system-ui,'PingFang SC',sans-serif;
             display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0">
<div style="max-width:520px;padding:28px;border:1px solid #243149;border-radius:12px;background:#131c2e">
  <div style="font-size:16px;font-weight:600;margin-bottom:10px">需要访问 key</div>
  <p style="color:#7c8aa5;margin:0 0 12px">网关对局域网开放，必须带 <code>?k=&lt;key&gt;</code> 才能打开。</p>
  <p style="color:#7c8aa5;margin:0">key 存在机器上的 <code>~/.agent-reach/gateway.key</code>，
     或在能登录的终端跑 <code>cat ~/.agent-reach/gateway.key</code> 取。</p>
</div></body>"""
ALLOWED = [ipaddress.ip_network(n) for n in ("127.0.0.0/8", "192.168.5.0/24", "10.7.0.0/24")]

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>d-reach gateway</title>
<style>
  :root{--bg:#0b1220;--card:#131c2e;--line:#243149;--fg:#e2e8f0;--dim:#7c8aa5;
        --ok:#10b981;--warn:#f59e0b;--bad:#ef4444;--acc:#10b981}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);
       font:14px/1.6 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
  .wrap{max-width:1180px;margin:0 auto;padding:24px 20px 40px}
  header{display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap}
  h1{font-size:17px;margin:0;font-weight:600;letter-spacing:.01em}
  .dot{width:8px;height:8px;border-radius:50%;background:var(--ok)}
  .dot.bad{background:var(--bad)}
  .sub{color:var(--dim);font-size:12px}
  .grid{display:grid;grid-template-columns:1.12fr 1fr;gap:16px;margin-bottom:16px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 16px 10px;
        animation:rise .45s cubic-bezier(.16,1,.3,1) both}
  .grid .card:nth-child(2){animation-delay:.05s}
  .card:nth-of-type(3){animation-delay:.1s}
  @keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
  .card h2{font-size:12px;margin:0 0 10px;color:var(--dim);font-weight:600;letter-spacing:.06em;text-transform:uppercase}
  table{width:100%;border-collapse:collapse;font-size:12.5px}
  td,th{padding:6px;text-align:left;border-bottom:1px solid #1b2740}
  th{color:var(--dim);font-weight:500;font-size:11px;letter-spacing:.03em}
  td.n{text-align:right;font-variant-numeric:tabular-nums}
  tr:last-child td{border-bottom:none}
  .pill{display:inline-block;padding:1px 7px;border-radius:99px;font-size:11px;white-space:nowrap}
  .p-ok{background:#0d3b2c;color:#34d399}
  .p-warn{background:#3a2c0f;color:#fbbf24}
  .p-bad{background:#3a1414;color:#f87171}
  .p-idle{background:#20293d;color:#94a3b8}
  .bar{height:5px;background:#1b2740;border-radius:99px;overflow:hidden}
  .bar>i{display:block;height:100%;background:var(--acc)}
  .bar>i.warn{background:var(--warn)}
  .bar>i.bad{background:var(--bad)}
  .search{display:flex;gap:8px;flex-wrap:wrap}
  input[type=text]{flex:1;min-width:200px;background:#0e1729;border:1px solid var(--line);
    border-radius:8px;padding:10px 12px;color:var(--fg);font-size:14px}
  input[type=text]:focus{outline:none;border-color:var(--acc)}
  select,button{background:#0e1729;border:1px solid var(--line);border-radius:8px;
    padding:10px 12px;color:var(--fg);font-size:13px;cursor:pointer}
  button.primary{background:var(--acc);color:#04211a;border-color:var(--acc);font-weight:600}
  button:disabled{opacity:.55;cursor:default}
  #out{margin-top:12px;background:#0a1120;border:1px solid var(--line);border-radius:8px;
    padding:14px;min-height:110px;max-height:520px;overflow:auto;font-size:13px}
  #out.fresh{animation:fade .35s ease both}
  @keyframes fade{from{opacity:0}to{opacity:1}}
  #out h3{font-size:13px;margin:14px 0 6px;color:var(--acc);font-weight:600}
  #out h3:first-child{margin-top:0}
  #out ul{margin:6px 0 10px;padding-left:18px}
  #out li{margin:3px 0}
  #out a{color:#6ee7b7;text-decoration:none}
  #out a:hover{text-decoration:underline}
  #out .muted{color:var(--dim)}
  #out .warn{color:#fbbf24}
  #out .bad{color:#f87171}
  #out .sum{border-top:1px solid var(--line);margin-top:12px;padding-top:10px;font-size:12.5px}
  .meta{color:var(--dim);font-size:11.5px;margin-top:8px}
  @media(max-width:860px){
    .grid{grid-template-columns:1fr}
    .wrap{padding:16px 14px 32px}
    .tier{display:none}
    .card{padding:14px 12px 8px}
    td,th{padding:6px 4px}
    td:nth-child(4),th:nth-child(4){display:none}
  }
</style></head><body>
<div class="wrap">
  <header>
    <span class="dot" id="dot"></span>
    <h1>d-reach gateway</h1>
    <span class="sub" id="head"></span>
  </header>

  <div class="grid">
    <div class="card"><h2>通道健康</h2><table><thead><tr>
      <th>通道</th><th class="tier">档</th><th>状态</th><th class="n">连败</th><th>最后成功</th></tr></thead>
      <tbody id="chans"></tbody></table></div>

    <div class="card"><h2>额度</h2><table><thead><tr>
      <th>通道</th><th class="n">本地已用</th><th class="n">官方剩余</th></tr></thead>
      <tbody id="quota"></tbody></table>
      <div class="meta" id="qmeta"></div></div>
  </div>

  <div class="card">
    <h2>搜索</h2>
    <div class="search">
      <input type="text" id="q" placeholder="要查什么？回车直接跑" autocomplete="off">
      <select id="mode">
        <option value="base">默认档（9 路）</option>
        <option value="deep">deep（+4 路限额）</option>
      </select>
      <button class="primary" id="go">跑一轮</button>
    </div>
    <div class="meta" id="timing"></div>
    <div id="out"><span class="muted">还没有查询结果。输入关键词回车即可。</span></div>
  </div>
</div>

<script>
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const K = new URLSearchParams(location.search).get('k') || '';
const api = (p) => p + (K ? (p.includes('?') ? '&' : '?') + 'k=' + encodeURIComponent(K) : '');

function md2html(md){
  const out = [];
  for (const raw of md.split('\\n')) {
    const line = raw.trimEnd();
    if (!line.trim() || line.trim() === '---') continue;
    if (line.startsWith('### ') || line.startsWith('## ')) {
      out.push('<h3>' + esc(line.replace(/^#+ /, '')) + '</h3>'); continue;
    }
    if (line.startsWith('- ')) {
      let t = line.slice(2);
      const m = t.match(/^\\[([^\\]]+)\\]\\(([^)]+)\\)(.*)$/);
      t = m ? '<a href="' + m[2] + '" target="_blank" rel="noreferrer">' + esc(m[1]) + '</a>' + esc(m[3])
            : esc(t);
      out.push('<li>' + t.replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>') + '</li>');
      continue;
    }
    let cls = '';
    if (line.includes('🔇') || line.includes('⚪')) cls = 'muted';
    if (line.includes('⚠️') || line.includes('❌')) cls = 'warn';
    if (line.startsWith('**汇总**') || line.startsWith('**通道健康**') || line.startsWith('**下一步**')) cls = 'sum';
    out.push('<div class="' + cls + '">' + esc(line).replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>') + '</div>');
  }
  return out.join('');
}

let firstPaint = true;
async function refresh(){
  try {
    const s = await (await fetch(api('/api/state'))).json();
    $('#dot').className = 'dot';
    $('#head').textContent = s.channels.length + ' 路通道 · ' + s.quota.length + ' 个限额账本' +
      (s.lan ? ' · 局域网模式' : '');
    $('#chans').innerHTML = s.channels.map(c => {
      const st = c.streak_fail >= 3 ? ['p-bad','已停用'] : c.streak_fail > 0 ? ['p-warn','有失败']
               : c.last_ok ? ['p-ok','正常'] : ['p-idle','未使用'];
      return '<tr><td>' + esc(c.name) + '</td><td class="tier sub">' + c.tier + '</td>' +
             '<td><span class="pill ' + st[0] + '">' + st[1] + '</span></td>' +
             '<td class="n">' + c.streak_fail + '</td>' +
             '<td class="sub">' + (c.last_ok ? c.last_ok.slice(5,16).replace('T',' ') : '·') + '</td></tr>';
    }).join('');
    $('#quota').innerHTML = s.quota.map(q => {
      const pct = q.limit ? Math.min(100, q.used / q.limit * 100) : 0;
      const k = pct > 85 ? 'bad' : pct > 70 ? 'warn' : '';
      return '<tr><td>' + esc(q.svc) + '</td><td class="n">' + q.used +
             (q.limit ? ' / ' + q.limit : '') + '</td><td class="n sub">' + esc(q.official) + '</td></tr>' +
             '<tr><td colspan="3" style="padding:0 6px 8px"><div class="bar"><i class="' + k +
             '" style="width:' + pct + '%"></i></div></td></tr>';
    }).join('');
    $('#qmeta').textContent = s.official_at
      ? '官方校准 ' + s.official_at.slice(0,16).replace('T',' ') : '尚未校准';
  } catch (e) {
    $('#dot').className = 'dot bad';
    $('#head').textContent = '网关无响应';
  }
  firstPaint = false;
}

async function run(){
  const q = $('#q').value.trim();
  if (!q) return;
  const btn = $('#go'); btn.disabled = true; btn.textContent = '跑…';
  const t0 = Date.now();
  try {
    const r = await fetch(api('/api/search'), {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({q, deep: $('#mode').value === 'deep'})
    });
    const d = await r.json();
    const out = $('#out');
    out.innerHTML = d.ok ? md2html(d.markdown)
      : '<div class="bad">失败：' + esc(d.error || '未知错误') + '</div>';
    out.classList.remove('fresh'); void out.offsetWidth; out.classList.add('fresh');
    $('#timing').textContent = '耗时 ' + ((Date.now()-t0)/1000).toFixed(1) + 's（脚本 ' + d.secs + 's）';
  } catch (e) {
    $('#out').innerHTML = '<div class="bad">请求失败：' + esc(e) + '</div>';
  } finally {
    btn.disabled = false; btn.textContent = '跑一轮';
    refresh();
  }
}

$('#go').onclick = run;
$('#q').addEventListener('keydown', e => { if (e.key === 'Enter') run(); });
refresh();
setInterval(refresh, 5000);
</script></body></html>
"""


def load_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def channel_meta():
    try:
        out = subprocess.run(["bash", str(FANOUT), "--list"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception:
        return []
    items = []
    for line in out.splitlines():
        m = re.match(r"\s{2}([a-z]+)\s+(base|deep)\s+(.+)$", line)
        if m:
            items.append({"key": m.group(1), "tier": m.group(2), "name": m.group(3)})
    return items


def state():
    h = load_json(HEALTH)
    q = load_json(QUOTA)
    official = q.get("_official") or {}
    chans = []
    for meta in channel_meta():
        v = h.get(meta["key"]) or {}
        chans.append({
            "name": meta["name"], "key": meta["key"], "tier": meta["tier"],
            "streak_fail": v.get("streak_fail", 0),
            "last_ok": v.get("last_ok"), "last_fail": v.get("last_fail"),
        })
    quota_rows = []
    for svc, v in q.items():
        if svc.startswith("_") or not isinstance(v, dict):
            continue
        off = official.get(svc) or {}
        if off.get("state") == "ok" and svc == "firecrawl":
            s = f"{off.get('remaining')}/{off.get('total')}"
        elif off.get("state") == "ok" and svc == "tinyfish":
            s = f"{off.get('balance')} {off.get('currency')}"
        elif off.get("state") in ("unavailable", "no_permission"):
            s = "查不到"
        else:
            s = "·"
        quota_rows.append({"svc": svc, "used": v.get("monthly", 0),
                           "limit": {"firecrawl": 1000, "exa": 2500, "brightdata": 5000}.get(svc, 0),
                           "official": s})
    stamp = next((v.get("probed_at") for v in official.values() if v.get("probed_at")), None)
    return {"channels": chans, "quota": quota_rows, "official_at": stamp, "lan": LAN}


def search(body):
    q = (body.get("q") or "").strip()
    if not q:
        return {"ok": False, "error": "缺少 q"}
    cmd = ["bash", str(FANOUT), q]
    if body.get("deep"):
        cmd.append("--deep")
    if body.get("on"):
        cmd += ["--on", str(body["on"])]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "超时（180s）"}
    return {"ok": r.returncode == 0, "markdown": r.stdout,
            "secs": round(time.time() - t0, 1),
            "error": (r.stderr or "")[-400:] if r.returncode else None}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self):
        """--lan 模式：源 IP 必须在白名单且 key 匹配；只绑回环时全放行。"""
        if not LAN:
            return True
        try:
            ip = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return False
        if not any(ip in net for net in ALLOWED):
            return False
        given = self.headers.get("X-Gateway-Key")
        if not given:
            given = (parse_qs(urlparse(self.path).query).get("k") or [None])[0]
        return given == KEY

    def do_GET(self):
        path = urlparse(self.path).path
        if not self._allowed():
            if path == "/":
                return self._send(403, NO_KEY_PAGE, "text/html; charset=utf-8")
            return self._send(403, '{"error":"forbidden"}', "application/json")
        if path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif path == "/api/state":
            self._send(200, json.dumps(state(), ensure_ascii=False), "application/json")
        else:
            self._send(404, '{"error":"not found"}', "application/json")

    def do_POST(self):
        if urlparse(self.path).path != "/api/search":
            return self._send(404, '{"error":"not found"}', "application/json")
        if not self._allowed():
            return self._send(403, '{"error":"forbidden"}', "application/json")
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, '{"error":"bad json"}', "application/json")
        self._send(200, json.dumps(search(body), ensure_ascii=False), "application/json")


def main(argv):
    global LAN, KEY
    port = PORT
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    LAN = "--lan" in argv
    if LAN:
        DATA.mkdir(parents=True, exist_ok=True)
        if not KEYFILE.exists() or not KEYFILE.read_text().strip():
            KEYFILE.write_text(secrets.token_urlsafe(16), encoding="utf-8")
            KEYFILE.chmod(0o600)
        KEY = KEYFILE.read_text().strip()
    host = "0.0.0.0" if LAN else "127.0.0.1"
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"d-reach gateway → http://{host}:{port}/" + (f"?k={KEY}" if LAN else ""))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main(sys.argv[1:])
