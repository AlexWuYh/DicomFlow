# 里程碑：完全离线 App（优先 Windows + Android）

供 AI / 开发阅读。分支：`feature/offline-app`。  
**产品约束：完全离线工具软件** — 转换全程不依赖外网；可在无网络环境安装与使用。

## 1. 目标

| 平台 | 优先级 | 形态 |
|------|--------|------|
| **Windows** | P0 | 桌面窗口应用（本地引擎 + 本地 UI） |
| **Android** | P0 | 安装包式离线工具（本机选文件、本机转换、本机预览/导出） |
| macOS / Linux / iOS | P2 | 同架构扩展，非本里程碑必达 |

交付体验：用户打开 App → 选择本地 DICOM 压缩包 → 设置参数 → 转换 → 预览/保存到本机。  
**无账号、无公网上传、无 Turnstile、无访问密码（App 模式强制）**。

## 2. 范围内 / 范围外

### 做

- 复用现有 **engine + JobService + 静态 Web UI**（或后续等价本地 UI）
- 本地环回 HTTP（仅 `127.0.0.1`）或进程内调用引擎
- Windows 可打包安装包 / 便携目录
- Android 可安装 APK（架构允许分阶段：先可运行骨架，再打通转换）
- 离线依赖：ffmpeg / 解压工具随包捆绑或平台等价方案

### 不做（本里程碑）

- 公网部署、SaaS、多用户
- 必须联网的鉴权 / captcha / 遥测
- 医疗器械认证、诊断级阅片
- 云同步、账号系统

## 3. 架构决策（ADR 摘要）

### ADR-A：Windows 优先「本地服务 + 原生壳」

- **决策**：Windows 使用 **pywebview**（WebView2）加载本机 `dicomflow serve`（`127.0.0.1`）。
- **理由**：最大复用现有 `web/` + API + 引擎；完全离线；打包路径清晰（PyInstaller 等）。
- **后果**：需捆绑 Python 运行时与 ffmpeg/unrar；窗口关闭时结束本地服务。

### ADR-B：Android 分两阶段

| 阶段 | 内容 |
|------|------|
| **A1** | 工程骨架 + 离线产品说明 + 与引擎集成的接口约定 |
| **A2** | 可安装包：优先评估 **Chaquopy / BeeWare / 自研 Kotlin 调本地二进制**；或精简引擎 native 化 |

Android 无法简单复用「本机 uvicorn + 系统浏览器」同一套分发，故 **Windows 先可交付，Android 并行推进骨架与集成方案**，避免阻塞 Windows。

### ADR-C：App 模式配置硬开关

`DICOMFLOW_OFFLINE_APP=true`（或 `dicomflow app` 启动时注入）时：

- `host=127.0.0.1` 仅本地
- 忽略 / 关闭 `ACCESS_TOKEN`
- 关闭 `CAPTCHA_*`
- 数据目录默认指向用户可写本地路径（App 数据目录）

## 4. 完成标准

### Windows（本里程碑必达）

- [ ] `dicomflow app`（或等价入口）可启动桌面窗口
- [ ] 无外网时可完成：选 zip/rar → 转换 → 预览/导出
- [ ] 打包文档/脚本可在干净 Windows 上离线运行（依赖随包）
- [ ] 自动化：至少单元/冒烟覆盖 app 启动配置（无 GUI 的 headless 测配置）

### Android（本里程碑必达骨架 + 路径清晰）

- [ ] `apps/offline/android/` 工程说明与集成接口
- [ ] 选定技术路线并写入本文；关键阻塞项列出
- [ ] 若条件允许：最小「选文件 → 调用引擎/服务 → 出文件」PoC

### 共同

- [ ] `.ai` 路线图 Phase 4 更新勾选
- [ ] 不把离线 App 规范写进用户向 README 的分支章节（可在 README 增加「桌面/App」简短入口，产品就绪后再写）

## 5. 仓库布局

```
apps/offline/
  README.md                 # 本目录索引
  windows/                  # 打包与入口说明（PyInstaller 等）
  android/                  # Android 骨架与集成说明
src/dicomflow/
  desktop/                  # 桌面壳启动逻辑（pywebview）
  cli.py                    # dicomflow app 子命令
```

## 6. 实现顺序（任务拆分）

1. 规格与分支（本文 + roadmap）  
2. Settings / `dicomflow app` 离线启动 + Windows 窗口  
3. Windows 打包脚本与依赖清单  
4. Android 技术选型落地与工程骨架  
5. 端到端离线验收与发布说明  

## 7. 风险

| 风险 | 缓解 |
|------|------|
| Android 跑完整 Python 引擎体积大、兼容差 | 分阶段；可评估仅打包 CLI 子进程 / 未来 native |
| WebView2 未安装 | 安装程序捆绑 evergreen bootstrapper 或文档要求 |
| RAR/ffmpeg 许可与体积 | 沿用 Docker 策略；体积写明 |
| 与公网 Web 模式配置冲突 | App 模式强制覆盖安全开关 |
