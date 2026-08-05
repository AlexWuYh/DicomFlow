from pathlib import Path

from fastapi.testclient import TestClient

from dicomflow.api.app import create_app
from dicomflow.api.deps import get_job_service


def test_upload_then_convert_without_reupload(tmp_path, monkeypatch):
    # Isolate data dir
    monkeypatch.setenv("DICOMFLOW_DATA_DIR", str(tmp_path / "data"))
    get_job_service.cache_clear()

    sample = Path("data/sample_dicom")
    if not sample.exists():
        # skip if sample missing
        return

    # Zip sample dicoms
    import zipfile

    zpath = tmp_path / "s.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for p in sample.glob("*.dcm"):
            zf.write(p, arcname=p.name)

    client = TestClient(create_app())

    with zpath.open("rb") as f:
        up = client.post("/api/v1/uploads", files={"file": ("s.zip", f, "application/zip")})
    assert up.status_code == 201
    upload_id = up.json()["upload_id"]
    assert up.json()["size_bytes"] > 0

    # Start convert twice with same upload_id (no re-upload)
    for merge in (False, True):
        job = client.post(
            "/api/v1/jobs",
            json={
                "upload_id": upload_id,
                "format": "mp4",
                "quality": "low",
                "merge": merge,
                "fps": 5,
            },
        )
        assert job.status_code == 202
        job_id = job.json()["job_id"]

        # Poll
        import time

        final = None
        for _ in range(60):
            st = client.get(f"/api/v1/jobs/{job_id}")
            assert st.status_code == 200
            body = st.json()
            if body["status"] in ("SUCCEEDED", "FAILED"):
                final = body
                break
            time.sleep(0.25)
        assert final is not None
        assert final["status"] == "SUCCEEDED", final
        assert final["result"]["outputs"]

        # Preview at least one file if present
        previewables = [o for o in final["result"]["outputs"] if o.get("previewable")]
        if previewables:
            name = previewables[0]["name"]
            prev = client.get(f"/api/v1/jobs/{job_id}/files/{name}")
            assert prev.status_code == 200
            assert len(prev.content) > 0

        dl = client.get(f"/api/v1/jobs/{job_id}/download")
        assert dl.status_code == 200
        assert len(dl.content) > 0

    get_job_service.cache_clear()
