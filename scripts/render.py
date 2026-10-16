#!/usr/bin/env python3
"""Render a local storyboard to a silent, code-drawn H.264 explainer."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

W, H = 1080, 1920
PAPER, INK, TEAL = '#F4EEDC', '#293F3D', '#357D78'
CORAL, GOLD, LIGHT, MUTE = '#C86C52', '#C5A05A', '#E5DCC4', '#74807A'


def load_story(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('story must be an object with version: 1')
    def text(value, label):
        if not isinstance(value, str) or not value.strip() or '\n' in value:
            raise ValueError(f'{label} must be nonempty single-line text')
    text(data.get('title'), 'title')
    scenes = data.get('scenes')
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 120:
        raise ValueError('provide 1–120 scenes')
    for i, s in enumerate(scenes):
        if not isinstance(s, dict):
            raise ValueError(f'scene {i + 1} must be an object')
        text(s.get('title'), 'scene.title')
        duration = s.get('duration')
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 1 <= duration <= 120:
            raise ValueError('scene.duration must be finite, 1–120 seconds')
        if s.get('layout') not in ('tree', 'process', 'cycle'):
            raise ValueError('layout must be tree, process, or cycle')
        labels = s.get('labels')
        limit = 6 if s['layout'] == 'tree' else 4
        if not isinstance(labels, list) or not 2 <= len(labels) <= limit:
            raise ValueError(f'{s["layout"]} requires 2–{limit} labels')
        for label in labels:
            text(label, 'label')
        captions = s.get('captions')
        if not isinstance(captions, list) or not captions:
            raise ValueError('each scene needs captions')
        for caption in captions:
            text(caption, 'caption')
        if duration / len(captions) < 0.5:
            raise ValueError('too many captions for scene duration')
    return data


def timeline(story, fps):
    """Quantize scenes and weighted captions to one shared frame clock."""
    scenes, captions, cursor = [], [], 0
    for i, source in enumerate(story['scenes']):
        scene = dict(source, index=i, start_frame=cursor)
        count = round(source['duration'] * fps)
        scene['end_frame'] = cursor + count
        weights = [len(c) + 8 for c in source['captions']]
        used, start = 0, cursor
        for j, (caption, weight) in enumerate(zip(source['captions'], weights)):
            used += weight
            end = cursor + (count if j == len(weights) - 1 else round(count * used / sum(weights)))
            if end <= start:
                raise ValueError('caption interval shorter than one frame')
            captions.append(dict(scene=i, start_frame=start, end_frame=end, text=caption))
            start = end
        cursor += count
        scenes.append(scene)
    return dict(fps=fps, frames=cursor, duration=cursor / fps, scenes=scenes, captions=captions)


def timestamp(frame, fps):
    ms = round(frame * 1000 / fps)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}'


def find_font(explicit):
    if explicit:
        if not Path(explicit).is_file():
            raise ValueError('font does not exist')
        return explicit
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/System/Library/Fonts/Supplemental/Arial.ttf',
    ]
    result = next((p for p in candidates if Path(p).is_file()), None)
    if not result:
        raise ValueError('supply --font with a local TTF/OTF/TTC file')
    return result


def check_glyphs(story, path, index):
    with TTFont(path, fontNumber=index) as font:
        cmap = font.getBestCmap() or {}
    strings = [story['title'], '0123456789 / . SILENT CODE-DRAWN']
    for s in story['scenes']:
        strings.extend([s['title'], *s['labels'], *s['captions']])
    missing = sorted({c for c in ''.join(strings) if not c.isspace() and ord(c) not in cmap})
    if missing:
        raise ValueError('font lacks glyphs: ' + ''.join(missing[:40]) + '; select a font covering your language')


def clamp(x):
    return max(0., min(1., x))


def ease(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def line(draw, points, fill=INK, width=5, reveal=1):
    """Arc-length reveal adapted from the original paper drawing primitives."""
    if reveal <= 0:
        return
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    remaining, out = sum(lengths) * clamp(reveal), [points[0]]
    for a, b, length in zip(points, points[1:], lengths):
        if remaining >= length:
            out.append(b)
            remaining -= length
        else:
            q = remaining / max(length, .0001)
            out.append((a[0] + (b[0] - a[0]) * q, a[1] + (b[1] - a[1]) * q))
            break
    draw.line(out, fill=fill, width=width, joint='curve')


class Painter:
    def __init__(self, story, clock, font_path, font_index):
        self.story, self.clock = story, clock
        self.font_path, self.font_index = font_path, font_index
        self.paper = Image.new('RGB', (W, H), PAPER)
        d, rng = ImageDraw.Draw(self.paper), random.Random(44)
        # Fixed texture across all frames: no flickering random grain.
        for _ in range(14000):
            x, y = rng.randrange(W), rng.randrange(H)
            d.point((x, y), fill=rng.choice(['#ECE5D3', '#F8F2E3']))
        for x in range(95, 1020, 48):
            for y in range(160, 1800, 48):
                d.ellipse((x, y, x+2, y+2), fill=LIGHT)
        line(d, [(62, 90), (62, 1810)], '#DDCDB1', 2)
        for y in (240, 700, 1160, 1620):
            d.ellipse((18, y, 42, y+24), fill=LIGHT)
        # Fail early on overflow, including every caption rather than sampled ones.
        self.fit(story['title'], 32, 860, 1)
        for s in clock['scenes']:
            self.fit(s['title'], 84, 865, 2)
            for label in s['labels']:
                self.fit(label, 38, 300, 2)
            for cap in s['captions']:
                self.fit(cap, 43, 798, 3)

    @lru_cache(64)
    def font(self, size):
        return ImageFont.truetype(self.font_path, size=size, index=self.font_index)

    def wrap(self, text, size, width):
        rows, row = [], ''
        # Keep words together where possible; allow CJK and long-word wrapping.
        for token in re.findall(r'[A-Za-z0-9]+|\s+|.', text):
            if self.font(size).getlength(row + token) <= width:
                row += token
                continue
            if row.strip():
                rows.append(row.rstrip())
                row = ''
            for char in token.lstrip():
                if row and self.font(size).getlength(row + char) > width:
                    rows.append(row)
                    row = ''
                row += char
        if row.strip():
            rows.append(row.rstrip())
        return rows

    @lru_cache(512)
    def fit(self, text, preferred, width, max_rows):
        for size in range(preferred, min(28, preferred)-1, -1):
            rows = self.wrap(text, size, width)
            if len(rows) <= max_rows:
                return rows, size
        raise ValueError(f'text overflows safe area; shorten: {text[:60]}')

    def text(self, d, value, x, y, size=40, width=800, rows=1, color=INK, center=False):
        wrapped, size = self.fit(value, size, width, rows)
        for j, row in enumerate(wrapped):
            px = x - self.font(size).getlength(row) / 2 if center else x
            d.text((px, y + j * (size + 16)), row, font=self.font(size), fill=color, anchor='lt')

    def node(self, d, label, x, y, active):
        box = (x-162, y-65, x+162, y+65)
        d.rounded_rectangle((box[0]+6, box[1]+9, box[2]+6, box[3]+9), 24, fill='#DFD5BE')
        d.rounded_rectangle(box, 24, fill='#DCE7DA' if active else '#FBF7EB', outline=TEAL if active else LIGHT, width=4)
        wrapped, size = self.fit(label, 38, 300, 2)
        self.text(d, label, x, y-len(wrapped)*(size+16)/2+8, size, 300, 2, TEAL if active else INK, True)

    def frame(self, n):
        clock = self.clock
        s = next(s for s in clock['scenes'] if s['start_frame'] <= n < s['end_frame'])
        cap = next(c for c in clock['captions'] if c['start_frame'] <= n < c['end_frame'])
        u = (n - s['start_frame']) / (s['end_frame'] - s['start_frame'])
        im = self.paper.copy()
        d = ImageDraw.Draw(im)
        self.text(d, self.story['title'], 100, 110, 32, 860, color=TEAL)
        line(d, [(100, 180), (980, 180)], LIGHT, 2)
        self.text(d, f'{s["index"]+1:02} / {len(clock["scenes"]):02}', 100, 240, 30, color=CORAL)
        self.text(d, s['title'], 98, 330, 84, 865, 2)
        labels, layout = s['labels'], s['layout']
        count = len(labels)
        if layout == 'process':
            points = [(540, 755 + i * 173) for i in range(count)]
            for a, b in zip(points, points[1:]):
                line(d, [a, b], TEAL, 6, ease(u * 2))
                line(d, [(b[0]-12, b[1]-85), (b[0], b[1]-70), (b[0]+12, b[1]-85)], TEAL, 5, ease(u*2))
        elif layout == 'cycle':
            points = [(540 + 275 * math.cos(-math.pi/2 + i*2*math.pi/count), 1020 + 255 * math.sin(-math.pi/2 + i*2*math.pi/count)) for i in range(count)]
            for i, a in enumerate(points):
                b = points[(i+1) % count]
                mid = ((a[0]+b[0])/2, (a[1]+b[1])/2)
                line(d, [a, mid, b], TEAL, 5, ease(u*2))
                angle = math.atan2(b[1]-a[1], b[0]-a[0])
                head = [(mid[0]-18*math.cos(angle-.5), mid[1]-18*math.sin(angle-.5)), mid, (mid[0]-18*math.cos(angle+.5), mid[1]-18*math.sin(angle+.5))]
                line(d, head, TEAL, 5, ease(u*2))
        else:
            points = []
            line(d, [(540, 1335), (531, 1130), (548, 910), (540, 730)], INK, 11, ease(u*1.7))
            for i in range(count):
                x, y = 300 if i%2 == 0 else 780, 790 + (i//2)*200
                points.append((x, y))
                line(d, [(540, y+95), (540+(x-540)*.4, y+35), (x, y)], TEAL, 6, ease(u*2-i*.10))
        for i, ((x, y), label) in enumerate(zip(points, labels)):
            if u >= i*.10:
                self.node(d, label, x, y, i == min(count-1, int(u*count)))
        d.rounded_rectangle((88, 1460, 992, 1665), 24, fill='#EAE4D2')
        line(d, [(116, 1490), (116, 1635)], TEAL, 4)
        self.text(d, cap['text'], 146, 1496, 43, 798, 3)
        self.text(d, 'SILENT / CODE-DRAWN', 100, 1707, 27, color=MUTE)
        line(d, [(100, 1770), (980, 1770)], LIGHT, 5)
        line(d, [(100, 1770), (980, 1770)], TEAL, 6, (n+1)/clock['frames'])
        self.text(d, f'{n/clock["fps"]:.1f} / {clock["duration"]:.1f}', 100, 1810, 25, color=MUTE)
        return im


def write_editorial(out, story, clock):
    (out/'timeline.json').write_text(json.dumps(clock, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    srt = []
    for i, c in enumerate(clock['captions'], 1):
        srt.extend([str(i), f'{timestamp(c["start_frame"], clock["fps"])} --> {timestamp(c["end_frame"], clock["fps"])}', c['text'], ''])
    (out/'captions.srt').write_text('\n'.join(srt)+'\n', encoding='utf-8')
    script = [story['title'], 'Silent render. Narration text only; no voice generated.', '']
    for s in clock['scenes']:
        script.extend([s['title'], *s['captions'], ''])
    (out/'narration.txt').write_text('\n'.join(script), encoding='utf-8')


def render_video(painter, out, width, height):
    target, temp = out/'video.mp4', out/'video.partial.mp4'
    cmd = ['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}', '-r', str(painter.clock['fps']), '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(temp)]
    started = time.monotonic()
    process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for n in range(painter.clock['frames']):
            im = painter.frame(n)
            if im.size != (width, height):
                im = im.resize((width, height), Image.Resampling.LANCZOS)
            process.stdin.write(im.tobytes())
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError('FFmpeg encoder failed')
        temp.replace(target)
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait()
        temp.unlink(missing_ok=True)
        raise
    return dict(render_seconds=round(time.monotonic()-started, 3), bytes=target.stat().st_size, sha256=hashlib.sha256(target.read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('story', type=Path)
    parser.add_argument('--out', type=Path, required=True, help='new output directory; existing paths are refused')
    parser.add_argument('--font', default=os.environ.get('SKETCH_FONT'))
    parser.add_argument('--font-index', type=int, default=0)
    parser.add_argument('--size', choices=('360x640', '720x1280', '1080x1920'), default='1080x1920')
    parser.add_argument('--fps', type=int, choices=(12, 24, 30), default=24)
    parser.add_argument('--preview-only', action='store_true')
    args = parser.parse_args()
    story = load_story(args.story)
    clock = timeline(story, args.fps)
    font = find_font(args.font)
    check_glyphs(story, font, args.font_index)
    painter = Painter(story, clock, font, args.font_index)
    if not args.preview_only and not shutil.which('ffmpeg'):
        raise ValueError('ffmpeg is required for video rendering')
    args.out.mkdir(parents=True, exist_ok=False)
    write_editorial(args.out, story, clock)
    shots = []
    for i, s in enumerate(clock['scenes']):
        for name, q in [('start', 0), ('middle', .62), ('end', .99)]:
            n = min(s['end_frame']-1, s['start_frame']+int((s['end_frame']-s['start_frame'])*q))
            im = painter.frame(n).resize((360, 640), Image.Resampling.LANCZOS)
            im.save(args.out/f'scene-{i+1:02}-{name}.jpg', quality=90)
            if name == 'middle':
                shots.append(im)
    # Bound the sheet height for longer stories; preserve individual QA frames.
    for page in range(0, len(shots), 12):
        chunk = shots[page:page+12]
        sheet = Image.new('RGB', (360*min(3, len(chunk)), 640*math.ceil(len(chunk)/3)), PAPER)
        for j, im in enumerate(chunk):
            sheet.paste(im, ((j%3)*360, (j//3)*640))
        sheet.save(args.out/f'contact-{page//12+1:02}.jpg', quality=90)
    report = dict(frames=clock['frames'], duration=clock['duration'], fps=args.fps, size=args.size, scenes=len(clock['scenes']), captions=len(clock['captions']), silent=True, preview_only=args.preview_only)
    if not args.preview_only:
        width, height = map(int, args.size.split('x'))
        report.update(render_video(painter, args.out, width, height))
    (args.out/'render-report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        sys.exit(1)
