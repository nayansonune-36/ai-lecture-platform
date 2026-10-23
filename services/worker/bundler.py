"""Offline bundle packaging service."""

import hashlib
import json
import logging
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Minimal valid 1x1 JPEG image bytes used as fallback
MINIMAL_JPEG = bytes(
    [
        0xFF,
        0xD8,
        0xFF,
        0xE0,
        0x00,
        0x10,
        0x4A,
        0x46,
        0x49,
        0x46,
        0x00,
        0x01,
        0x01,
        0x01,
        0x00,
        0x48,
        0x00,
        0x48,
        0x00,
        0x00,
        0xFF,
        0xDB,
        0x00,
        0x43,
        0x00,
        0x08,
        0x06,
        0x06,
        0x07,
        0x06,
        0x05,
        0x08,
        0x07,
        0x07,
        0x07,
        0x09,
        0x09,
        0x08,
        0x0A,
        0x0C,
        0x14,
        0x0D,
        0x0C,
        0x0B,
        0x0B,
        0x0C,
        0x19,
        0x12,
        0x13,
        0x0F,
        0x14,
        0x1D,
        0x1A,
        0x1F,
        0x1E,
        0x1D,
        0x1A,
        0x1C,
        0x1C,
        0x20,
        0x24,
        0x2E,
        0x27,
        0x20,
        0x22,
        0x2C,
        0x23,
        0x1C,
        0x1C,
        0x28,
        0x37,
        0x29,
        0x2C,
        0x30,
        0x31,
        0x34,
        0x34,
        0x34,
        0x1F,
        0x27,
        0x39,
        0x3D,
        0x38,
        0x32,
        0x3C,
        0x2E,
        0x33,
        0x34,
        0x32,
        0xFF,
        0xC0,
        0x00,
        0x0B,
        0x08,
        0x00,
        0x01,
        0x00,
        0x01,
        0x01,
        0x01,
        0x11,
        0x00,
        0xFF,
        0xC4,
        0x00,
        0x1F,
        0x00,
        0x00,
        0x01,
        0x05,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x01,
        0x02,
        0x03,
        0x04,
        0x05,
        0x06,
        0x07,
        0x08,
        0x09,
        0x0A,
        0x0B,
        0xFF,
        0xDA,
        0x00,
        0x08,
        0x01,
        0x01,
        0x00,
        0x00,
        0x3F,
        0x00,
        0xBF,
        0x80,
        0xFF,
        0xD9,
    ]
)


def make_relative_media_playlist(index_m3u8_content: str) -> str:
    """Ensure media.m3u8 references only relative segment and init filenames."""
    lines = index_m3u8_content.splitlines()
    sanitized: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            sanitized.append("")
            continue
        if stripped.startswith("#EXT-X-MAP:URI="):
            # Extract URI string e.g. URI=".../init.mp4"
            uri_part = stripped.split("URI=", 1)[1].strip('"')
            filename = Path(uri_part).name
            sanitized.append(f'#EXT-X-MAP:URI="{filename}"')
        elif not stripped.startswith("#"):
            # This is a segment file path
            filename = Path(stripped).name
            sanitized.append(filename)
        else:
            sanitized.append(stripped)
    return "\n".join(sanitized) + "\n"


def make_single_variant_master(
    master_m3u8_path: Path | None,
    rendition: int,
    bitrate_kbps: int = 1200,
) -> str:
    """Create a single-variant master playlist pointing to media.m3u8."""
    if master_m3u8_path and master_m3u8_path.is_file():
        content = master_m3u8_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        stream_inf_line: str | None = None
        for i, line in enumerate(lines):
            target = f"{rendition}p/index.m3u8"
            if target in line and i > 0 and lines[i - 1].startswith("#EXT-X-STREAM-INF"):
                stream_inf_line = lines[i - 1]
                break
        if stream_inf_line:
            return f"#EXTM3U\n#EXT-X-VERSION:7\n\n{stream_inf_line}\nmedia.m3u8\n"

    # Fallback calculated master
    width = int(round(rendition * 16 / 9 / 2)) * 2
    bandwidth = bitrate_kbps * 1000
    return (
        "#EXTM3U\n"
        "#EXT-X-VERSION:7\n\n"
        f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={width}x{rendition},CODECS="avc1.4d401f,mp4a.40.2"\n'
        "media.m3u8\n"
    )


def build_bundle_zip(
    storage_root: Path,
    lecture_id: uuid.UUID,
    rendition: int,
    version: int,
    lecture_title: str,
    course_title: str,
    duration_ms: int | None,
    chapters: list[dict[str, Any]] | None = None,
    captions_vtt: str | None = None,
    poster_bytes: bytes | None = None,
    bitrate_kbps: int = 1200,
) -> dict[str, Any]:
    """Assemble all offline package files into one uncompressed ZIP archive.

    Returns dictionary containing bundle metadata, file path, size, and sha256.
    """
    rendition_dir = storage_root / "lectures" / str(lecture_id) / "hls" / f"{rendition}p"
    index_m3u8_file = rendition_dir / "index.m3u8"
    if not index_m3u8_file.is_file():
        raise FileNotFoundError(
            f"Rendition playlist not found at {index_m3u8_file}. Lecture must be transcoded first."
        )

    # 1. Prepare hls/media.m3u8
    index_content = index_m3u8_file.read_text(encoding="utf-8")
    media_m3u8_content = make_relative_media_playlist(index_content)
    media_m3u8_bytes = media_m3u8_content.encode("utf-8")

    # 2. Prepare hls/master.m3u8
    original_master = storage_root / "lectures" / str(lecture_id) / "hls" / "master.m3u8"
    master_m3u8_content = make_single_variant_master(
        master_m3u8_path=original_master if original_master.is_file() else None,
        rendition=rendition,
        bitrate_kbps=bitrate_kbps,
    )
    master_m3u8_bytes = master_m3u8_content.encode("utf-8")

    # 3. Collect media segments and init
    media_files: list[tuple[str, bytes]] = [
        ("hls/master.m3u8", master_m3u8_bytes),
        ("hls/media.m3u8", media_m3u8_bytes),
    ]

    init_file = rendition_dir / "init.mp4"
    if init_file.is_file():
        media_files.append(("hls/init.mp4", init_file.read_bytes()))

    for seg in sorted(rendition_dir.glob("segment_*.m4s")):
        media_files.append((f"hls/{seg.name}", seg.read_bytes()))

    # 4. Prepare poster.jpg
    if poster_bytes is not None:
        poster_data = poster_bytes
    else:
        disk_poster = storage_root / "lectures" / str(lecture_id) / "hls" / "poster.jpg"
        if disk_poster.is_file():
            poster_data = disk_poster.read_bytes()
        else:
            poster_data = MINIMAL_JPEG
    media_files.append(("poster.jpg", poster_data))

    # 5. Prepare captions.vtt
    if captions_vtt is not None and captions_vtt.strip():
        vtt_content = captions_vtt.strip()
        if not vtt_content.startswith("WEBVTT"):
            vtt_content = "WEBVTT\n\n" + vtt_content
        vtt_bytes = (vtt_content + "\n").encode("utf-8")
    else:
        vtt_bytes = b"WEBVTT\n\n"
    media_files.append(("captions.vtt", vtt_bytes))

    # 6. Prepare chapters.json
    chapters_list = chapters if chapters is not None else []
    chapters_bytes = json.dumps(chapters_list, indent=2).encode("utf-8") + b"\n"
    media_files.append(("chapters.json", chapters_bytes))

    # 7. Compute file hashes for manifest.json
    files_meta: list[dict[str, Any]] = []
    for rel_path, data in media_files:
        files_meta.append(
            {
                "path": rel_path,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )

    # Sort files deterministically by path
    files_meta.sort(key=lambda x: str(x["path"]))

    # 8. Create manifest.json
    manifest_obj: dict[str, Any] = {
        "schema_version": 1,
        "lecture_id": str(lecture_id),
        "title": lecture_title,
        "course_title": course_title,
        "duration_ms": duration_ms,
        "rendition": rendition,
        "created_at": datetime.now(UTC).isoformat(),
        "files": files_meta,
        "ai_index": None,
    }
    manifest_bytes = json.dumps(manifest_obj, indent=2).encode("utf-8") + b"\n"

    # 9. Write ZIP archive with ZIP_STORED (no compression)
    out_dir = storage_root / "bundles" / str(lecture_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    zip_filename = f"{rendition}p-v{version}.zip"
    final_zip_path = out_dir / zip_filename
    temp_zip_path = out_dir / f"{zip_filename}.tmp"

    try:
        with zipfile.ZipFile(temp_zip_path, mode="w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr("manifest.json", manifest_bytes)
            for rel_path, data in media_files:
                zf.writestr(rel_path, data)

        # Atomic replace
        temp_zip_path.replace(final_zip_path)
    finally:
        if temp_zip_path.exists():
            try:
                temp_zip_path.unlink()
            except OSError:
                pass

    # 10. Compute zip sha256 and size_bytes
    hasher = hashlib.sha256()
    with open(final_zip_path, "rb") as fp:
        while chunk := fp.read(65536):
            hasher.update(chunk)
    zip_sha256 = hasher.hexdigest()
    zip_size = final_zip_path.stat().st_size

    rel_storage_path = f"bundles/{lecture_id}/{zip_filename}"

    logger.info(
        "Built bundle zip: %s (%d bytes, sha256=%s...)",
        rel_storage_path,
        zip_size,
        zip_sha256[:12],
    )

    return {
        "path": rel_storage_path,
        "size_bytes": zip_size,
        "sha256": zip_sha256,
        "version": version,
        "manifest": manifest_obj,
        "file_path": final_zip_path,
    }
