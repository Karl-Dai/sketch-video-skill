# Optional narration — experimental

The core renderer is silent and has no TTS integration. Narration is a separate, optional local stage. No model weights, voice assets or automatic model installer are included.

Short Mandarin auditions using a Kokoro Chinese ONNX setup have passed audio technical checks in an upstream experiment, but no final voice has been accepted. Voice quality and whole-sentence synthesis remain under evaluation. This repository has not reproduced that setup, and full-video narration is incomplete. Technical audio checks do not establish naturalness, listener approval or production readiness. This is not a verified end-to-end voiced-video feature.

If narration is requested:

1. Choose a local engine and voice only after verifying the exact implementation, model/voice licenses and download size. Obtain authorization before large downloads. Do not assume that a model family's license covers a specific third-party voice pack.
2. Generate a short audition from representative Chinese terms, numbers and punctuation. Listen for pronunciation, rhythm and voice suitability; run audio decode, loudness and clipping checks.
3. Produce scene-level narration from the checked script. Measure each file's real duration. Expand scene times or edit the script to fit; the bundled caption timing is a heuristic and does not align speech.
4. Create an audio-aligned caption schedule and use it consistently for burn-in and SRT. This requires extending the current scheduler or a separate editing step. Never reuse silent captions and imply that alignment was verified.
5. Mix only licensed audio. Mux the finished track with the final video, verify both streams completely, check AV sync at scene boundaries and listen through the entire result. Document that this voiced output uses a different verification procedure: `verify.py` deliberately expects silence.

Do not simply use FFmpeg `-shortest` to hide mismatched durations: it can discard the end of the video or narration. Keep a silent deliverable available until a complete voiced version has passed review.
