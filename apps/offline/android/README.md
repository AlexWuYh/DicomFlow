# Android offline app — technology choice

Product rules: [`.ai/12-offline-app.md`](../../../.ai/12-offline-app.md).

## Recommendation (summary)

| Priority | Stack | Role |
|----------|--------|------|
| **Primary** | **Kotlin + Jetpack Compose** + **FFmpeg-Kit** + **Zip** (+ DICOM via Java lib / ported logic) | Production offline APK |
| **Spike only** | Chaquopy (embed CPython) | ≤2 weeks; kill if size/perf fails |
| **Not chosen** | BeeWare; WebView + local Python server; full PyPI stack in APK as long-term | — |

### Why not “just ship the Python engine”?

The desktop app reuses FastAPI + `web/` + pywebview on **loopback**. On Android that pattern fights the OS (process model, background limits, store policy) and the scientific stack (**pydicom / numpy / imageio-ffmpeg / unrar**) blows up APK size and ARM packaging.

**Reuse product semantics** (params, phases, series naming, merge rules), **not** the CPython process, for a maintainable offline tool.

### Primary architecture

```
Compose UI
  → ViewModel / UseCase
    → Archive extract (Zip; RAR later)
    → Dicom discover/sort/window (Java DICOM lib or ported rules)
    → Encode (FFmpeg-Kit → MP4; GIF optional later)
    → App storage + Share/Export
```

No network calls in the convert path.

### Contract (same as desktop/web)

```
Input:  SAF / file path → zip|rar|...
Params: format, quality, merge, fps   # ConvertParams
Progress: phase + percent             # ProgressEvent-like
Output: files in app storage + export
```

### Spike kill criteria (Chaquopy)

Abandon embedded Python if any:

- APK (with deps) ≳ 150–200 MB after reasonable stripping  
- Mid-range device convert time >> desktop Python for same study  
- Cannot ship a reliable ffmpeg (or encoder) offline  

### Next engineering steps

1. Android Studio module under `apps/offline/android/app/` (A2)  
2. Zip pick + extract + list files UI  
3. Wire FFmpeg-Kit smoke (e.g. images → mp4)  
4. DICOM path: evaluate dcm4che subset vs minimal port from `engine/`  
5. Offline E2E on airplane mode  

Windows packaging remains independent (`dicomflow app` + PyInstaller).
