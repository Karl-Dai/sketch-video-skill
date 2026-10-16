# Provenance and third-party boundaries

This project adapts the reusable mechanics of an earlier original hand-drawn educational video production: a 38-second prototype and a 300-second Chinese explainer with 18 scenes, native 1080×1920 drawing, 24 fps, H.264 and synchronized captions. The supplied editable source packages were obtained and reviewed during extraction. This repository reuses their arc-length line-reveal method, easing, paper palette/texture approach, shared caption clock and render/inspect/decode workflow.

The generic JSON renderer, portable font handling, glyph/overflow checks, validation scripts, new examples and documentation were developed for this package. The earlier topic-specific full film was not rerendered as part of this package's validation. Its historical production parameters are provenance, not performance claims for this version. The raw archives, original private metadata, full film and environment-specific transfer tools are not redistributed.

The MIT license applies only to this repository's original code, prose and code-drawn demo visuals. It does not relicense third-party works, websites, models, voices, fonts, executables or dependencies. Facts in the evidence ledger are paraphrased with primary-source links; source illustrations are not copied.

| External component | Use and license boundary |
| --- | --- |
| [Python](https://www.python.org/psf/license/) | Installed runtime; retain Python's license. |
| [Pillow](https://pillow.readthedocs.io/en/stable/about.html#license) | Installed image library; MIT-CMU license. |
| [fontTools](https://github.com/fonttools/fonttools/blob/main/LICENSE) | Installed font inspection library; MIT license. |
| [FFmpeg](https://ffmpeg.org/legal.html) | External binary; LGPL/GPL configuration varies. libx264-enabled builds have additional licensing considerations. Not bundled. |
| [Noto Sans CJK](https://github.com/notofonts/noto-cjk/blob/main/Sans/LICENSE) | Suggested Chinese font; SIL OFL 1.1. Not bundled. |
| Local system fonts | Used only from the user's machine; retain the applicable vendor terms. Not bundled. |
| TTS implementations, models and voices | Optional, experimental; check each exact distribution separately. None bundled. |
| [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) / [Whisper](https://github.com/openai/whisper) | Optional external engines/checkpoints under their respective terms (upstream Apache-2.0 / MIT). This project provides generic local adapter interfaces only; no upstream code or weights are vendored. Exact model/voice metadata and costs must be recorded. |

Public demo raster/video previews use locally available fonts at render time. Their inclusion does not grant a right to redistribute the underlying font software. The tested fonts and environment are recorded in [docs/validation.md](docs/validation.md).
