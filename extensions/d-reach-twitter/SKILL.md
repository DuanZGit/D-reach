---
name: agent-reach-twitter
description: Use when the user shares an X/Twitter tweet, X Article, author handle, or search phrase and wants content extracted, archived as markdown, or saved into a wiki using the agent-reach twitter-cli workflow.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [research, social-media, twitter, x, agent-reach, twitter-cli]
    related_skills: [xitter, wiki-management]
---

# X/Twitter Reading via agent-reach twitter-cli

## Overview

Use `twitter-cli` from the agent-reach toolkit for reading X/Twitter timelines, tweets, replies, X Articles, and user posts. This is the cookie/session-based path, separate from the official-API `x-cli` workflow.

Verified locally with `twitter, version 0.8.5`（本机在 `/usr/local/bin/twitter`，直接在 PATH 上）。

## Prerequisites

```bash
pipx install twitter-cli  # or pipx upgrade twitter-cli
twitter --version
```

Authentication uses browser cookie values as environment variables:

```bash
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
```

Do not hard-code secrets into skills, markdown archives, or repo files. Pass them as environment variables for each command/session.

## Quick Reference

```bash
# Home feed
twitter feed -n 20 --json

# Single tweet, usually includes replies in data[]
twitter tweet URL_OR_ID --json

# X Article linked from a tweet
twitter article URL_OR_ID --json

# User timeline
twitter user-posts @username -n 20 --json

# User profile
twitter user @username --json

# Search; can be unstable when X changes GraphQL
twitter search 'query' -n 20 --json
```

## Search Workflow

1. Search exact title first:

```bash
twitter search '"A Functional Taxonomy of World Models"' -n 20 --json
```

2. If exact search misses, broaden:

```bash
twitter search '"Functional Taxonomy" "World Models"' -n 20 --json
twitter search '"World Models" "Fei-Fei Li"' -n 20 --json
twitter search 'from:drfeifei "world models"' -n 20 --json
```

3. Identify the authoritative author handle and tweet ID from `data[].author.screenName` and `data[].id`.

## Reading Tweets and Replies

```bash
twitter tweet 2062247238143996275 --json > /tmp/tweet.json
```

The JSON shape is usually:

- `ok`, `schema_version`
- `data[]`: main tweet plus replies/thread items
- tweet fields: `id`, `text`, `author`, `metrics`, `createdAt`, `createdAtISO`, `media`, `urls`, `quotedTweet`

When `twitter tweet` returns many replies, do not parse through Hermes tool-output truncation. Redirect to a temp file first, then parse the file locally.

## Reading X Articles

If a tweet text is only a `t.co` link or links to `/i/article/...`, call `twitter article` with the tweet ID, not necessarily the article ID:

```bash
twitter article 2062247238143996275 --json > /tmp/article.json
```

Verified schema for X Articles:

- `data.articleTitle`
- `data.articleText`
- `data.urls[]`
- normal tweet metadata: `author`, `metrics`, `createdAtISO`

Pitfall: `twitter article ARTICLE_ID` may return `Article not found`; use the source tweet ID first.

## Saving as Obsidian Markdown

Use YAML frontmatter and keep raw content un-summarized unless asked to refine.

Recommended fields:

```yaml
---
title: "Article or tweet title"
created: YYYY-MM-DD
saved: YYYY-MM-DD
type: raw
source: x-twitter
author: "Display Name"
author_handle: "@handle"
tweet_id: "..."
article_id: "..."        # if applicable
url: "https://x.com/handle/status/id"
article_url: "https://x.com/i/article/id"
tags: [x, twitter]
likes: 0
retweets: 0
replies: 0
quotes: 0
views: 0
bookmarks: 0
confidence: high
---
```

Body sections:

```markdown
# Title

> Source post: ...
> X Article: ...
> Author: ...
> Created: ...
> Saved: ...

## Post text

Raw tweet text.

## Article

Raw article text.

## Links

- resolved URLs

## Media

- media URLs

## Metrics at capture time

- Likes: ...

## Replies captured

- @user: reply text
```

## Robust Parse Pattern

For large tweets/articles, redirect CLI output to files and parse with Python:

```bash
export TWITTER_AUTH_TOKEN="..." TWITTER_CT0="..."
twitter tweet TWEET_ID --json > /tmp/tweet.json
twitter article TWEET_ID --json > /tmp/article.json
```

```python
import json

tweet = json.loads(open('/tmp/tweet.json', encoding='utf-8').read(), strict=False)
article = json.loads(open('/tmp/article.json', encoding='utf-8').read(), strict=False)
main = next(x for x in tweet['data'] if x['id'] == 'TWEET_ID')
article_title = article['data'].get('articleTitle')
article_text = article['data'].get('articleText')
```

Use `strict=False` because some tweet/reply text may contain control characters that break strict JSON parsing.

## Resolving t.co Links

Use Python redirect resolution when needed:

```python
import urllib.request
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
final_url = urllib.request.urlopen(req, timeout=10).geturl()
```

## Common Pitfalls

1. **Tool output truncation breaks JSON parsing.** Redirect to `/tmp/*.json` before parsing large results.

2. **`twitter article ARTICLE_ID` may fail.** Call `twitter article SOURCE_TWEET_ID --json` first.

3. **Search can be noisy.** Use exact title, then broaden with author filters like `from:drfeifei`.

4. **Search can break when X changes GraphQL endpoints.** Try `pipx upgrade twitter-cli`; if still broken, use user timelines or known tweet URLs.

5. **Do not store secrets.** Never save `auth_token`, `ct0`, or full Cookie headers into wiki/raw markdown.

6. **IP/account risk.** Avoid high-frequency scraping, followers/following expansion, or use from VPS/datacenter IPs. Prefer local/residential network and delays for batches.
