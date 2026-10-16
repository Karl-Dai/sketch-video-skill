# Sketch Video Skill

**Turn ideas into hand-drawn explainer videos with code.**

A question becomes a story. The story becomes a diagram. The diagram comes to life—with captions you can inspect and a video you can reproduce.

[简体中文](README.md) · [Agent instructions](SKILL.md) · [12-second demo](docs/demo.mp4) · [Validation](docs/validation.md)

![Mixed visuals: branches, timeline, comparison, steps and a cycle](docs/mixed-preview.jpg)

## Paper, ink, and a real pipeline

A reusable Agent Skill and a small local renderer for educational sketch videos. It carries forward drawing and quality-control methods from an earlier 38-second prototype and five-minute Chinese explainer, then opens them up to new topics through editable JSON.

- **Draw with code:** warm paper, ink strokes, progressive lines and animated tree, process, cycle, timeline and comparison diagrams.
- **Keep words in sync:** burn-in captions, SRT and narration text come from one frame clock.
- **See what you made:** start/middle/end frames, contact sheets and full-video decode checks.
- **Run locally:** Python + Pillow + fontTools + FFmpeg. Rendering the examples needs no API key or model download.
- **Explain in your language:** English and Simplified Chinese examples, explicit fonts and missing-glyph checks.

Default output is a **silent**, vertical 1080×1920 H.264 video at 24 fps. Research, storytelling and visual review are Agent/human work; the renderer does not automatically turn a prompt into a verified lesson. Custom subject-specific illustrations require drawing-code changes.

## Run with npx — no npm login

Node 22+ and Git are needed for this direct GitHub command. This immutable commit contains the CLI; no npm registry publication is involved:

```bash
npx --yes --ignore-scripts --package="git+https://github.com/Karl-Dai/sketch-video-skill.git#e54741d821474e417bb1f25daf13d93e393bc259" sketch-video --help
```

Replace `--help` with `init my-video --example water` to create a Chinese storyboard, or `install-skill /path/to/new-skill-directory` to install the Agent Skill. Running the CLI and installing a Skill are separate actions. Neither installs Python, FFmpeg or models. [Command reference and tested scope](docs/npm.md).

For repeat use, install the same explicit GitHub package into your project:

```bash
npm install --ignore-scripts "git+https://github.com/Karl-Dai/sketch-video-skill.git#e54741d821474e417bb1f25daf13d93e393bc259"
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
3. Storyboard first: choose `tree`, `process`, `cycle`, `timeline` or `comparison` according to meaning. Mix forms; scene illustrations and local zooms need custom drawing code.
4. Preview, inspect, render and verify. Keep script, caption and timing edits together.

Read the [storyboard contract](references/storyboard.md), [production notes](references/workflow.md) and [measured validation results](docs/validation.md). Caption timing is a text-length heuristic, not speech alignment. The baseline is single-process; no real-time or long-video speedup is promised.

## Complete audio/video production and publication handoff

The silent workflow remains intact. The executable extension supports audition/selection records, pre-generated scene or whole-file WAVs, explicit local TTS/ASR adapters, measured audio timing, reviewed subtitle boundaries, AAC mixing, full AV checks and local publication bundles/receipts. [Follow the complete walkthrough](docs/production.md) and [audio contracts/licensing](references/voice.md).

From your checked idea/script, create `story.json` and reviewed `audio.json`. Then run:

```bash
python scripts/production.py audition voices.json --out build/auditions
# Listen and select a voice; import WAVs or explicitly execute a trusted local TTS adapter.
python scripts/production.py prepare-audio story.json --audio audio.json --out build/prepared
python scripts/production.py asr-check build/prepared --transcript transcript.json --out build/asr-review.json
python scripts/render.py build/prepared/retimed.json --out build/animation --font /path/to/font.ttf
python scripts/production.py mux build/animation build/prepared --out build/final
python scripts/production.py verify-av build/final
python scripts/production.py package build/final --metadata publication.json --out build/handoff
```

ASR is optional; use an existing transcript or an installed adapter, never an automatic model download. Without reviewed caption boundaries, timing is a labelled heuristic, not forced alignment. A **no-model test-tone version** of the entire example is provided in the walkthrough; it validates media plumbing, not speech quality.

The upstream Qwen3-TTS Serena production completed at 358.875 seconds, 18 scenes and 54 captions with local Whisper checks and full AV decoding. No sentence-by-sentence human listening or fresh local model inference is claimed. The 0.6B CustomVoice path does not support extra style instructions. Model sizes, licenses and unknown costs are explicit in the audio reference. [Optional offline tools](docs/optional-voice.md) now include local Qwen/Whisper adapters, pinned weight verification, pause/semantic timing estimates and quiet splicing, also available through npx. Acquire models separately; nothing downloads automatically.

`package` sends nothing. After reviewing facts, rights, privacy, account and AV quality, a separately authorized browser/manual action may upload. Record observed success, draft, failure or uncertainty with `record-publication`. No generic Xiaohongshu publishing API is claimed.

[Watch the 15-second mixed-layout demo](docs/mixed-demo.mp4), or use `init my-video --example mixed`. Its project timeline is explicitly hypothetical, not a historical claim.

## License and scope

[MIT](LICENSE) covers our original code, documentation and code-drawn demo visuals. Dependencies, models, voices, fonts and external assets retain their own terms; see [NOTICE.md](NOTICE.md). No model weights or font files are included. Creating a video does not authorize posting it externally; the package has no publishing integration.
