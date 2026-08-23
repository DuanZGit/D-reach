# Twitter/X via agent-reach `twitter-cli` (cookie auth)

Use this reference when the user provides browser cookie values (`auth_token` and `ct0`) or asks for X/Twitter read-only scraping without official X API developer credentials.

## Tool

`twitter-cli` command is exposed as `twitter` (commonly at `~/.local/bin/twitter`). Verify with:

```bash
twitter --version
# expected known-good: twitter, version 0.8.5
```

Install/upgrade if needed:

```bash
pipx install twitter-cli
pipx upgrade twitter-cli
```

## Auth from cookies

Set both values for the command invocation:

```bash
export TWITTER_AUTH_TOKEN="<auth_token>"
export TWITTER_CT0="<ct0>"
```

Only these two cookie values are needed for tested read commands. Do not persist secrets in SKILL.md or references.

## Known-good read commands

```bash
# Home feed
twitter feed -n 20 --json

# Single tweet / thread / replies
twitter tweet URL_OR_ID --json

# User timeline
twitter user-posts @username -n 20 --json

# User profile
twitter user @username --json

# X Article attached to a tweet
twitter article TWEET_ID --json
```

Search can work but is less reliable:

```bash
twitter search '"exact phrase"' -n 20 --json
```

## X Article gotcha

For an X Article link like:

```text
https://x.com/i/article/2062244283940544512
```

`twitter article ARTICLE_ID --json` may return `Article not found`. Use the *tweet id that shared the article* instead:

```bash
twitter article 2062247238143996275 --json
```

The article payload may use these fields:

- `articleTitle`
- `articleText`

Do not assume `title`, `text`, `content`, or `body` contain the article body.

## Markdown capture pattern

For raw Obsidian-compatible capture, include:

- YAML frontmatter: title, created, saved, type, source, author, author_handle, tweet_id, url, tags, metrics
- Original post text
- Resolved X Article URL if present
- Full `articleText` when available
- Media URLs
- A bounded reply sample (e.g. first 30) if `twitter tweet` returns replies

Suggested source commands to record in the file:

```text
twitter tweet <tweet_id> --json
twitter article <tweet_id> --json
```

## Pitfalls

- Avoid logging full cookie secrets in final answers or durable skill text.
- `twitter tweet` output can be large; if JSON parsing through a capped tool output fails, redirect to a temp file first and parse the file.
- `twitter search` may return noisy matches; combine exact phrase queries with `from:<handle>` and then verify the author/tweet id before saving.
