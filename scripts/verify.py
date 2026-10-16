#!/usr/bin/env python3
"""Verify a completed render against its shared frame clock; decode every frame."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys

from render import timestamp


def verify(out):
    clock = json.loads((out/'timeline.json').read_text(encoding='utf-8'))
    render = json.loads((out/'render-report.json').read_text())
    if render['preview_only']:
        raise ValueError('preview-only output has no video to verify')
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(out/'video.mp4')], check=True, capture_output=True, text=True)
    meta = json.loads(probe.stdout)
    videos = [s for s in meta['streams'] if s['codec_type'] == 'video']
    audio = [s for s in meta['streams'] if s['codec_type'] == 'audio']
    if len(videos) != 1 or audio:
        raise ValueError('expected exactly one video stream and no audio')
    v = videos[0]
    if v['codec_name'] != 'h264' or v['pix_fmt'] != 'yuv420p':
        raise ValueError('expected H.264 / yuv420p')
    if f'{v["width"]}x{v["height"]}' != render['size']:
        raise ValueError('unexpected dimensions')
    if Fraction(v['avg_frame_rate']) != clock['fps'] or int(v['nb_frames']) != clock['frames']:
        raise ValueError('frame count or fps mismatch')
    if abs(float(v['duration']) - clock['duration']) > 1/clock['fps']:
        raise ValueError('duration mismatch')
    expected, previous = [], 0
    for i, c in enumerate(clock['captions'], 1):
        if c['start_frame'] != previous or c['end_frame'] <= previous:
            raise ValueError('caption gaps, overlaps, or empty interval')
        previous = c['end_frame']
        expected.extend([str(i), f'{timestamp(c["start_frame"], clock["fps"])} --> {timestamp(c["end_frame"], clock["fps"])}', c['text'], ''])
    if previous != clock['frames']:
        raise ValueError('captions do not cover full video')
    if (out/'captions.srt').read_text(encoding='utf-8') != '\n'.join(expected)+'\n':
        raise ValueError('SRT differs from the burn-in frame clock')
    decoded = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(out/'video.mp4'), '-map', '0:v:0', '-progress', 'pipe:1', '-nostats', '-f', 'null', '-'], check=True, capture_output=True, text=True)
    frames = [int(line.split('=', 1)[1]) for line in decoded.stdout.splitlines() if line.startswith('frame=')]
    if not frames or frames[-1] != clock['frames']:
        raise ValueError('full decode frame count mismatch')
    if decoded.stderr.strip():
        raise ValueError('decoder reported errors')
    report = dict(status='passed', decoded_frames=frames[-1], duration=clock['duration'], fps=clock['fps'], size=render['size'], codec=v['codec_name'], pixel_format=v['pix_fmt'], audio_streams=len(audio), captions=len(clock['captions']), caption_clock='contiguous and identical to SRT', visual_review='manual review required; see scene JPGs and contact sheets')
    (out/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.output), indent=2))
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print(f'verification failed: {exc}', file=sys.stderr)
        sys.exit(1)
