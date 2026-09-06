from __future__ import annotations

import atexit
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from benchmark.capture import capture_to_temp_jpg
from benchmark.context import ContextStore
from benchmark.migrate import import_legacy_data
from benchmark.store import BenchmarkStore

ROOT = Path(__file__).resolve().parent
DATA_ROOT = ROOT / "data"
STATIC_ROOT = ROOT / "static"
store = BenchmarkStore(DATA_ROOT)
context_store = ContextStore(DATA_ROOT / "capture_context.json")

app = FastAPI(title="FocusGuard Screenshot Benchmark 0906")
_pending_image: Optional[Path] = None
_pending_metadata: dict = {}


class ContextPayload(BaseModel):
    mode: str = "guardian"
    task: str = ""
    supervision_level: Optional[str] = None
    activity: str = ""
    human_reason: str = ""
    split: str = "train"
    ai_label: str = ""
    ai_reason: str = ""
    ai_model: str = ""
    prompt_version: str = ""
    retriever_version: str = ""
    source_type: str = "manual_seed"
    review_status: str = "reviewed"


class SaveCapturePayload(ContextPayload):
    human_label: str


class MovePayload(BaseModel):
    split: str


class SampleUpdatePayload(BaseModel):
    mode: Optional[str] = None
    task: Optional[str] = None
    supervision_level: Optional[str] = None
    human_label: Optional[str] = None
    human_reason: Optional[str] = None
    activity: Optional[str] = None
    window_title: Optional[str] = None
    split: Optional[str] = None
    source_type: Optional[str] = None
    review_status: Optional[str] = None
    ai_label: Optional[str] = None
    ai_reason: Optional[str] = None
    ai_model: Optional[str] = None
    ai_confidence: Optional[float] = None
    judgement_status: Optional[str] = None
    trigger_category: Optional[str] = None
    prompt_version: Optional[str] = None
    retriever_version: Optional[str] = None


def _public_sample(sample: dict) -> dict:
    result = dict(sample)
    result["screenshot_url"] = f"/api/samples/{sample['id']}/image"
    return result


def _cleanup_pending() -> None:
    global _pending_image, _pending_metadata
    if _pending_image:
        _pending_image.unlink(missing_ok=True)
    _pending_image = None
    _pending_metadata = {}


atexit.register(_cleanup_pending)


@app.get("/api/health")
def health():
    samples = store.list_samples()
    return {
        "ok": True,
        "data_root": str(DATA_ROOT),
        "pending": bool(_pending_image and _pending_image.is_file()),
        "counts": {
            "total": len(samples),
            "train": sum(1 for sample in samples if sample["split"] == "train"),
            "test": sum(1 for sample in samples if sample["split"] == "test"),
        },
    }


@app.get("/api/context")
def get_context():
    return {"context": context_store.load()}


@app.put("/api/context")
def save_context(payload: ContextPayload):
    try:
        values = payload.model_dump()
    except AttributeError:  # Pydantic 1.x
        values = payload.dict()
    try:
        context = context_store.save(values)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"context": context}


@app.get("/api/samples")
def list_samples(
    split: Optional[str] = None,
    mode: Optional[str] = None,
    source_type: Optional[str] = None,
    review_status: Optional[str] = None,
):
    try:
        samples = store.list_samples(split)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if mode:
        samples = [sample for sample in samples if sample.get("mode") == mode]
    if source_type:
        samples = [sample for sample in samples if sample.get("source_type") == source_type]
    if review_status:
        samples = [sample for sample in samples if sample.get("review_status") == review_status]
    return {"samples": [_public_sample(sample) for sample in samples]}


@app.get("/api/samples/{sample_id}/image")
def sample_image(sample_id: str):
    sample = store.get(sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    path = store.screenshot_path(sample)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(str(path), media_type="image/jpeg")


@app.post("/api/capture")
def capture():
    global _pending_image, _pending_metadata
    _cleanup_pending()
    try:
        _pending_image, _pending_metadata = capture_to_temp_jpg()
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return {
        "pending": True,
        "image_url": "/api/pending-image",
        "metadata": _pending_metadata,
    }


@app.get("/api/pending-image")
def pending_image():
    if not _pending_image or not _pending_image.is_file():
        raise HTTPException(status_code=404, detail="No pending screenshot")
    return FileResponse(str(_pending_image), media_type="image/jpeg")


@app.delete("/api/pending")
def discard_pending():
    _cleanup_pending()
    return {"status": "discarded"}


@app.post("/api/capture/save")
def save_capture(payload: SaveCapturePayload):
    global _pending_image
    if not _pending_image or not _pending_image.is_file():
        raise HTTPException(status_code=400, detail="Please capture a screenshot first")
    try:
        values = payload.model_dump()
    except AttributeError:
        values = payload.dict()
    try:
        context_store.save({key: value for key, value in values.items() if key != "human_label"})
        sample = store.add_sample(
            source_image=_pending_image,
            mode=values["mode"],
            human_label=values["human_label"],
            split=values["split"],
            task=values["task"],
            supervision_level=values.get("supervision_level"),
            human_reason=values["human_reason"],
            activity=values["activity"],
            window_title=_pending_metadata.get("window_title", ""),
            ai_label=values["ai_label"],
            ai_reason=values["ai_reason"],
            ai_model=values["ai_model"],
            source_type=values["source_type"],
            review_status=values["review_status"],
            prompt_version=values["prompt_version"],
            retriever_version=values["retriever_version"],
        )
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    _cleanup_pending()
    return {"sample": _public_sample(sample)}


@app.patch("/api/samples/{sample_id}")
def update_sample(sample_id: str, payload: SampleUpdatePayload):
    try:
        values = payload.model_dump(exclude_unset=True)
    except AttributeError:
        values = payload.dict(exclude_unset=True)
    try:
        current = store.get(sample_id)
        if not current:
            raise KeyError(sample_id)
        requested_split = values.pop("split", None)
        if requested_split and requested_split != current["split"]:
            store.move(sample_id, requested_split)
        sample = store.update(sample_id, values)
    except KeyError:
        raise HTTPException(status_code=404, detail="Sample not found") from None
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"sample": _public_sample(sample)}


@app.post("/api/samples/{sample_id}/move")
def move_sample(sample_id: str, payload: MovePayload):
    try:
        sample = store.move(sample_id, payload.split)
    except KeyError:
        raise HTTPException(status_code=404, detail="Sample not found") from None
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"sample": _public_sample(sample)}


@app.delete("/api/samples/{sample_id}")
def delete_sample(sample_id: str):
    if not store.delete(sample_id):
        raise HTTPException(status_code=404, detail="Sample not found")
    return {"status": "deleted"}


@app.post("/api/import-0825")
def import_0825():
    roots = [
        ROOT.parent / "0825_bench" / "data",
        ROOT.parent / "0825_bench" / "dataTab" / "data",
    ]
    return import_legacy_data(store, roots)


app.mount("/", StaticFiles(directory=str(STATIC_ROOT), html=True), name="static")
