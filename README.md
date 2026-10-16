# Sketch Video Skill

**Turn ideas into hand-drawn explainer videos with code.**

A question becomes a story. The story becomes a diagram. The diagram comes to life—with captions you can inspect and a video you can reproduce.

[简体中文](README.zh-CN.md) · [Agent instructions](SKILL.md) · [12-second demo](docs/demo.mp4) · [Validation](docs/validation.md)

![Three code-drawn scenes: story tree, animation pipeline, review loop](docs/preview.jpg)

## Paper, ink, and a real pipeline

A reusable Agent Skill and a small local renderer for educational sketch videos. It carries forward drawing and quality-control methods from an earlier 38-second prototype and five-minute Chinese explainer, then opens them up to new topics through editable JSON.

- **Draw with code:** warm paper, ink strokes, progressive lines and animated tree, process and cycle diagrams.
- **Keep words in sync:** burn-in captions, SRT and narration text come from one frame clock.
- **See what you made:** start/middle/end frames, contact sheets and full-video decode checks.
- **Run locally:** Python + Pillow + fontTools + FFmpeg. Rendering the examples needs no API key or model download.
- **Explain in your language:** English and Simplified Chinese examples, explicit fonts and missing-glyph checks.

Default output is a **silent**, vertical 1080×1920 H.264 video at 24 fps. Research, storytelling and visual review are Agent/human work; the renderer does not automatically turn a prompt into a verified lesson. Custom subject-specific illustrations require drawing-code changes.

## Run with npx — no npm login

Node 22+ and Git are needed for this direct GitHub command. This immutable commit contains the CLI; no npm registry publication is involved:

```bash
npx --yes --ignore-scripts --package="git+https://github.com/Karl-Dai/sketch-video-skill.git#3e7e94259864588ff5ac815d1cc608bb42ac532f" sketch-video --help
```

Replace `--help` with `init my-video --example water` to create a Chinese storyboard, or `install-skill /path/to/new-skill-directory` to install the Agent Skill. Running the CLI and installing a Skill are separate actions. Neither installs Python, FFmpeg or models. [Command reference and tested scope](docs/npm.md).

For repeat use, install the same explicit GitHub package into your project:

```bash
npm install --ignore-scripts "git+https://github.com/Karl-Dai/sketch-video-skill.git#3e7e94259864588ff5ac815d1cc608bb42ac532f"
npm exec -- sketch-video init my-video --example water
```

After setting up a Python environment, run `npm exec -- sketch-video doctor --python /path/to/python`, then `npm exec -- sketch-video render --python /path/to/python my-video/story.json --out new-output --font /path/to/font.ttc`, followed by `npm exec -- sketch-video verify --python /path/to/python new-output`. The wrapper calls the existing Python renderer. For registry-free distribution, the manifest sets `private: true`; the GitHub repository remains public.

## Run Python directly

Requirements: Python 3.10+, FFmpeg/ffprobe with the `libx264` encoder, and a local TTF/OTF/TTC font. Install FFmpeg with your system package manager first. Linux users can use DejaVu Sans for English and Noto Sans CJK for Chinese. Fonts and executables are not bundled.

```bash
git clone https://github.com/Karl-Dai/sketch-video-skill.git
cd sketch-video-skill
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/render.py examples/idea-to-video.json --out build/demo --size 360x640
python scripts/verify.py build/demo
```

Windows: activate with `.venv\Scripts\Activate.ps1` and pass `--font "C:\path\to\font.ttf"`. Elsewhere, use `--font /path/to/font.ttf` or set `SKETCH_FONT` if discovery fails. Use a **new output directory** each time; existing paths are refused.

Outputs include `video.mp4`, `captions.srt`, `narration.txt`, `timeline.json`, QA JPGs and render/verification reports. [Watch the Chinese example](docs/water-cycle.mp4) and inspect its [evidence ledger](examples/sources.md).

```bash
# Preview without encoding video
python scripts/render.py examples/water-cycle.zh.json --out build/water-preview \
  --font /path/to/NotoSansCJK-Regular.ttc --preview-only

# Native-resolution output: omit --size, then verify the entire file
python scripts/render.py examples/idea-to-video.json --out build/full-hd
python scripts/verify.py build/full-hd
```

Review the QA images and play the full result. A successful decode does not establish factual accuracy or readable pacing.

## Install as an Agent Skill

For Codex, copy this directory into your configured skills directory, commonly `~/.codex/skills/sketch-video-skill`. Keep `SKILL.md`, `scripts/`, `references/` and `examples/` together. Inspect an existing destination before replacing anything. Install Python dependencies in a virtual environment and make FFmpeg available. Reload skill discovery if needed. Compatible Agents can load the same `SKILL.md`; the scripts also run independently.

Try:

> Use $sketch-video-skill to explain how a battery stores energy to curious teenagers. Make a 45-second silent Chinese vertical video. Verify the scientific claims, use original code-drawn diagrams, include subtitles and show me the QA frames.

The Skill covers brief → research → script → storyboard → animation → captions → render → inspection → full decode. [SKILL.md](SKILL.md) contains the working instructions.

## Make it yours

1. Start with [a brief](examples/brief.md) and a claim-to-source ledger.
2. Edit titles, scene durations, labels and captions in [an example JSON](examples/idea-to-video.json).
3. Choose `tree`, `process` or `cycle`; extend the drawing code for richer visuals.
4. Preview, inspect, render and verify. Keep script, caption and timing edits together.

Read the [storyboard contract](references/storyboard.md), [production notes](references/workflow.md) and [measured validation results](docs/validation.md). Caption timing is a text-length heuristic, not speech alignment. The baseline is single-process; no real-time or long-video speedup is promised.

## Voice is optional—and experimental

The core works without audio. Upstream Kokoro Chinese ONNX auditions have passed short audio technical checks, but no final voice has been accepted and full-film narration is incomplete. Naturalness and production readiness are unvalidated. This repository has no TTS adapter or model installer. See the [optional narration procedure](references/voice.md) before extending it.

## License and scope

[MIT](LICENSE) covers our original code, documentation and code-drawn demo visuals. Dependencies, models, voices, fonts and external assets retain their own terms; see [NOTICE.md](NOTICE.md). No model weights or font files are included. Creating a video does not authorize posting it externally; the package has no publishing integration.
