# Contributing to DicomFlow

**English** | [简体中文](./CONTRIBUTING.zh-CN.md)

## Branch model

| Branch | Role |
|--------|------|
| **`main`** | **Release** line only. Production-ready code. Every push triggers release packaging CI. |
| **`dev`** | **Development** integration branch. Day-to-day merges land here. |
| **`feature/*`**, **`fix/*`**, … | Short-lived branches cut **from `dev`**. |

```
feature/foo ──┐
feature/bar ──┼──► dev ──(release)──► main ──► GitHub Release + packages
hotfix/x    ──┘
```

### Daily development

1. Update `dev`:
   ```bash
   git checkout dev
   git pull origin dev
   ```
2. Create a branch:
   ```bash
   git checkout -b feature/my-change
   ```
3. Implement, commit, push, open a **Pull Request into `dev`** (not `main`).
4. After review, merge the PR into `dev`. CI runs on PRs and on `dev` pushes.

### Releasing

1. On `dev`, ensure version in `pyproject.toml` and `src/dicomflow/__init__.py` is bumped when you intend a **new** release tag (e.g. `0.2.0` → `0.3.0`).
2. Open a PR **`dev` → `main`** (or merge with your team process).
3. After merge to `main`, the **Release** workflow:
   - runs tests
   - builds `sdist` + wheel
   - uploads build artifacts on the workflow run
   - if tag `v{version}` does **not** already exist, creates a GitHub Release and attaches the packages

If `main` is updated without a version bump, packaging still runs and artifacts are uploaded, but a second GitHub Release for the same `v{version}` is **not** recreated.

### Local checks

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## Code of conduct

Be respectful. This project is **not a medical device** and must not be marketed as one.
