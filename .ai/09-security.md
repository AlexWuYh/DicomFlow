# 公网安全说明

## 默认安全姿态

| 项 | 默认 | 说明 |
|----|------|------|
| OpenAPI `/docs` | **关闭** | `DICOMFLOW_ENABLE_DOCS=true` 才开启 |
| 访问令牌 | 可选 | 设 `DICOMFLOW_ACCESS_TOKEN` 后 API 需 `X-DicomFlow-Token` |
| 人机验证 | **默认关** | `DICOMFLOW_CAPTCHA_ENABLED=true` + Turnstile site/secret；校验上传 |
| 全局限流 | 60 次/分钟/IP | `DICOMFLOW_RATE_LIMIT_RPM` |
| 上传限流 | 20 次/小时/IP | `DICOMFLOW_RATE_LIMIT_UPLOADS_PER_HOUR` |
| 上传大小 | 1 GiB | `DICOMFLOW_MAX_UPLOAD_BYTES` |
| 扩展名白名单 | zip/rar/7z/tar/gz/tgz | |
| 安全响应头 | 启用 | nosniff, frame deny, CSP, no-store on API |
| CORS | 关闭 | 仅当配置 `DICOMFLOW_CORS_ORIGINS` 时开放 |
| `X-Forwarded-For` | **默认不信任** | 仅在可信反代后设 `TRUST_X_FORWARDED_FOR=true` |
| 任务元数据 | SQLite | `data/dicomflow.db`，重启可查询历史任务状态 |

## 公网部署检查清单

1. **必须**设置强随机 `DICOMFLOW_ACCESS_TOKEN`（≥32 字符）
2. **建议**开启人机验证：`DICOMFLOW_CAPTCHA_ENABLED=true` + Cloudflare Turnstile 密钥
3. 前置 **HTTPS** 反向代理（Caddy / nginx / Cloudflare）
4. 设置 `DICOMFLOW_ALLOWED_HOSTS=你的域名`
5. 保持 `DICOMFLOW_ENABLE_DOCS=false`
6. 不要把 `/data` 卷或源文件映射到公网可读路径
7. 医疗影像属敏感数据：优先私有化 / 内网；公网需告知用户并尽快清理
8. 建议定期轮换令牌；任务结果 ID 为不可猜 UUID，但仍应限时清理

## 访问密码与人机验证（均可开关）

| 能力 | 开关 | 作用面 |
|------|------|--------|
| 访问密码 | 设/清空 `DICOMFLOW_ACCESS_TOKEN` | 几乎全部 `/api/*` |
| 人机验证 | `DICOMFLOW_CAPTCHA_ENABLED` + Turnstile keys | **上传** `POST /api/v1/uploads` |

两者独立：可只开密码、只开 captcha，或同时开启。

### Turnstile 配置

```bash
export DICOMFLOW_CAPTCHA_ENABLED=true
export DICOMFLOW_TURNSTILE_SITE_KEY="0x4AAAA..."   # 公开，给前端
export TURNSTILE_SECRET="..."                       # 仅服务端（canonical 名；勿写入仓库）
```

- 密钥在 [Cloudflare Turnstile](https://dash.cloudflare.com/?to=/:account/turnstile) 创建
- Secret 读取顺序：`DICOMFLOW_TURNSTILE_SECRET_KEY` → 进程环境 `TURNSTILE_SECRET` → `.env` 中 `TURNSTILE_SECRET`
- 仅当 `CAPTCHA_ENABLED=true` **且** site/secret 都非空时，bootstrap 才返回 `captcha_enabled: true`
- 若开关为 true 但缺密钥：上传失败（503 `CAPTCHA_MISCONFIGURED`），避免静默裸奔
- 服务端 `POST https://challenges.cloudflare.com/turnstile/v0/siteverify`，body：`secret` + `response` + `remoteip`；要求 `success === true`
- 前端 widget 使用 `data-action="turnstile-spin-v2"`
- CSP 已允许 `challenges.cloudflare.com` 的 script / frame / connect / worker
- **本地预览**：Turnstile 控制台 Hostname Management 必须包含 `localhost` 与 `127.0.0.1`（不要带端口号）。否则小部件会显示「无法连接到网站」（错误码 110200）

## 前端令牌

- 启动时请求 `/api/v1/bootstrap` → `auth_required`、`captcha_enabled`、`captcha_site_key`
- 需要时弹窗输入访问密码，存入 `sessionStorage`（关标签即清）
- 所有 API 请求带 `X-DicomFlow-Token`
- captcha 开启时渲染 Turnstile 小部件，上传 FormData 附带 `cf-turnstile-response`
- 预览/下载通过 fetch+blob（媒体标签无法自定义头）

## 健康检查

`/health` 与 `/api/v1/health` **不需要**令牌，供 Docker / 负载均衡探测。

## 数据保留

- 默认 **24 小时**后自动删除 `uploads/`、`work/`、`outputs/` 下过期目录
- 环境变量：`DICOMFLOW_JOB_TTL_HOURS`（默认 24）、`DICOMFLOW_CLEANUP_INTERVAL_SECONDS`（默认 900）
- 服务启动时立即跑一轮清理，之后按间隔后台执行
- 内存中的任务/上传元数据同步剔除过期项
