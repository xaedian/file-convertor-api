import os
import subprocess
import tempfile
import logging
from pathlib import Path

from fastapi import FastAPI, UploadFile, Query, HTTPException
from fastapi.responses import FileResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="File Converter API",
    description="Convert files using Vips with configurable quality and DPI",
    version="1.0.0",
)

# Vips format support matrix
# Maps (from, to) pairs to the Vips action and file extension
FORMAT_MAP = {
    # PDF inputs (via poppler)
    ("pdf", "jpeg"): {"action": "pdfload", "ext": ".jpg"},
    ("pdf", "png"): {"action": "pdfload", "ext": ".png"},
    ("pdf", "tiff"): {"action": "pdfload", "ext": ".tiff"},
    ("pdf", "webp"): {"action": "pdfload", "ext": ".webp"},
    ("pdf", "avif"): {"action": "pdfload", "ext": ".avif"},
    ("pdf", "heif"): {"action": "pdfload", "ext": ".heif"},
    ("pdf", "jxl"): {"action": "pdfload", "ext": ".jxl"},

    # Image inputs
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

    # SVG inputs (via librsvg)
    ("svg", "jpeg"): {"action": "rsvgload", "ext": ".jpg"},
    ("svg", "png"): {"action": "rsvgload", "ext": ".png"},
    ("svg", "webp"): {"action": "rsvgload", "ext": ".webp"},
    ("svg", "tiff"): {"action": "rsvgload", "ext": ".tiff"},

    # HEIF/HEIC
    ("heif", "jpeg"): {"action": "copy", "ext": ".jpg"},
    ("heif", "png"): {"action": "copy", "ext": ".png"},
    ("heif", "webp"): {"action": "copy", "ext": ".webp"},

    # AVIF
    ("avif", "jpeg"): {"action": "copy", "ext": ".jpg"},
    ("avif", "png"): {"action": "copy", "ext": ".png"},
    ("avif", "webp"): {"action": "copy", "ext": ".webp"},

    # JXL
    ("jxl", "jpeg"): {"action": "copy", "ext": ".jpg"},
    ("jxl", "png"): {"action": "copy", "ext": ".png"},
    ("jxl", "webp"): {"action": "copy", "ext": ".webp"},
}

# Formats that accept quality parameter
QUALITY_FORMATS = {"jpeg", "webp", "avif", "heif", "jxl"}

# Formats that accept DPI parameter
DPI_FORMATS = {"jpeg", "tiff"}

# Formats that accept scale parameter
SCALE_FORMATS = {"jpeg", "png", "webp", "tiff", "avif", "heif", "jxl"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/formats")
async def list_formats():
    """List all supported conversion pairs."""
    pairs = []
    for (from_fmt, to_fmt), info in FORMAT_MAP.items():
        pairs.append({
            "from": from_fmt,
            "to": to_fmt,
            "action": info["action"],
        })
    return {"formats": pairs}


@app.post("/convert")
async def convert_file(
    file: UploadFile,
    from_format: str = Query(..., description="Source format (pdf, png, jpeg, webp, tiff, svg, heif, avif, jxl)"),
    to_format: str = Query(..., description="Target format (jpeg, png, webp, tiff, avif, heif, jxl)"),
    dpi: int = Query(default=72, ge=1, le=1000, description="DPI for rendering (default: 72)"),
    quality: int = Query(default=75, ge=1, le=100, description="Quality for lossy formats (default: 75)"),
    scale: float = Query(default=1.0, ge=0.1, le=10.0, description="Scale factor (default: 1.0)"),
    page: int = Query(default=0, ge=0, description="Page number for PDFs (default: 0)"),
):
    """Convert a file using Vips."""
    from_format = from_format.lower().strip(".")
    to_format = to_format.lower().strip(".")

    key = (from_format, to_format)
    if key not in FORMAT_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported conversion: {from_format} -> {to_format}. Use /formats to see supported pairs.",
        )

    fmt_info = FORMAT_MAP[key]
    action = fmt_info["action"]
    ext = fmt_info["ext"]

    with tempfile.NamedTemporaryFile(suffix=f".{from_format}", delete=False) as src:
        content = await file.read()
        src.write(content)
        src_path = src.name

    # Intermediate format for PDFs (all pages concatenated vertically)
    tmp_path = src_path + ".tif"
    dst_path = src_path + ext

    try:
        if action == "pdfload":
            # Step 1: Load ALL pages from PDF, stacked vertically into one tall image
            load_cmd = ["vips", "pdfload", src_path, tmp_path, "--dpi", str(dpi), "--n", "-1"]
            if scale != 1.0:
                load_cmd.extend(["--scale", str(scale)])

            logger.info(f"Running: {' '.join(load_cmd)}")
            result = subprocess.run(load_cmd, capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                logger.error(f"Vips pdfload error: {result.stderr}")
                raise HTTPException(status_code=500, detail=f"PDF load failed: {result.stderr}")

            # Step 2: Save to target format with quality
            save_action = {
                "jpeg": "jpegsave",
                "jpg": "jpegsave",
                "png": "pngsave",
                "webp": "webpsave",
                "tiff": "tiffsave",
                "tif": "tiffsave",
                "avif": "avifsave",
                "heif": "heifsave",
                "jxl": "jxlsave",
            }.get(to_format)

            if not save_action:
                raise HTTPException(status_code=400, detail=f"No save action for {to_format}")

            save_cmd = ["vips", save_action, tmp_path, dst_path]
            if to_format in QUALITY_FORMATS:
                save_cmd.extend(["--Q", str(quality)])

            logger.info(f"Running: {' '.join(save_cmd)}")
            result = subprocess.run(save_cmd, capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                logger.error(f"Vips save error: {result.stderr}")
                raise HTTPException(status_code=500, detail=f"Save failed: {result.stderr}")

        else:
            # Direct image-to-image conversion
            cmd = ["vips", action, src_path, dst_path]
            if to_format in QUALITY_FORMATS:
                cmd.extend(["--Q", str(quality)])
            if to_format in SCALE_FORMATS and scale != 1.0:
                cmd.extend(["--scale", str(scale)])

            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                logger.error(f"Vips error: {result.stderr}")
                raise HTTPException(status_code=500, detail=f"Conversion failed: {result.stderr}")

        if not os.path.exists(dst_path):
            raise HTTPException(status_code=500, detail="Conversion produced no output file")

        media_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
            ".avif": "image/avif",
            ".heif": "image/heif",
            ".jxl": "image/jxl",
        }

        return FileResponse(
            path=dst_path,
            media_type=media_types.get(ext, "application/octet-stream"),
            filename=f"converted{ext}",
        )

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Conversion timed out after 60s")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error during conversion")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for path in [src_path, dst_path, tmp_path]:
            if os.path.exists(path):
                os.unlink(path)
