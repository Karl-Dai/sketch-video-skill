---
name: sketch-video-skill
description: Produce hand-drawn explainers from an idea through research, script, storyboard, animation, optional narration/ASR, audio-based captions, AV checks and a publication handoff. Use for code-drawn educational videos; actual external posting needs separate authorization.
---

# Sketch Video

Turn an idea into an inspectable explainer: evidence, script, storyboard, code-drawn animation, optional reviewed narration, subtitles, validated final media and a publication handoff. Use the user's language and duration. Preserve the silent path when audio is not requested. The renderer is a starting point for topic-specific diagrams; local TTS/ASR uses explicit adapters, not an automatic service.

## Shape the explanation

Infer the audience, takeaway, language, duration and format from the request. Clarify only missing choices that change the result. For a broad topic, pick one explainable question and state the scope. Start with a concise brief like [examples/brief.md](examples/brief.md).

Research material claims before presenting them as facts. Prefer primary sources; record URLs, dates, supported claims and caveats in an evidence ledger like [examples/sources.md](examples/sources.md). Distinguish facts, analogy and simplification. Recheck time-sensitive claims. Mark uncertainty instead of inventing precision. The renderer does not fact-check.

Write a narrative with a question, mechanism or causal chain, and a takeaway. Allocate scene durations according to reading or speaking time. One visual idea per scene is a useful default, not a fixed scene count. A long topic needs more time or a narrower scope.

Storyboard first, then choose the visual grammar: `tree` for real branches, `process` for ordered steps, `cycle` for recurrence, `timeline` for dated developments, `comparison` for two alternatives on shared dimensions. Mix forms when the explanation needs them; a hand-drawn style does not mean a tree on every page. Scene illustrations and local zooms require custom drawing-code extensions and tests; they are not built-in layouts. See [the mixed example](examples/mixed-visuals.json).

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

## Narration, optional ASR and the real audio clock

For voiced work, read [references/voice.md](references/voice.md) and the [complete walkthrough](docs/production.md). The model-free WAV path is fully executable; optional model adapters require already-installed software/weights and explicit `--execute`. Do not download models or install system software automatically. Record exact model/voice license, revision, bytes, device/dtype and resource cost; unknown is not zero. An accepted audition is specific to that production, not a universal voice-quality guarantee.

1. Generate/import comparable short auditions. `audition voices.json --out new-listen` makes WAVs and technical metrics; listen before `select-voice ... --voice ID --note ... --out selection.json`.
2. Import reviewed scene WAVs, or explicitly execute a trusted local `tts request.json --adapter adapter.json --out new-speech --execute`. Whole-script synthesis is also supported but needs reviewed scene cuts afterwards. No style control is promised for Qwen 0.6B CustomVoice Serena. Unknown platforms require a short device-specific trial; do not transfer Linux dtype/wheel/performance assumptions to macOS.
3. Run `prepare-audio story.json --audio audio.json --out new-prepared --fps 24`. It measures audio and pads only frame-rounding tails. Reviewed caption times become the shared integer frame clock; without them timing remains a labelled heuristic. Never imply forced alignment.
4. Optionally invoke `asr ... --adapter ... --execute` or import an existing transcript, then run `asr-check prepared --transcript transcript.json --out review.json`. Listen to discrepancies and fix source audio/text; recognition is not ground truth and does not automatically approve narration.
5. Render `prepared/retimed.json` at the same fps, then `mux new-render prepared --out new-final` and `verify-av new-final`. An old silent timeline cannot simply be reused with new narration. Do not use `-shortest` to hide mismatched durations.

These names are npx CLI commands. Direct Python uses `python scripts/production.py <command>`; rendering remains `python scripts/render.py`. See the walkthrough for exact arguments. `fixture --out new-inputs` supplies clearly labelled test tones and a test transcript with zero model downloads; fixture success is not speech-quality or real-ASR evidence.

## Final verification and delivery

Render after fixing preview problems. Run `scripts/verify.py`: it checks H.264/yuv420p, dimensions, fps, duration, frame count, continuous captions, SRT consistency, silence and a full decode. This does not establish scientific accuracy or visual quality; perform the visual review separately. Record inputs, dependency versions, commands, verification result and any limits. Rerun affected checks after edits.

For narrated output, `verify-av` checks both streams, frame count, subtitle agreement, AV timestamps/duration, full decode, silence/clipping and PCM levels. Listen through the whole final film and inspect boundaries: technical checks do not establish pronunciation, naturalness or semantic sync. Record actual checks separately from upstream unfinished experiments.

Deliver video, editable source, SRT, narration text, sources, preview and QA records. State whether the output is silent or voiced. See [docs/validation.md](docs/validation.md) for the original baseline; [docs/production.md](docs/production.md) covers the executable extension.

## Publication handoff and receipt

Run `package final --metadata publication.json --out new-handoff` to assemble final media, cover, subtitles, public copy, rights notes, AV results, hashes and a review checklist. This is local and sends nothing. Review personal data and rights before exposing the package. Keep dependencies, fonts, models, voices and assets under their own licenses; never bundle weights or unlicensed media.

A video request does not authorize posting it. Before any external action, obtain explicit current user approval for the exact platform, account and media. Use an existing authorized browser capability or manual upload; no generic platform/Xiaohongshu API is implemented here. Stop at login, CAPTCHA, denial or uncertainty. Confirm the actual draft/post URL before claiming success; inspect an uncertain result before retrying.

Save evidence using `record-publication handoff --receipt receipt.json --authorized` only when real authorization exists. This records the caller's evidence; it does not grant consent, upload or independently verify a post. Use accurate `published`, `draft`, `failed`, `unknown`, `denied` or `not_attempted` outcomes. Target/media hashes must match; do not overwrite an earlier receipt.
