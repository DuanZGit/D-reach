#!/usr/bin/env python3
"""PDF → 文本（d_reach_fetch 的 PDF 档）。

为什么需要它：curl 拿到 application/pdf 时，htmlToText 会把二进制当 HTML 剥标签，
产出上百万字符的乱码，judge 一看字数够就判「成功」。这是最恶劣的一类假成功。
本机已有 pymupdf（fitz），直接用它。
"""
import json
import sys


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "err": "no_path"}))
        return
    try:
        try:
            import pymupdf as fitz  # 新名，无 deprecation 告警
        except ImportError:
            import fitz  # 老版本 pymupdf 只有这个名字
    except ImportError as e:
        print(json.dumps({"ok": False, "err": f"缺 pymupdf: {e}"}))
        return
    try:
        doc = fitz.open(sys.argv[1])
    except Exception as e:  # noqa: BLE001 - 加密/损坏的 PDF 都要落成可读失败
        print(json.dumps({"ok": False, "err": f"打不开 PDF: {e}"}))
        return
    try:
        pages = [page.get_text() for page in doc]
        text = "\n\n".join(p.strip() for p in pages if p.strip())
        # 扫描件没有文字层：返回空文本，让上游明确报「这是图片 PDF」而不是编内容
        print(json.dumps({"ok": True, "text": text, "pages": doc.page_count}, ensure_ascii=False))
    finally:
        doc.close()


if __name__ == "__main__":
    main()
