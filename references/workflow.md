# From evidence to animation

## Plan the story, then the timeline

Keep a brief, claim ledger, script, storyboard and list of teaching boundaries. A scene should have a reason to appear: introduce a question, show a mechanism, contrast outcomes or consolidate an idea. Do not hard-code an 18-scene structure, five-minute duration or AI-history chronology into a new topic.

Estimate pacing from a short read-through, not a universal characters-per-second number. Leave time to see a newly revealed connection. If the script does not fit, shorten the message or extend duration. Shared captions and narration text prevent silent edits from drifting apart.

Storyboard before choosing a drawing form. Implemented JSON layouts are `tree` for branches, `process` for steps, `cycle` for recurrence, `timeline` for historical/project milestones, and `comparison` for two alternatives on the same dimensions. They do not infer causality or simulate physical systems. Mix forms as needed, as in [the mixed-visual example](../examples/mixed-visuals.json). Scene illustration and local zoom are custom extensions, not shipped layout names: extend `Painter.frame`, validation, glyph/overflow checks and representative frame tests together. Keep editorial content separate from geometry.

## Preserve the useful drawing mechanics

The original workflow used a fixed seeded paper texture, teal/coral ink, progressive arc-length line reveals and smoothstep easing. Random texture is fixed across frames to avoid temporal flicker. The renderer carries these methods forward with a portable font argument instead of an environment-specific font directory.

One integer frame clock is authoritative. Quantize scenes first, then assign contiguous caption intervals inside each scene. The total duration is the sum of quantized scene durations, which can differ slightly from the requested fractional durations. Sample video frames at `frame / fps`, not wall-clock render time.

FFmpeg receives RGB frames over stdin and encodes H.264/yuv420p. No frame PNG sequence is required. A temporary MP4 is renamed only after successful encoding. The output folder must be new so an earlier result is never overwritten accidentally.

## Review beyond a contact sheet

Review every caption for facts and reading time. Inspect start/middle/end of each scene; contact sheets show only midpoints. Sample extra frames around line reveals and hard cuts, then play the full video. Look for missing glyphs, cramped text, hidden arrows, misleading scale, empty late frames and diagrams that appear too briefly. Sampled images cannot prove a whole video is visually flawless.

Run full decode validation after final encoding. A successful encode or thumbnail is insufficient: the complete file must decode, the number of decoded frames must match, and captions must cover the video. Record both mechanical checks and human visual observations without presenting one as the other.

## Longer videos and optional parallel rendering

The supplied general renderer is single-process and streams frames, favoring a small setup and bounded memory. The earlier topic-specific production split a 300-second timeline into six 50-second jobs, used a bounded worker pool, and concatenated matching encoded segments. That optimization has not been ported or benchmarked here.

If profiling justifies segments, keep resolution, fps, codec, pixel format and timebase identical. Split on frame boundaries, bound worker memory, concatenate and validate the complete result. Do not claim linear speedups. Test a short representative segment before committing to a long native-resolution render.
