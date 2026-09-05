# 视频 / 播客

YouTube 用 yt-dlp，B站用 bili-cli（**B站不要用 yt-dlp，风控全面 412 拦，直连/代理/带 cookie 都试过**）。
B站取证铁律（字幕 + 评论区必须都看）见顶层 `SKILL.md`。

## YouTube (yt-dlp)

```bash
yt-dlp --dump-json "URL"                       # 元数据
yt-dlp --dump-json "ytsearch5:query"           # 搜索

# 字幕（不下视频）→ 读 /tmp/<id>.vtt
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" \
  --skip-download -o "/tmp/%(id)s" "URL"

# 评论（在 .info.json 的 comments 字段）
yt-dlp --write-comments --skip-download --write-info-json \
  --extractor-args "youtube:max_comments=20" -o "/tmp/%(id)s" "URL"
```

- 手动上传字幕可靠；自动字幕常行间重复，需后处理。
- `--write-comments` 是网页抓取（非 Data API），部分评论会丢。

## B站 (bili-cli)

```bash
bili search "query" --type video -n 5
bili video BVxxx                 # 详情/时长/互动数据/字幕可用性
bili hot -n 10 ; bili rank -n 10
bili video BVxxx -s --yaml       # 字幕
bili video BVxxx --ai            # AI 总结
bili video BVxxx -c --yaml       # 评论（字段 message）
bili audio BVxxx                 # 导出 ASR-ready 分段 WAV
```

本机已 `bili login`，只读操作无需再登录。安装：`pipx install bilibili-cli`。
弹幕：bili-cli 没有弹幕命令，proto 接口易 412 —— 信息量低于评论区，可跳过。

### 无字幕视频转写

`bili audio BVxxx` 出分段 WAV → 再转写（本机**未装** whisper，需要时先
`pipx install faster-whisper` 或改用 `browser_use` 拿平台自带 AI 摘要）。
（原小宇宙 `transcribe.sh` 依赖 `~/.agent-reach/tools/`，本机不存在，已删。）

### 零配置兜底：B站搜索 API 直连

```bash
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
curl -s -c /tmp/bili_ck.txt -o /dev/null -A "$UA" "https://www.bilibili.com/"
curl -s -b /tmp/bili_ck.txt -A "$UA" -e "https://www.bilibili.com/" \
  "https://api.bilibili.com/x/web-interface/search/all/v2?keyword=QUERY&page=1"
```
