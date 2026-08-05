# 公网安全说明

## 默认安全姿态

| 项 | 默认 | 说明 |
|----|------|------|
| OpenAPI `/docs` | **关闭** | `DICOMFLOW_ENABLE_DOCS=true` 才开启 |
| 访问令牌 | 可选 | 设 `DICOMFLOW_ACCESS_TOKEN` 后 API 需 `X-DicomFlow-Token` |
| 全局限流 | 60 次/分钟/IP | `DICOMFLOW_RATE_LIMIT_RPM` |
| 上传限流 | 20 次/小时/IP | `DICOMFLOW_RATE_LIMIT_UPLOADS_PER_HOUR` |
| 上传大小 | 1 GiB | `DICOMFLOW_MAX_UPLOAD_BYTES` |
| 扩展名白名单 | zip/rar/7z/tar/gz/tgz | |
| 安全响应头 | 启用 | nosniff, frame deny, CSP, no-store on API |
| CORS | 关闭 | 仅当配置 `DICOMFLOW_CORS_ORIGINS` 时开放 |

## 公网部署检查清单

1. **必须**设置强随机 `DICOMFLOW_ACCESS_TOKEN`（≥32 字符）
2. 前置 **HTTPS** 反向代理（Caddy / nginx / Cloudflare）
3. 设置 `DICOMFLOW_ALLOWED_HOSTS=你的域名`
4. 保持 `DICOMFLOW_ENABLE_DOCS=false`
5. 不要把 `/data` 卷或源文件映射到公网可读路径
6. 医疗影像属敏感数据：优先私有化 / 内网；公网需告知用户并尽快清理
7. 建议定期轮换令牌；任务结果 ID 为不可猜 UUID，但仍应限时清理

## 前端令牌

- 启动时请求 `/api/v1/bootstrap` → `auth_required`
- 需要时弹窗输入令牌，存入 `sessionStorage`（关标签即清）
- 所有 API 请求带 `X-DicomFlow-Token`
- 预览/下载通过 fetch+blob（媒体标签无法自定义头）

## 健康检查

`/health` 与 `/api/v1/health` **不需要**令牌，供 Docker / 负载均衡探测。

## 数据保留

- 默认 **24 小时**后自动删除 `uploads/`、`work/`、`outputs/` 下过期目录
- 环境变量：`DICOMFLOW_JOB_TTL_HOURS`（默认 24）、`DICOMFLOW_CLEANUP_INTERVAL_SECONDS`（默认 900）
- 服务启动时立即跑一轮清理，之后按间隔后台执行
- 内存中的任务/上传元数据同步剔除过期项
