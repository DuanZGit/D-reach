# secrets.enc — 凭据加密包

聚合了 D-Reach 运行所需的全部 API key 和平台 cookie，AES-256-CBC + PBKDF2 (600k iterations) 加密。

## 内容

- **26 个 API key**：FIRECRAWL、BRIGHTDATA、EXA、BRAVE、SERPER、SCRAPECREATORS、DEEPSEEK、QWEN、OPENROUTER、STEPFUN、SILICONFLOW、MINIMAX、XAI、SENSENOVA、SWITCHYARD、NEWAPI×3、DIDA365、FINNHUB、ALPHA_VANTAGE、BAIDU、CNB_TOKEN/USERNAME、XGET_TOKEN、OPENCODE
- **2 个平台 cookie**：bilibili（credential.json）、xiaohongshu（cookies.json）

## 解密

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
  -in secrets.enc -out secrets.json -pass "pass:<你的密码>"
```

## 加密（更新后重新打包）

```bash
openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt \
  -in secrets.json -out secrets.enc -pass "pass:<你的密码>"
rm secrets.json   # 明文立即删除
```

## 安全规则

- **密码不存本仓库**，仅用户本人保管；丢失则无法解密
- `secrets.json`（明文）已在 `.gitignore` 排除，永远不要提交
- 本仓库为 PRIVATE；若转为 PUBLIC，**必须先删除 secrets.enc 并清理 git 历史**
