---
name: agent-reach-xhs
description: >
  Read Xiaohongshu (小红书/XHS) notes using the xhs CLI from the agent-reach toolkit.
  Use when user shares a xiaohongshu.com or xhslink.com URL and wants content extracted.
triggers:
  - xiaohongshu/xhs/小红书/红书/xhslink
metadata:
  hermes:
    tags: [research, social-media, xiaohongshu, agent-reach]
---

# Xiaohongshu Note Reading (via agent-reach)

## Overview

The `xhs` CLI (installed via `pipx install xiaohongshu-cli`) is the Xiaohongshu
channel for D-Reach. Canonical routing lives in the parent `SKILL.md`.

## Prerequisites

- `xhs` CLI on PATH (this box: `/usr/local/bin/xhs`, verified v0.6.4)
- Cookies stored at `~/.xiaohongshu-cli/cookies.json`
- Login status: `xhs status` (verbose: `xhs -v status`)
- If expired: `xhs login --cookie-source chrome` or `xhs login --qrcode`
- **当前状态（2026-09-05 实测）**：cookie 已过期，`xhs search` 直接返回
  `{"ok":false,"error":{"code":"not_authenticated","message":"Session expired..."}}`
  —— 需要用户本人扫码登录，agent 无法代跑。别连续重试烧配额。

## Critical: xsec_token Restriction

Xiaohongshu enforces an `xsec_token` mechanism. **You CANNOT read a note by
bare note_id directly.** The correct flow:

1. **First** get a valid xsec_token via `xhs search`, `xhs feed`, or `xhs hot`
2. **Then** use the URL/ID from those results (which include the token) to `xhs read`

```bash
# ❌ WRONG — will return empty {} or error
xhs read 68cff000000000001202053f

# ✅ RIGHT — search first, then read from results
xhs search "关键词" --json
xhs read "URL_FROM_SEARCH_RESULTS"
```

The `xhs read` command also accepts `--xsec-token TOKEN` if you have one.

## Critical: Short Link Handling

The `xhs` CLI does **NOT** resolve short links (`xhslink.com/o/...`). It
concatenates the entire URL into the `/explore/` path, causing error 300017.

```bash
# ❌ WRONG — CLI mangles the URL
xhs read 'http://xhslink.com/o/AqEmOpQLHHL'

# ✅ RIGHT — resolve short link first, then use note ID
# Short link → browser redirect → note ID from final URL
```

### Resolving Short Links

**Method 1 — Browser redirect** (Recommended, most reliable):
Navigate to the short link with the browser. XHS redirects to a URL like:
```
https://www.xiaohongshu.com/explore/NOTE_ID?...&xsec_token=TOKEN&...
```
Extract `NOTE_ID` and `xsec_token` from the redirect URL. Even if the page
shows an error (300012 = IP risk), the redirect URL itself contains valid data.

**Critical**: Browser tokens (prefix `CB`) are validated by xhs CLI and work
immediately. curl tokens (prefix `AB`) often trigger Captcha — avoid them.

**Workflow**: Browser redirect → extract CB-token from URL → `xhs read` with token
```bash
xhs read 'https://www.xiaohongshu.com/explore/NOTE_ID' --xsec-token 'CB...' --json
```

**Method 2 — curl** (Limited, may fail):
```bash
curl -sI 'http://xhslink.com/o/XXXXX' | grep -i location
```
Note: curl tokens (prefix `AB`) often fail with xhs CLI due to Captcha.
Only use if browser method is unavailable.

### Extracting Images for Vision Analysis

The note JSON contains `image_list` with URLs in multiple sizes:
- `info_list[].url` where `image_scene == "WB_DFT"` — default quality
- `info_list[].url` where `image_scene == "WB_PRV"` — preview quality
- `url_default` / `url_pre` — top-level shortcuts

Download with `curl` (these are direct CDN links, no auth needed):
```bash
curl -sL -o /tmp/img.webp "URL_FROM_WB_DFT"
```

Images are typically `.webp` format. Use `vision_analyze` for OCR/text extraction.

## Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 300012 | IP risk block | Use residential proxy or local machine |
| 300017 | Abnormal link | CLI mangled the URL; fix the input format |
| 300031 | Note temporarily unavailable | Note deleted/private/restricted — **not a tool or cookie problem** |

## Pitfalls

1. **Don't confuse cookie expiry with note unavailability.** Check `xhs status`
   first. If status is OK but read returns `{}`, the note itself is restricted.

2. **Don't waste time on 300031.** If a note returns this error from multiple
   methods (CLI, curl, Jina Reader, browser), the note is genuinely
   unavailable server-side. No amount of cookie refresh or proxy switching
   will fix it. Ask the user to copy-paste the content from their phone.

3. **Jina Reader doesn't work for XHS.** `r.jina.ai` returns the Xiaohongshu
   homepage or login page, not note content. XHS requires JavaScript SSR
   with valid session cookies.

4. **Rate limiting:** Batch operations need 2-3s delays. High-frequency
   requests trigger CAPTCHAs.

5. **⚠️ 必须 xhs-cli ≥ 0.6.4**：0.4.0/0.5.x 读评论被 406 风控拦死（本机实证 2026-08-26）。
   升级：`pip install --user --no-deps xiaohongshu-cli==0.6.4 xhshow`。
   `xhs comments` 优先于 `xhs read`——`read` 易触发 captcha，`comments` 更稳且支持 `--all` 分页。

## Comments Extraction

To get high-information comments and author replies:

```bash
xhs comments NOTE_ID_OR_URL --xsec-token TOKEN --json
```

The comments JSON contains:
- `content`: Comment text
- `user.nickname`: Commenter name
- `like_count`: Likes on the comment
- `sub_comments`: Replies to the comment (including author replies)

Extract valuable comments by filtering for:
1. High like counts (indicates community validation)
2. Author replies (marked by matching user_id with note author)
3. Sub-comments with technical corrections or additions

## Quick Reference

```bash
xhs search "query"              # Search notes
xhs read NOTE_ID_OR_URL         # Read note (needs xsec_token context)
xhs comments NOTE_ID_OR_URL     # View comments
xhs hot                         # Browse trending
xhs feed                        # Recommendation feed
xhs status                      # Check login
xhs login --cookie-source auto  # Re-login from browser cookies
```

## 相关通道

其它平台不在本文件里：Twitter/X 见 `../d-reach-twitter/SKILL.md`，
抖音/微博/V2EX/Reddit 见 `../../references/social.md`，路由总表见顶层 `SKILL.md`。
