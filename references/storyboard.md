# Storyboard contract (version 1)

The renderer reads local UTF-8 JSON. It does not execute content, fetch URLs or call an AI model.

```json
{
  "version": 1,
  "title": "A short series title",
  "scenes": [{
    "title": "One question per scene",
    "duration": 8,
    "layout": "process",
    "labels": ["Input", "Change", "Result"],
    "captions": ["Describe the change.", "Then explain why it matters."]
  }]
}
```

| Field | Requirement |
| --- | --- |
| `version` | `1` |
| `title` | Nonempty single-line text, automatically fitted in the series header |
| `scenes` | 1–120 scene objects |
| `duration` | Finite number, 1–120 seconds per scene; rounded to the selected frame clock |
| `layout` | `tree`, `process`, or `cycle` |
| `labels` | 2–6 for tree, 2–4 for process/cycle; short text, fitted to two lines |
| `captions` | Nonempty list of single-line strings; at least 0.5 seconds per item on average |

Unknown extra keys are ignored, so evidence and editorial notes may be kept alongside scenes. The script validates required fields; keep key spelling exact.

The logical canvas is 1080×1920. Output choices are 360×640, 720×1280 or 1080×1920, at 12, 24 or 30 fps. This baseline intentionally supports vertical composition only. Rendering still draws the native canvas before scaling; draft mode reduces file size and encoding load but is not a performance promise.

Scene titles fit up to two lines, captions three lines, and labels two lines. Font sizes reduce to a minimum of 28 logical pixels; overflow fails before output creation. Keep words short enough to remain readable on a phone, even when they technically fit. The line breaker is a practical Latin/CJK helper, not a full multilingual typesetter; inspect punctuation and line breaks. Complex scripts, right-to-left layout and emoji are not validated features.

Caption intervals use `len(text) + 8` weights within each scene. Both burn-in selection and SRT export use identical integer frame boundaries. This is a silent reading-time heuristic, not forced alignment. For narration, first build a real audio timeline and update caption scheduling (see [voice.md](voice.md)).

The full frame timeline is exported as `timeline.json`; `render-report.json` records output parameters and render time. `captions.srt` is UTF-8 text. `narration.txt` contains the same caption wording, grouped by scene. There are start/middle/end QA JPGs per scene and paginated midpoint contact sheets. Preview-only mode emits these editorial artifacts without an MP4.

`--font` accepts a local TTF/OTF/TTC. `--font-index` selects a face (default 0); it is unrelated to a language code. `SKETCH_FONT` is an alternative environment variable. Default font discovery covers common Linux and macOS locations for the English demo; pass a Chinese-capable font for Chinese. Font coverage is checked through fontTools before drawing. Fonts are not bundled.
