import os
import subprocess
import tempfile
import logging
import shutil

from fastapi import FastAPI, UploadFile, Query, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="File Converter API",
    description="Convert files using Vips with configurable quality and DPI",
    version="1.1.0",
)

FORMAT_MAP = {
    ("pdf", "jpeg"): {"action": "pdfload", "ext": ".jpg"},
    ("pdf", "png"): {"action": "pdfload", "ext": ".png"},
    ("pdf", "tiff"): {"action": "pdfload", "ext": ".tiff"},
    ("pdf", "webp"): {"action": "pdfload", "ext": ".webp"},
    ("pdf", "avif"): {"action": "pdfload", "ext": ".avif"},
    ("pdf", "heif"): {"action": "pdfload", "ext": ".heif"},
    ("pdf", "jxl"): {"action": "pdfload", "ext": ".jxl"},
    ("png", "jpeg"): {"action": "copy", "ext": ".jpg"},
    ("png", "webp"): {"action": "copy", "ext": ".webp"},
    ("png", "tiff"): {"action": "copy", "ext": ".tiff"},
    ("png", "avif"): {"action": "copy", "ext": ".avif"},
    ("png", "heif"): {"action": "copy", "ext": ".heif"},
    ("png", "jxl"): {"action": "copy", "ext": ".jxl"},
    ("jpeg", "png"): {"action": "copy", "ext": ".png"},
    ("jpeg", "webp"): {"action": "copy", "ext": ".webp"},
    ("jpeg", "tiff"): {"action": "copy", "ext": ".tiff"},
    ("jpeg", "avif"): {"action": "copy", "ext": ".avif"},
    ("jpeg", "heif"): {"action": "copy", "ext": ".heif"},
    ("jpeg", "jxl"): {"action": "copy", "ext": ".jxl"},
    ("webp", "jpeg"): {"action": "copy", "ext": ".jpg"},
    ("webp", "png"): {"action": "copy", "ext": ".png"},
    ("webp", "tiff"): {"action": "copy", "ext": ".tiff"},
    ("webp", "avif"): {"action": "copy", "ext": ".avif"},
    ("webp", "heif"): {"action": "copy", "ext": ".heif"},
    ("tiff", "jpeg"): {"action": "copy", "ext": ".jpg"},
    ("tiff", "png"): {"action": "copy", "ext": ".png"},
    ("tiff", "webp"): {"action": "copy", "ext": ".webp"},
    ("svg", "jpeg"): {"action": "rsvgload", "ext": ".jpg"},
    ("svg", "png"): {"action": "rsvgload", "ext": ".png"},
    ("svg", "webp"): {"action": "rsvgload", "ext": ".webp"},
    ("svg", "tiff"): {"action": "rsvgload", "ext": ".tiff"},
    ("heif", "jpeg"): {"action": "copy", "ext": ".jpg"},
    ("heif", "png"): {"action": "copy", "ext": ".png"},
    ("heif", "webp"): {"action": "copy", "ext": ".webp"},
    ("avif", "jpeg"): {"action": "copy", "ext": ".jpg"},
    ("avif", "png"): {"action": "copy", "ext": ".png"},
    ("avif", "webp"): {"action": "copy", "ext": ".webp"},
    ("jxl", "jpeg"): {"action": "copy", "ext": ".jpg"},
    ("jxl", "png"): {"action": "copy", "ext": ".png"},
    ("jxl", "webp"): {"action": "copy", "ext": ".webp"},
}

QUALITY_FORMATS = {"jpeg", "webp", "avif", "heif", "jxl"}
SCALE_FORMATS = {"jpeg", "png", "webp", "tiff", "avif", "heif", "jxl"}

SAVE_ACTIONS = {
    "jpeg": "jpegsave", "jpg": "jpegsave",
    "png": "pngsave", "webp": "webpsave",
    "tiff": "tiffsave", "tif": "tiffsave",
    "avif": "avifsave", "heif": "heifsave", "jxl": "jxlsave",
}

MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
    ".tiff": "image/tiff", ".tif": "image/tiff",
    ".avif": "image/avif", ".heif": "image/heif", ".jxl": "image/jxl",
}


def cleanup(*paths):
    for p in paths:
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        elif os.path.exists(p):
            os.unlink(p)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/formats")
async def list_formats():
    return {"formats": [{"from": f, "to": t} for (f, t) in FORMAT_MAP]}


@app.post("/convert")
async def convert_file(
    file: UploadFile,
    from_format: str = Query(..., description="Source format"),
    to_format: str = Query(..., description="Target format"),
    dpi: int = Query(default=72, ge=1, le=1000),
    quality: int = Query(default=75, ge=1, le=100),
    scale: float = Query(default=1.0, ge=0.1, le=10.0),
):
    from_format = from_format.lower().strip(".")
    to_format = to_format.lower().strip(".")

    key = (from_format, to_format)
    if key not in FORMAT_MAP:
        raise HTTPException(400, f"Unsupported: {from_format} -> {to_format}")

    fmt_info = FORMAT_MAP[key]
    action = fmt_info["action"]
    ext = fmt_info["ext"]

    work_dir = tempfile.mkdtemp()
    src_path = os.path.join(work_dir, f"input.{from_format}")
    tmp_path = os.path.join(work_dir, "intermediate.tif")
    dst_path = os.path.join(work_dir, f"output{ext}")

    try:
        content = await file.read()
        with open(src_path, "wb") as f:
            f.write(content)

        if action == "pdfload":
            load_cmd = ["vips", "pdfload", src_path, tmp_path, "--dpi", str(dpi), "--n", "-1"]
            if scale != 1.0:
                load_cmd.extend(["--scale", str(scale)])
            logger.info(f"Running: {' '.join(load_cmd)}")
            r = subprocess.run(load_cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                raise HTTPException(500, f"PDF load failed: {r.stderr}")

            save_action = SAVE_ACTIONS.get(to_format)
            if not save_action:
                raise HTTPException(400, f"No save action for {to_format}")

            save_cmd = ["vips", save_action, tmp_path, dst_path]
            if to_format in QUALITY_FORMATS:
                save_cmd.extend(["--Q", str(quality)])
            logger.info(f"Running: {' '.join(save_cmd)}")
            r = subprocess.run(save_cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                raise HTTPException(500, f"Save failed: {r.stderr}")
        else:
            cmd = ["vips", action, src_path, dst_path]
            if to_format in QUALITY_FORMATS:
                cmd.extend(["--Q", str(quality)])
            if to_format in SCALE_FORMATS and scale != 1.0:
                cmd.extend(["--scale", str(scale)])
            logger.info(f"Running: {' '.join(cmd)}")
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                raise HTTPException(500, f"Conversion failed: {r.stderr}")

        if not os.path.exists(dst_path):
            raise HTTPException(500, "Conversion produced no output file")

        return FileResponse(
            path=dst_path,
            media_type=MEDIA_TYPES.get(ext, "application/octet-stream"),
            filename=f"converted{ext}",
            background=BackgroundTask(cleanup, work_dir),
        )

    except subprocess.TimeoutExpired:
        cleanup(work_dir)
        raise HTTPException(504, "Conversion timed out")
    except HTTPException:
        cleanup(work_dir)
        raise
    except Exception as e:
        cleanup(work_dir)
        logger.exception("Unexpected error")
        raise HTTPException(500, str(e))
