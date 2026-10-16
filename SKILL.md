---
name: sketch-video-skill
description: Create code-drawn hand-drawn explainer videos from an idea or script, including research, storyboard, animation, synchronized captions, rendering and visual/video QA. Use for educational sketch animations; narration is optional.
---

# Sketch Video

Turn an idea into a clear, inspectable explainer: a script with evidence, a storyboard, code-drawn animation, synchronized subtitles and a validated local video. Use the user's language and requested duration. The bundled renderer makes silent paper-style vertical videos; it is a starting point for topic-specific diagrams, not an automatic research or voice service.

## Shape the explanation

Infer the audience, takeaway, language, duration and format from the request. Clarify only missing choices that change the result. For a broad topic, pick one explainable question and state the scope. Start with a concise brief like [examples/brief.md](examples/brief.md).

Research material claims before presenting them as facts. Prefer primary sources; record URLs, dates, supported claims and caveats in an evidence ledger like [examples/sources.md](examples/sources.md). Distinguish facts, analogy and simplification. Recheck time-sensitive claims. Mark uncertainty instead of inventing precision. The renderer does not fact-check.

Write a narrative with a question, mechanism or causal chain, and a takeaway. Allocate scene durations according to reading or speaking time. One visual idea per scene is a useful default, not a fixed scene count. A long topic needs more time or a narrower scope.

## Build and preview

Read [references/storyboard.md](references/storyboard.md) for the JSON contract and layout constraints. Use [examples/idea-to-video.json](examples/idea-to-video.json) or [examples/water-cycle.zh.json](examples/water-cycle.zh.json) as a starting point. Read [references/workflow.md](references/workflow.md) when expanding animation or planning longer productions.

Run scripts relative to this skill directory; keep project inputs and generated outputs in the user's chosen project folder. Python 3.10+, Pillow, fontTools, a suitable local font, and FFmpeg with libx264 are required for video. See [README.md](README.md) for setup. Do not install models or system packages without authorization.

An optional Node CLI wraps the same scripts; see [docs/npm.md](docs/npm.md) for the tested GitHub npx entry point, `doctor`, `init`, and explicit Skill installation. Running npx does not register a Skill or install Python dependencies automatically.

```bash
python scripts/render.py /path/to/story.json --out /path/to/new-preview --font /path/to/font.ttf --preview-only
python scripts/render.py /path/to/story.json --out /path/to/new-render --font /path/to/font.ttf
python scripts/verify.py /path/to/new-render
```

The output directory must be new. Draft with `--size 360x640`; final defaults are 1080×1920 and 24 fps. The script checks font glyph coverage and text overflow before encoding. It emits the SRT, narration text and burn-in captions from one quantized frame clock. Auto timing uses text length, so inspect pacing; it does not align speech.

Inspect start, middle and end frames of every scene, plus contact sheets. Check legibility, text margins, line breaks, transitions, diagram meaning and timing. For technical motion, inspect additional frames near reveals. If a diagram needs a different visual grammar, extend the drawing code rather than forcing a misleading tree or cycle.

## Render, verify and deliver

Render after fixing preview problems. Run `scripts/verify.py`: it checks H.264/yuv420p, dimensions, fps, duration, frame count, continuous captions, SRT consistency, silence and a full decode. This does not establish scientific accuracy or visual quality; perform the visual review separately. Record inputs, dependency versions, commands, verification result and any limits. Rerun affected checks after edits.

Deliver the video, editable storyboard/code, SRT, narration text, sources, representative preview and QA results. State clearly when it is silent. See [docs/validation.md](docs/validation.md) for the tested baseline and reproduction commands.

Narration is an optional extension; read [references/voice.md](references/voice.md) only when requested. Short audio smoke checks do not validate a complete voiced video. Keep licensing of dependencies, fonts, models and assets separate from the project's original code. Do not bundle weights or unlicensed media. A request to make a video does not authorize posting it externally.
