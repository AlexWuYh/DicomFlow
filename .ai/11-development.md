# 开发规范（供 AI / 代理阅读）

本文档描述 DicomFlow 的分支管理、PR 目标与发布流水线约定。实现代码时默认遵守；**不要**把本节内容写进用户向 README。

## 分支模型

| 分支 | 职责 |
|------|------|
| **`main`** | **发布**主分支。只合入可发布代码。每次 push 触发 Release 打包流水线。 |
| **`dev`** | **开发**集成主分支。日常功能合并到这里。GitHub 默认分支为 `dev`。 |
| **`feature/*`**、**`fix/*`**、**`chore/*`** 等 | 从 **`dev` 拉取** 的短期分支。 |

```
feature/* ──┐
fix/*     ──┼──► dev ──(发布)──► main ──► GitHub Release + sdist/wheel
chore/*   ──┘
```

## 开发流程（强制）

1. 基于最新 `dev` 开分支（`feature/…`、`fix/…` 等），**禁止**直接在 `main` 上开发功能。
2. 功能开发完成后，开 PR **目标分支 = `dev`**（不要对 `main` 开功能 PR）。
3. CI（`.github/workflows/ci.yml`）在以下情况跑测试：
   - push 到 `dev`
   - PR 指向 `dev` 或 `main`
4. 需要发布时：
   - 在 `dev` 上升版本：`pyproject.toml` 的 `project.version` 与 `src/dicomflow/__init__.py` 的 `__version__` 保持一致
   - 将 `dev` 合并到 `main`（PR 或约定流程）
5. `main` 上有提交后，Release 流水线（`.github/workflows/release.yml`）会：
   - 跑测试
   - 构建 sdist + wheel，上传 workflow artifacts
   - 若标签 `v{version}` **尚不存在**，则创建 GitHub Release 并附带安装包
   - 若标签已存在（未升版本号），仍打包 artifacts，**不**重复建 Release

## 版本号

- 语义化版本：主.次.修订（当前见 `pyproject.toml`）
- 新 Release 标签格式：`v{version}`（如 `v0.2.0`）
- 合入 `main` 前若期望产生新 GitHub Release，必须先升版本号

## AI 改代码时的默认行为

| 场景 | 默认 |
|------|------|
| 功能 / 修复 / 文档（开发态） | 在 `dev` 上工作；新分支从 `dev` 拉 |
| 发布相关提交 | 版本号改在 `dev`，再合 `main`；不要只在 `main` 上堆功能 |
| 用户说「提交 / push」且未指定分支 | 推送到当前工作分支；若在错误分支上（如误在 `main` 做功能），先切到 `dev` 或 feature 分支再说明 |
| 用户明确要求发布 | 检查版本号 → 合入 `main` → 依赖 GitHub Actions 出包 |

## 相关工作流文件

| 文件 | 触发 | 作用 |
|------|------|------|
| `.github/workflows/ci.yml` | `dev` push；PR → `dev`/`main` | pytest（Python 3.11 / 3.12） |
| `.github/workflows/release.yml` | `main` push | 测试 + 构建包 + 条件创建 Release |

## 本地验证（实现后）

```bash
pip install -e ".[dev]"
pytest -q
```
