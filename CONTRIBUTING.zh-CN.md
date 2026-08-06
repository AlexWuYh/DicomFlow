# 参与 DicomFlow 开发

[English](./CONTRIBUTING.md) | **简体中文**

## 分支模型

| 分支 | 职责 |
|------|------|
| **`main`** | **发布**主分支，只放可发布代码。每次有提交都会触发 release 打包流水线。 |
| **`dev`** | **开发**集成主分支，日常功能合并到这里。 |
| **`feature/*`**、**`fix/*`** 等 | 从 **`dev` 拉取** 的短期功能/修复分支。 |

```
feature/foo ──┐
feature/bar ──┼──► dev ──(发布)──► main ──► GitHub Release + 安装包
hotfix/x    ──┘
```

### 日常开发

1. 同步 `dev`：
   ```bash
   git checkout dev
   git pull origin dev
   ```
2. 开分支：
   ```bash
   git checkout -b feature/my-change
   ```
3. 开发、提交、推送，并向 **`dev`** 开 Pull Request（不要直接对 `main` 开发）。
4. Review 通过后合并进 `dev`。PR 与 `dev` 推送会跑 CI 测试。

### 发布

1. 在 `dev` 上确认：若需要**新**的 release 标签，请先升高 `pyproject.toml` 与 `src/dicomflow/__init__.py` 中的版本号（如 `0.2.0` → `0.3.0`）。
2. 开 PR **`dev` → `main`**（或按团队约定合并）。
3. 合并进 `main` 后，**Release** 流水线会：
   - 跑测试
   - 构建 `sdist` + wheel
   - 把构建产物挂到本次 workflow artifacts
   - 若标签 `v{version}` **尚不存在**，则创建 GitHub Release 并上传安装包

若 `main` 有提交但**未升版本号**，仍会打包并上传 artifacts，但**不会**为同一 `v{version}` 重复创建 Release。

### 本地检查

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## 说明

请保持尊重。本项目**不是医疗器械**，不得作为诊断设备宣传或使用。
