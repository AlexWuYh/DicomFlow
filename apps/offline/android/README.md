# Android offline app (scaffold)

## Goal

Fully offline Android tool: pick local DICOM archive → convert on device → preview/export.

## Constraints

- No cloud APIs, no Turnstile, no login
- Reuse **conversion semantics** from `src/dicomflow/engine` where feasible
- APK must run without network

## Candidate stacks (decision pending A2)

| Option | Pros | Cons |
|--------|------|------|
| **Chaquopy** (Python in APK) | Reuse engine code | APK size, lifecycle, ffmpeg/unrar on ARM |
| **BeeWare / Briefcase** | Python UI + package | Maturity / DICOM deps |
| **Kotlin UI + native libs** | Best mobile UX | Large rewrite of engine |
| **Termux-like sidecar** | Fast experiment | Poor store / UX |

**Current decision (milestone A1):** document + interface only; implement Windows first.  
**A2:** spike Chaquopy or Kotlin+ffmpeg with a minimal “one series → mp4” path.

## Integration contract (for any stack)

```
Input:  content:// or file path to zip|rar|...
Params: format, quality, merge, fps  (same as ConvertParams)
Output: list of media files in app-private storage + share/export intent
Progress: percent + phase string (map from ProgressEvent)
```

Do **not** call GHCR or any HTTPS service during convert.

## Directory (future)

```
android/
  app/                 # Android Studio project (to be added in A2)
  README.md            # this file
```
