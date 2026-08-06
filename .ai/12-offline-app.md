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

### ADR-B：Android 技术选型（已推荐）

> 结论见下表「推荐路径」。详细对比供评审；实现以推荐路径为准，除非 spike 证伪。

#### 约束回顾

- 完全离线；APK 内自带能力  
- 能力：zip（必选）/ rar（可二期）→ 按序列出 MP4/GIF → 本机预览与分享  
- 现有核心在 **Python**（pydicom / numpy / imageio-ffmpeg）  
- 团队优先级：先 Windows 可交付，Android 要可持续而非「能跑 demo」

#### 方案对比

| 方案 | 离线 | 复用 Python 引擎 | 包体/性能 | 可维护性 | 商店/体验 | 结论 |
|------|------|------------------|-----------|----------|-----------|------|
| **A. Kotlin + Compose + FFmpeg-Kit + Zip** | 优 | 差（逻辑对照移植） | 可控 | **优** | **优** | **主选** |
| **B. Chaquopy 嵌 CPython** | 中 | **优** | APK 巨大、ARM 依赖难 | 差 | 中 | **仅 2 周 spike 探路** |
| **C. BeeWare / Briefcase** | 中 | 中 | 未验证科学栈 | 中 | 中 | 不选 |
| **D. Flutter + 自写/FFI 引擎** | 优 | 差 | 可控 | 中（双栈 UI） | 优 | 备选 UI，引擎仍要自建 |
| **E. WebView + 本机 Python 服务** | 差 | 优 | 难上架 | 差 | 差 | 不做 |

#### 推荐路径（主选 A）

**UI：Kotlin + Jetpack Compose**  
**转换：进程内 / 协程调用本地流水线**  
- **解压**：Java Zip；RAR 二期（junrar 或仅文档提示「请用 zip」）  
- **DICOM**：优先 **Java 生态（如 dcm4che 裁剪）** 做发现/排序/像素；窗位逻辑对照 `engine/window.py` 移植  
- **编码**：**FFmpeg-Kit**（或 MediaCodec 仅 H.264 简化路径）出 MP4；GIF 可用 Android 库或降级为「仅 MP4」  
- **语义对齐**：参数与进度对齐 `ConvertParams` / `ProgressEvent`（见 `03-mvp-spec`），便于双端体验一致  

**不作为长期方案**：整包塞入 CPython + pydicom + numpy + imageio（B）。移动端体积、后台杀死、存储权限与 ffmpeg 捆绑成本通常不可接受。

#### 可选 spike（证伪用，非主线）

用 **Chaquopy** 做 ≤2 周 spike：单序列 100 帧 512² 转换 + 测 APK 体积与中端机耗时。  
**否决线（任一触发则放弃 B）**：

- 安装包（含引擎依赖）&gt; ~150–200 MB 且无法明显裁剪  
- 中端机转换时间相对桌面 Python 差一个数量级以上且无法优化  
- 无法稳定捆绑可用 ffmpeg/解压  

Spike 通过也只作「内部工具 APK」，**商店向产品仍以 A 为准**。

#### 分阶段

| 阶段 | 内容 |
|------|------|
| **A1** | 骨架 + 接口约定（已有 `apps/offline/android/`） |
| **A2** | Compose 工程：选 zip → 解压 → 列序列 → 调本地转换 stub |
| **A3** | 接上 DICOM 发现 + FFmpeg 出 MP4；断网验收 |
| **A4** | RAR / GIF / 合并 / 分享面板等增强 |

Windows 仍走 pywebview 壳（ADR-A），与 Android **共享产品语义、不共享运行时**。

### ADR-C：App 模式配置硬开关

`DICOMFLOW_OFFLINE_APP=true`（或 `dicomflow app` 启动时注入）时：

- `host=127.0.0.1` 仅本地
- 忽略 / 关闭 `ACCESS_TOKEN`
- 关闭 `CAPTCHA_*`
- 数据目录默认指向用户可写本地路径（App 数据目录）

## 4. 完成标准

### Windows（本里程碑必达）

- [x] `dicomflow app` / `apps/offline/windows/entry.py` 可启动桌面窗口（需 WebView2）
- [ ] 无外网时可完成：选 zip/rar → 转换 → 预览/导出（真机验收）
- [x] PyInstaller 一目录打包脚本：`build.ps1` / `DicomFlow.spec`（在 Windows 上出 `dist/DicomFlow`）
- [x] 自动化：offline 配置 / bootstrap / web 路径 / prepare_env 单测
- [ ] 干净 Windows 机离线验收（无 Python 环境，仅便携目录）

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
