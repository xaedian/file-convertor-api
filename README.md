# File Converter API

Convert files using Vips with configurable quality and DPI. Built for receipt scanning workflows.

## Quick Start

```bash
docker compose up -d
```

## Usage

### Convert PDF to JPEG

```bash
curl -X POST "http://localhost:3001/convert?from_format=pdf&to_format=jpeg&dpi=300&quality=95" \
  -F "file=@receipt.pdf" \
  --output receipt.jpg
```

### Convert PNG to WebP

```bash
curl -X POST "http://localhost:3001/convert?from_format=png&to_format=webp&quality=90" \
  -F "file=@image.png" \
  --output image.webp
```

### List Supported Formats

```bash
curl http://localhost:3001/formats
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `from_format` | (required) | Source format: pdf, png, jpeg, webp, tiff, svg, heif, avif, jxl |
| `to_format` | (required) | Target format: jpeg, png, webp, tiff, avif, heif, jxl |
| `dpi` | 72 | DPI for PDF rendering (1-1000) |
| `quality` | 75 | Quality for lossy formats (1-100) |
| `scale` | 1.0 | Scale factor (0.1-10.0) |
| `page` | 0 | Page number for PDFs |

## Health Check

```bash
curl http://localhost:3001/health
```

## Docker Compose

```yaml
receipt-converter:
  image: ghcr.io/xaedian/file-convertor-api:latest
  container_name: receipt-converter
  restart: unless-stopped
  ports:
    - '3001:3001'
```

## License

MIT
