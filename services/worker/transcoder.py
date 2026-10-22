"""FFprobe metadata extraction and FFmpeg HLS fMP4 transcoding pipeline."""

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class VideoStreamInfo:
    """Video stream technical attributes."""

    width: int
    height: int
    codec_name: str
    fps: float
    duration_s: float


@dataclass
class AudioStreamInfo:
    """Audio stream technical attributes."""

    codec_name: str
    channels: int
    duration_s: float


@dataclass
class VideoMetadata:
    """Probed metadata for a media asset."""

    duration_s: float
    duration_ms: int
    video: VideoStreamInfo
    audio: AudioStreamInfo | None

    @property
    def has_audio(self) -> bool:
        """Check if audio stream is present."""
        return self.audio is not None


@dataclass
class RenditionTarget:
    """Target resolution profile for HLS fMP4 encoding."""

    height: int
    video_bitrate_kbps: int
    audio_bitrate_kbps: int
    h264_profile: str = "main"
    h264_level: str = "3.1"


@dataclass
class RenditionResult:
    """Result of encoding a single rendition profile."""

    height: int
    width: int
    bitrate_kbps: int
    playlist_rel_path: str
    output_dir: Path
    size_bytes: int


# Standard rendition targets: 720p, 480p, 360p
STANDARD_RENDITIONS = [
    RenditionTarget(
        height=720,
        video_bitrate_kbps=2500,
        audio_bitrate_kbps=128,
        h264_profile="high",
        h264_level="3.1",
    ),
    RenditionTarget(
        height=480,
        video_bitrate_kbps=1200,
        audio_bitrate_kbps=96,
        h264_profile="main",
        h264_level="3.1",
    ),
    RenditionTarget(
        height=360,
        video_bitrate_kbps=600,
        audio_bitrate_kbps=64,
        h264_profile="main",
        h264_level="3.0",
    ),
]


async def _run_command(cmd: list[str], description: str, cwd: Path | None = None) -> str:
    """Execute external CLI command asynchronously and return stdout."""
    logger.debug("Executing %s: %s (cwd=%s)", description, " ".join(cmd), cwd)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace")
        logger.error("%s failed with exit code %d:\n%s", description, proc.returncode, err_msg)
        raise RuntimeError(f"{description} failed (exit {proc.returncode}): {err_msg[:400]}")
    return stdout.decode("utf-8", errors="replace")


async def probe_video(video_path: Path, ffprobe_binary: str | None = None) -> VideoMetadata:
    """Probe media container with ffprobe to extract streams and duration."""
    if not video_path.exists():
        raise FileNotFoundError(f"Input video file not found at {video_path}")

    binary = ffprobe_binary or get_settings().get_ffprobe_binary()
    cmd = [
        binary,
        "-v",
        "error",
        "-show_entries",
        "stream=index,codec_type,codec_name,width,height,r_frame_rate,duration",
        "-show_entries",
        "format=duration,size",
        "-of",
        "json",
        str(video_path),
    ]

    stdout = await _run_command(cmd, f"ffprobe on {video_path.name}")
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse ffprobe output for {video_path}: {exc}") from exc

    streams = data.get("streams", [])
    format_info = data.get("format", {})

    video_stream: dict[str, Any] | None = None
    audio_stream: dict[str, Any] | None = None

    for s in streams:
        if s.get("codec_type") == "video" and video_stream is None:
            video_stream = s
        elif s.get("codec_type") == "audio" and audio_stream is None:
            audio_stream = s

    if video_stream is None:
        raise ValueError(f"No video stream found in {video_path}")

    # Determine duration
    duration_s = 0.0
    if "duration" in format_info and format_info["duration"] != "N/A":
        duration_s = float(format_info["duration"])
    elif "duration" in video_stream and video_stream["duration"] != "N/A":
        duration_s = float(video_stream["duration"])
    elif audio_stream and "duration" in audio_stream and audio_stream["duration"] != "N/A":
        duration_s = float(audio_stream["duration"])

    if duration_s <= 0.0:
        logger.warning("Could not determine duration from container; assuming 1.0s fallback")
        duration_s = 1.0

    duration_ms = int(round(duration_s * 1000))

    # Parse frame rate
    fps = 30.0
    r_frame_rate = video_stream.get("r_frame_rate", "30/1")
    if "/" in r_frame_rate:
        num, den = r_frame_rate.split("/", 1)
        try:
            den_f = float(den)
            if den_f > 0:
                fps = float(num) / den_f
        except (ValueError, ZeroDivisionError):
            fps = 30.0
    else:
        try:
            fps = float(r_frame_rate)
        except ValueError:
            fps = 30.0

    width = int(video_stream.get("width", 1280))
    height = int(video_stream.get("height", 720))
    v_codec = str(video_stream.get("codec_name", "unknown"))

    video_info = VideoStreamInfo(
        width=width,
        height=height,
        codec_name=v_codec,
        fps=fps,
        duration_s=duration_s,
    )

    audio_info: AudioStreamInfo | None = None
    if audio_stream is not None:
        a_dur = duration_s
        if "duration" in audio_stream and audio_stream["duration"] != "N/A":
            try:
                a_dur = float(audio_stream["duration"])
            except ValueError:
                pass
        audio_info = AudioStreamInfo(
            codec_name=str(audio_stream.get("codec_name", "aac")),
            channels=int(audio_stream.get("channels", 2)),
            duration_s=a_dur,
        )

    return VideoMetadata(
        duration_s=duration_s,
        duration_ms=duration_ms,
        video=video_info,
        audio=audio_info,
    )


def select_renditions(source_height: int) -> list[RenditionTarget]:
    """Select rendition profiles, skipping any larger than source."""
    # Filter standard renditions: skip renditions larger than the source
    chosen = [r for r in STANDARD_RENDITIONS if r.height <= source_height]

    # If source is smaller than 360p, create a custom rendition matching source
    if not chosen:
        chosen = [
            RenditionTarget(
                height=source_height,
                video_bitrate_kbps=max(300, min(600, source_height * 2)),
                audio_bitrate_kbps=64,
                h264_profile="main",
                h264_level="3.0",
            )
        ]
    return chosen


async def transcode_rendition(
    input_path: Path,
    output_dir: Path,
    target: RenditionTarget,
    has_audio: bool,
    source_width: int,
    source_height: int,
    ffmpeg_binary: str | None = None,
) -> RenditionResult:
    """Encode single HLS fMP4 rendition (6s segments, init.mp4, index.m3u8)."""
    binary = ffmpeg_binary or get_settings().get_ffmpeg_binary()
    output_dir.mkdir(parents=True, exist_ok=True)

    calc_width = int(round(source_width * (target.height / source_height)))
    calc_width = (calc_width // 2) * 2  # Must be even for libx264

    cmd = [
        binary,
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-profile:v",
        target.h264_profile,
        "-level",
        target.h264_level,
        "-b:v",
        f"{target.video_bitrate_kbps}k",
        "-maxrate",
        f"{int(target.video_bitrate_kbps * 1.2)}k",
        "-bufsize",
        f"{target.video_bitrate_kbps * 2}k",
        "-vf",
        f"scale=-2:{target.height}",
        "-pix_fmt",
        "yuv420p",
    ]

    if has_audio:
        cmd.extend(
            [
                "-c:a",
                "aac",
                "-b:a",
                f"{target.audio_bitrate_kbps}k",
                "-ac",
                "2",
            ]
        )
        total_bitrate = target.video_bitrate_kbps + target.audio_bitrate_kbps
    else:
        cmd.append("-an")
        total_bitrate = target.video_bitrate_kbps

    cmd.extend(
        [
            "-f",
            "hls",
            "-hls_time",
            "6",
            "-hls_playlist_type",
            "vod",
            "-hls_segment_type",
            "fmp4",
            "-hls_flags",
            "independent_segments",
            "-hls_segment_filename",
            "segment_%03d.m4s",
            "-hls_fmp4_init_filename",
            "init.mp4",
            "index.m3u8",
        ]
    )

    await _run_command(cmd, f"HLS encode {target.height}p", cwd=output_dir)

    # Calculate total size of generated media files
    total_size = 0
    for root, _, files in os.walk(output_dir):
        for f in files:
            file_path = Path(root) / f
            total_size += file_path.stat().st_size

    return RenditionResult(
        height=target.height,
        width=calc_width,
        bitrate_kbps=total_bitrate,
        playlist_rel_path=f"{target.height}p/index.m3u8",
        output_dir=output_dir,
        size_bytes=total_size,
    )


def generate_master_playlist(
    renditions: list[RenditionResult],
    has_audio: bool,
    master_path: Path,
) -> None:
    """Create HLS master.m3u8 playlist referencing all encoded renditions."""
    lines = ["#EXTM3U", "#EXT-X-VERSION:7", ""]
    for r in sorted(renditions, key=lambda x: x.height, reverse=True):
        bandwidth = r.bitrate_kbps * 1000
        codecs = "avc1.4d401f,mp4a.40.2" if has_audio else "avc1.4d401f"
        lines.append(
            f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={r.width}x{r.height},CODECS="{codecs}"'
        )
        # Playlist relative path in master.m3u8
        lines.append(f"{r.height}p/index.m3u8")
        lines.append("")

    master_path.parent.mkdir(parents=True, exist_ok=True)
    master_path.write_text("\n".join(lines), encoding="utf-8")


async def generate_poster_image(
    input_path: Path,
    output_path: Path,
    duration_s: float,
    ffmpeg_binary: str | None = None,
) -> Path:
    """Extract a poster image frame at 10% of total video duration."""
    binary = ffmpeg_binary or get_settings().get_ffmpeg_binary()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 10% timestamp position
    poster_time = max(0.1, duration_s * 0.1)
    if duration_s < 1.0:
        poster_time = duration_s * 0.5

    cmd = [
        binary,
        "-y",
        "-ss",
        f"{poster_time:.2f}",
        "-i",
        str(input_path),
        "-vframes",
        "1",
        "-q:v",
        "2",
        str(output_path),
    ]

    await _run_command(cmd, f"poster extraction at {poster_time:.2f}s")
    return output_path


def _format_vtt_timestamp(seconds: float) -> str:
    """Format floating point seconds into HH:MM:SS.mmm."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{millis:03d}"


async def generate_thumbnails(
    input_path: Path,
    thumbnails_dir: Path,
    duration_s: float,
    ffmpeg_binary: str | None = None,
) -> list[Path]:
    """Generate scrubbing thumbnails every 5 seconds plus a WebVTT map."""
    binary = ffmpeg_binary or get_settings().get_ffmpeg_binary()
    thumbnails_dir.mkdir(parents=True, exist_ok=True)

    pattern = thumbnails_dir / "thumb_%04d.jpg"
    cmd = [
        binary,
        "-y",
        "-i",
        str(input_path),
        "-vf",
        "fps=1/5,scale=160:-2",
        "-q:v",
        "3",
        str(pattern),
    ]

    await _run_command(cmd, "thumbnail generation at 5s interval")

    thumb_files = sorted(thumbnails_dir.glob("thumb_*.jpg"))

    # Generate companion WebVTT file for timeline scrubbing
    vtt_lines = ["WEBVTT", ""]
    interval = 5.0
    for idx, thumb in enumerate(thumb_files):
        start = idx * interval
        end = min((idx + 1) * interval, duration_s)
        vtt_lines.append(f"{_format_vtt_timestamp(start)} --> {_format_vtt_timestamp(end)}")
        vtt_lines.append(f"{thumb.name}")
        vtt_lines.append("")

    vtt_file = thumbnails_dir / "thumbnails.vtt"
    vtt_file.write_text("\n".join(vtt_lines), encoding="utf-8")

    return thumb_files


@dataclass
class TranscodeResult:
    """Full transcoding pipeline output."""

    duration_ms: int
    duration_s: float
    renditions: list[RenditionResult]
    master_playlist: Path
    poster_image: Path
    thumbnails: list[Path]


async def run_transcode_pipeline(
    input_path: Path,
    output_hls_dir: Path,
    ffmpeg_binary: str | None = None,
    ffprobe_binary: str | None = None,
) -> TranscodeResult:
    """Execute complete transcoding pipeline: probe, renditions, master, poster, thumbnails."""
    logger.info("Starting transcode pipeline for %s -> %s", input_path, output_hls_dir)

    # Clean previous outputs in destination directory for complete idempotency
    if output_hls_dir.exists():
        for item in output_hls_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink(missing_ok=True)
    output_hls_dir.mkdir(parents=True, exist_ok=True)

    # 1. Probe input
    meta = await probe_video(input_path, ffprobe_binary=ffprobe_binary)
    logger.info(
        "Probed %s: %dx%d, %.2fs, audio=%s",
        input_path.name,
        meta.video.width,
        meta.video.height,
        meta.duration_s,
        meta.has_audio,
    )

    # 2. Select renditions (skip renditions larger than source)
    target_renditions = select_renditions(meta.video.height)
    logger.info(
        "Selected renditions: %s",
        [f"{r.height}p" for r in target_renditions],
    )

    # 3. Transcode each rendition
    rendition_results: list[RenditionResult] = []
    for target in target_renditions:
        rendition_dir = output_hls_dir / f"{target.height}p"
        res = await transcode_rendition(
            input_path=input_path,
            output_dir=rendition_dir,
            target=target,
            has_audio=meta.has_audio,
            source_width=meta.video.width,
            source_height=meta.video.height,
            ffmpeg_binary=ffmpeg_binary,
        )
        rendition_results.append(res)

    # 4. Generate master.m3u8
    master_path = output_hls_dir / "master.m3u8"
    generate_master_playlist(
        renditions=rendition_results,
        has_audio=meta.has_audio,
        master_path=master_path,
    )

    # 5. Extract poster image at 10%
    poster_path = output_hls_dir / "poster.jpg"
    await generate_poster_image(
        input_path=input_path,
        output_path=poster_path,
        duration_s=meta.duration_s,
        ffmpeg_binary=ffmpeg_binary,
    )

    # 6. Generate 5-second interval thumbnails
    thumbs_dir = output_hls_dir / "thumbnails"
    thumbnails = await generate_thumbnails(
        input_path=input_path,
        thumbnails_dir=thumbs_dir,
        duration_s=meta.duration_s,
        ffmpeg_binary=ffmpeg_binary,
    )

    return TranscodeResult(
        duration_ms=meta.duration_ms,
        duration_s=meta.duration_s,
        renditions=rendition_results,
        master_playlist=master_path,
        poster_image=poster_path,
        thumbnails=thumbnails,
    )
