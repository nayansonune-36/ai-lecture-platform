"""CLI tool to run media transcoding pipeline on local files for testing."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from settings import get_settings
from transcode_job import transcode_lecture_job
from transcoder import probe_video, run_transcode_pipeline


async def _main_async(args: argparse.Namespace) -> int:
    input_path = Path(args.input_file).resolve()
    if not input_path.exists():
        print(f"Error: Input file does not exist: {input_path}", file=sys.stderr)
        return 1

    settings = get_settings()
    ffmpeg_bin = args.ffmpeg or settings.get_ffmpeg_binary()
    ffprobe_bin = args.ffprobe or settings.get_ffprobe_binary()

    print("=== AI Lecture Platform Transcoder CLI ===")
    print(f"Input file:   {input_path}")
    print(f"FFmpeg bin:   {ffmpeg_bin}")
    print(f"FFprobe bin:  {ffprobe_bin}")

    if args.lecture_id and not args.skip_db:
        print(f"\nRunning with Database for lecture_id={args.lecture_id}...")
        try:
            result = await transcode_lecture_job(
                lecture_id=args.lecture_id,
                job_id=args.job_id,
                attempt=1,
                ffmpeg_binary=ffmpeg_bin,
                ffprobe_binary=ffprobe_bin,
            )
            print("\nDatabase update and transcode complete!")
            print(json.dumps(result, indent=2))
            return 0
        except Exception as exc:
            print(f"Error executing transcode job: {exc}", file=sys.stderr)
            return 1

    # Standalone mode: transcode to output directory without DB
    out_dir = Path(args.output_dir or "./output_hls").resolve()
    print(f"Output HLS:   {out_dir}")

    try:
        print("\n1. Probing video metadata...")
        meta = await probe_video(input_path, ffprobe_binary=ffprobe_bin)
        print(f"   Duration:  {meta.duration_s:.2f}s ({meta.duration_ms} ms)")
        print(
            f"   Video:     {meta.video.width}x{meta.video.height} @ "
            f"{meta.video.fps:.2f} fps ({meta.video.codec_name})"
        )
        print(f"   Audio:     {meta.audio.codec_name if meta.audio else 'None (silent)'}")

        print("\n2. Executing transcode pipeline...")
        res = await run_transcode_pipeline(
            input_path=input_path,
            output_hls_dir=out_dir,
            ffmpeg_binary=ffmpeg_bin,
            ffprobe_binary=ffprobe_bin,
        )

        print("\n3. Transcoding summary:")
        print(f"   Master playlist: {res.master_playlist}")
        print(f"   Poster image:    {res.poster_image}")
        print(f"   Thumbnails:      {len(res.thumbnails)} generated in {out_dir / 'thumbnails'}")
        print("   Renditions:")
        for r in res.renditions:
            print(
                f"     - {r.height}p: {r.width}x{r.height}, {r.bitrate_kbps} kbps, "
                f"size: {r.size_bytes:,} bytes, playlist: {r.playlist_rel_path}"
            )

        print("\nSUCCESS: All renditions and assets generated successfully.")
        return 0
    except Exception as exc:
        print(f"\nError: Transcoding failed: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Run lecture transcoding pipeline on a local media file for testing."
    )
    parser.add_argument(
        "input_file",
        help="Path to the source video file (mp4, mov, mkv, webm)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        help="Destination directory for HLS renditions (default: ./output_hls)",
    )
    parser.add_argument(
        "--lecture-id",
        help="Optional lecture UUID to update database record",
    )
    parser.add_argument(
        "--job-id",
        help="Optional job UUID to update database record",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip database updates and run only FFmpeg pipeline",
    )
    parser.add_argument(
        "--ffmpeg",
        help="Custom path to ffmpeg binary",
    )
    parser.add_argument(
        "--ffprobe",
        help="Custom path to ffprobe binary",
    )

    args = parser.parse_args()
    exit_code = asyncio.run(_main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
