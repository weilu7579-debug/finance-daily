# 📰 每日财经新闻邮件速览

每天自动从东方财富、新浪财经、雪球、华尔街见闻抓取当日最热财经新闻，经通义千问 AI 生成摘要，HTML 邮件发送到你的邮箱。

## ✨ 功能

| 步骤 | 说明 |
|------|------|
| 🕷️ **爬虫** | 4 源并行抓取（东方财富 / 新浪财经 / 雪球 / 华尔街见闻）→ 去重 |
| 🤖 **AI 摘要** | 阿里云通义千问筛选 Top 10，生成 2-3 句中文摘要 + 分类标注 |
| 📧 **邮件发送** | Jinja2 渲染 HTML → QQ邮箱 SMTP，手机/电脑均可阅读 |
| ☁️ **云部署** | 阿里云函数计算 FC，定时触发器每天 8:00 自动运行 |

## 💰 成本

| 项目 | 费用 |
|------|------|
| 阿里云函数计算 | 免费（30次/月调用，免费额度内） |
| 通义千问 API | ≈ ¥1-2/月 |
| 邮箱 SMTP | 免费 |
| **合计** | **≈ ¥1-2/月** |

## 🏗️ 架构

```
finance-daily/
├── scraper.py        # 爬虫：4源并行抓取 → 标题相似度去重
├── summarizer.py     # AI：DashScope API 筛选+摘要 → Top 10 JSON
├── mailer.py         # 邮件：Jinja2 模板渲染 + SMTP SSL 发送（3次重试）
├── main.py           # 编排入口 + 阿里云 FC handler
├── template.html     # 邮件 HTML 模板（响应式、纯内联 CSS）
└── requirements.txt  # 依赖清单
```

## 🚀 快速开始

### 前提条件

- Python ≥ 3.9
- 阿里云 DashScope API Key（[免费申请](https://dashscope.console.aliyun.com/)）
- QQ 邮箱 SMTP 授权码

### 安装

```bash
git clone https://github.com/weilu7579-debug/finance-daily.git
cd finance-daily
pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
# 编辑 .env 填入真实的 API Key 和邮箱凭证
```

### 本地运行

```bash
set -a && source .env && set +a
python main.py
```

### 部署到阿里云 FC（每天 8:00 自动发送）

1. 登录 [阿里云函数计算控制台](https://fc.console.aliyun.com/)
2. 创建函数（Python 3.9，超时 120s，内存 256MB）
3. 上传项目 zip（不含 `.env`）
4. 在函数环境变量中配置 `DASHSCOPE_API_KEY`、`SMTP_*` 等
5. 添加定时触发器：`cron: 0 0 8 * * *`

## 📧 邮件效果

```
📰 每日财经速览
2026年6月8日 · 周一

━━━━━━━━━━━━━━━━━━━━━━

1. 央行宣布降准0.25个百分点          🔴宏观
   中国人民银行决定于6月15日下调存款准备金率0.25个百分点...
   来源：新浪财经 → 阅读原文

2. A股三大指数集体收涨 沪指涨超1%   🔵股市
   A股今日全面走强，上证指数收涨1.2%...
   来源：东方财富 → 阅读原文

（共 10 条，按重要性排序，分宏观/股市/行业/公司/国际 五类）

━━━━━━━━━━━━━━━━━━━━━━
每日自动生成 · AI 摘要仅供参考，不构成投资建议
```

## ⚠️ 注意事项

- AI 摘要是大模型生成的，可能存在事实错误，仅供参考
- 不要将 `.env` 文件提交到公开仓库
- 单一数据源抓取失败不影响整体运行
- AI API 调用失败会自动降级为纯标题+链接版邮件

## 📄 License

MIT
