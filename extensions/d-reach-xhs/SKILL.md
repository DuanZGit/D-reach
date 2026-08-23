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

The `xhs` CLI (installed via `pipx install xiaohongshu-cli`) is part of the
**agent-reach** skill collection. The Claude Code version lives at
`~/.claude/skills/d-reach/` — read its `references/social.md` for the
canonical upstream docs if this skill is stale.

## Prerequisites

- `xhs` CLI: `/Users/roucher/.local/bin/xhs`
- Cookies stored at `~/.xiaohongshu-cli/cookies.json`
- Login status: `xhs status` (verbose: `xhs -v status`)
- If expired: `xhs login --cookie-source chrome` or `xhs login --qrcode`

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

5. **POST operations (post/comment/like)** may fail with 406 in v0.6.x due to
   signing issues. Downgrade to v0.3.5 if needed: `pipx install xiaohongshu-cli==0.3.5`

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

## Agent-Reach Ecosystem

The `xhs` CLI is part of a larger toolkit at `~/.claude/skills/d-reach/`.
Other platforms include: Twitter (`twitter-cli`), Reddit (`rdt-cli`),
Douyin (MCP server), Bilibili (`yt-dlp`), V2EX (public API), YouTube, etc.
The Claude Code skill has full references in `references/social.md`,
`references/web.md`, `references/video.md`, etc.

See `references/social.md` in this skill for canonical upstream docs covering
all platforms (XHS, Twitter/X, Douyin, Weibo, Bilibili, V2EX, Reddit).

### Twitter/X (twitter-cli)

```bash
# Install
pipx install twitter-cli  # ensure v0.8.5+

# Auth — set env vars from browser cookies
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."

# Stable commands
twitter feed -n 20 --json
twitter tweet URL_OR_ID --json
twitter article URL_OR_ID --json
twitter user-posts @username -n 20 --json
twitter user @username --json

# May fail — Twitter changes GraphQL frequently
twitter search "query" -n 10
```

> **IP风控**: 不要在VPS/数据中心IP频繁调用，有封号风险。使用住宅代理或本地环境。
> **search可能失效**: Twitter频繁修改GraphQL端点，search可能返回404。如遇此情况，用`twitter feed`替代。
