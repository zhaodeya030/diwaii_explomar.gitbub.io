# 小鹏游艇新闻追踪器

每天自动搜索小鹏汽车游艇项目（代号"飞鱼"）的最新新闻，通过邮件推送。

## 工作原理
- GitHub Actions 每天北京时间 09:00 自动触发
- 调用 Claude API + web_search 搜索关键词
- 通过 Gmail SMTP 发送邮件到 zhaodeya@gmail.com
- 自动去重，不会重复推送

## 必需的 Secrets
| 名称 | 说明 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API Key（console.anthropic.com） |
| `EMAIL_SENDER` | 发件 Gmail 地址 |
| `EMAIL_PASSWORD` | Gmail App Password（不是登录密码） |
| `EMAIL_RECIPIENT` | 收件邮箱（可选，默认 zhaodeya@gmail.com） |

## 手动触发
Actions 标签 → "小鹏游艇新闻追踪" → Run workflow
