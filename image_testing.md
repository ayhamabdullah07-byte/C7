# C1 – AI Image Testing Notes

- Always use base64-encoded images (JPEG/PNG/WEBP). No SVG/BMP/HEIC.
- Images must contain real visual features (not solid color).
- Transcode to PNG/JPEG if not one of the accepted formats; re-detect MIME after transformation.
- For animated formats (GIF/APNG), use the first frame only.
- Keep payloads reasonable (resize large images).
