#!/usr/bin/env python3
"""把 d-reach 抽屉加载器追加到 pi-web 的 client chunk。

pi-web 的 npm 包只发编译产物（files: bin/.next/public），没有源码；
首页是 SSR，改 index.html 无效。唯一稳的注入点是在 client chunk 末尾追加一段
自执行代码，它再去加载网关下发的 /reach/drawer.js —— 真正的 UI 代码不在这里，
以后改抽屉只改网关，不用再动 pi-web 产物。

  python3 patch-piweb.py            # 打补丁
  python3 patch-piweb.py --check    # 只检查
  python3 patch-piweb.py --revert   # 移除补丁

pi-web 升级后 chunk 的 hash 会变，重跑本脚本即可。
"""
import pathlib
import sys

WEB = pathlib.Path.home() / ".npm-global/lib/node_modules/@agegr/pi-web"
CHUNK_DIR = WEB / ".next/static/chunks/app"
MARK = "__DREACH_LOADER__"
# 直连 30142（不经过 Caddy）时 /reach/ 不存在，s.onerror 退回本机网关（3426 只绑 127.0.0.1）
LOADER = (
    ';/* d-reach drawer */'
    '!function(){try{if(window.__DREACH_LOADER__)return;window.__DREACH_LOADER__=1;'
    'var s=document.createElement("script");s.src="/reach/drawer.js";s.async=!0;'
    's.onerror=function(){try{var t=document.createElement("script");'
    't.src="http://127.0.0.1:3426/drawer.js";t.async=!0;document.head.appendChild(t)}catch(e){}};'
    'document.head.appendChild(s)}catch(e){}}();'
)


def targets():
    # layout 是全局 chunk（每个路由都加载），page 只属于首页；两个都注，
    # loader 自己有 __DREACH_LOADER__ 幂等保护，重复注入不会重复执行。
    return sorted(CHUNK_DIR.glob("layout-*.js")) + sorted(CHUNK_DIR.glob("page-*.js"))


def main(argv):
    check = "--check" in argv
    revert = "--revert" in argv
    files = targets()
    if not files:
        print(f"找不到 chunk：{CHUNK_DIR}")
        return 2

    changed = 0
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        has = MARK in text
        if check:
            print(f"{f.name}: {'已注入' if has else '未注入'}")
            continue
        if revert:
            if has:
                i = text.index(";/* d-reach drawer */")
                f.write_text(text[:i], encoding="utf-8")
                print(f"{f.name}: 已移除")
                changed += 1
            continue
        if has:
            print(f"{f.name}: 已是最新，跳过")
            continue
        bak = f.with_suffix(".js.dreach-bak")
        if not bak.exists():
            bak.write_text(text, encoding="utf-8")
        f.write_text(text + LOADER, encoding="utf-8")
        print(f"{f.name}: 已注入（备份 {bak.name}）")
        changed += 1

    if changed:
        print("\n浏览器请强刷一次（Ctrl+Shift+R）；chunk 文件名没变，普通刷新可能吃缓存。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
