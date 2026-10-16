# Validation and reproduction

Tested on 2026-10-16. These are smoke-test results for this generic package, not benchmarks or a rerender of the earlier five-minute production.

## Recorded environment

- macOS, ARM64; Python 3.14.7.
- Pillow 12.3.0, fontTools 4.67.0; PyYAML 6.0.3 for package checks.
- FFmpeg/ffprobe 9.0.2, with libx264.
- English: locally installed Arial. Chinese: locally installed STHeiti Light, TTC face 0. Fonts are not bundled. Linux CI uses DejaVu Sans and Noto Sans CJK instead.

Runtime dependency ranges are in `requirements.txt`. To reproduce the tested Python versions, use a fresh environment with `python -m pip install Pillow==12.3.0 fonttools==4.67.0 PyYAML==6.0.3`. Exact pixels and MP4 hashes can change with fonts, font rasterizers, library/encoder versions and platforms; frame count, caption continuity and decode checks should still agree.

## Measured outputs

| Input | Output | Frames | Captions | Bytes | Full decode |
| --- | --- | --- | --- | --- | --- |
| `examples/idea-to-video.json` | 12 s, 360×640, 24 fps | 288 | 3 | 75,117 | Passed |
| `examples/water-cycle.zh.json` | 12 s, 360×640, 24 fps | 288 | 2 | 54,421 | Passed |
| `examples/smoke-hd.json` | 2 s, 1080×1920, 24 fps | 48 | 1 | 91,046 | Passed |

All outputs are H.264/yuv420p, with one video stream and no audio stream. The decoder processed every expected frame without reported errors. Caption intervals cover the full timeline without gaps or overlaps; SRT timing and wording match the burn-in clock.

See [machine-readable reports and SHA-256 hashes](validation-results.json), the [English MP4](demo.mp4), [Chinese MP4](water-cycle.mp4), [English contact sheet](preview.jpg) and [Chinese contact sheet](water-preview.jpg). Recorded render times are local observations, not performance promises.

Visual inspection covered start, midpoint and end images for all five demo scenes. Titles, labels, captions and arrows fit the safe areas; Chinese wording was shortened after spotting an awkward line break. Line reveals and active-node changes were visible across sampled frames. This is sampled visual review, not a claim of exhaustive frame-by-frame inspection or tested narration quality.

## Reproduce

From the repository root, after dependency setup:

```bash
python scripts/check_package.py
TEST_FONT=/path/to/latin-font.ttf python -m unittest discover -s tests -v
python scripts/render.py examples/idea-to-video.json --out build/en-check \
  --size 360x640 --font /path/to/latin-font.ttf
python scripts/verify.py build/en-check
python scripts/render.py examples/water-cycle.zh.json --out build/zh-check \
  --size 360x640 --font /path/to/chinese-font.ttc
python scripts/verify.py build/zh-check
python scripts/render.py examples/smoke-hd.json --out build/hd-check \
  --font /path/to/latin-font.ttf
python scripts/verify.py build/hd-check
```

Use new output directories for reruns. On PowerShell, set `$env:TEST_FONT` separately before the unittest command. The three regression tests check frame quantization and continuous caption intervals, invalid input rejection, missing glyph/overflow failures and rendering checkpoints across all layouts. Set `TEST_FONT` to exercise font-dependent assertions; otherwise that test is skipped.

The package checker validates Skill frontmatter, UI metadata, example structures and repository-local Markdown targets. The official skill-creator `quick_validate.py` also passed during packaging; that external helper is not required at runtime. GitHub Actions runs package checks, regression tests, and English/Chinese/HD render-and-decode smoke tests on Linux: [workflow](../.github/workflows/ci.yml), [current CI status](https://github.com/Karl-Dai/sketch-video-skill/actions).

## Practical limits

The drawing baseline has three layouts, vertical composition and hard cuts. The later [executable production extension](production.md) adds WAV import, local adapter interfaces, audio-based scene timing, optional reviewed caption boundaries, AAC mixing, AV checks and a local publication handoff. It does not bundle TTS/ASR models, forced alignment, music, research automation, browser control or a social publishing API. Without reviewed caption boundaries, timing remains heuristic. The historical 300-second production is provenance, not this extraction's validation evidence.

The extension has nine Python regression tests in total and four Node CLI tests. Synthetic-tone fixtures exercise scene and whole WAV timing, imported ASR differences, explicit fake adapter execution, silent/clipped input rejection, subtitle boundaries, a 59-frame H.264/AAC render, complete AV decode and authorization/hash-bound handoff receipts. The actual npm tarball is also extracted and tested through the production commands. These are technical fixture results, not validation of Qwen/Whisper speech quality or the upstream full film. Windows and actual model inference on macOS remain unvalidated. See [voice status and resource boundaries](../references/voice.md).
