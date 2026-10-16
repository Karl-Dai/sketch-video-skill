# Complete local production walkthrough

Use these Python commands from the repository root, or replace `python scripts/production.py` with `sketch-video` in the Node CLI. Every production command accepts `--help`; npx supports `--python` or `SKETCH_PYTHON`. Nothing here publishes externally.

## Idea → final voiced video → publication handoff

1. Write a brief, source ledger and factual script. Create a [storyboard](../references/storyboard.md).
2. Import short WAV auditions, run `audition`, listen, then record a production-specific `select-voice` decision.
3. Supply pre-generated WAVs or explicitly execute a reviewed local TTS adapter. Whole-script synthesis needs reviewed scene cuts afterwards. Optional ASR accepts a local adapter or an existing transcript.
4. Prepare audio timing, inspect captions, render the retimed storyboard, mix and verify both streams.
5. Listen through; check facts/rights/privacy; create the publication bundle. Use a separately authorized browser/manual upload, then save an accurate receipt.

## Reproducible no-model example

This generates **sine tones, not speech**, and a hand-authored test transcript. It exercises the complete local media path without a model. Use new directories.

```bash
python scripts/production.py fixture --out build/inputs
python scripts/production.py audition build/inputs/voices.json --out build/auditions
python scripts/production.py prepare-audio build/inputs/story.json \
  --audio build/inputs/audio.json --out build/prepared --fps 24
python scripts/production.py asr-check build/prepared \
  --transcript build/inputs/transcript.json --out build/asr-review.json
python scripts/render.py build/prepared/retimed.json --out build/animation \
  --font /path/to/font.ttf --size 360x640 --fps 24
python scripts/production.py mux build/animation build/prepared --out build/final
python scripts/production.py verify-av build/final
python scripts/production.py package build/final \
  --metadata build/inputs/publication.json --out build/handoff
```

Expected: 59 video frames, 24 fps, approximately 2.458 seconds, one AAC stream and no upload. Measured clips of 1.1/1.3 seconds occupy 27/32 frames; only frame-rounding tails are silence. The handoff contains video, SRT, narration text, cover, metadata, AV checks and `handoff.json`. Replace the fixture's placeholder platform/account before any real publication.

Substitute `whole-audio.json` to test whole-recording input. For a real voiced film, replace fixture WAVs with reviewed speech and supply actual caption boundaries; the remaining commands are identical. A tone test is not TTS quality evidence.

## Audition and speech synthesis

An audition manifest has `voices: [{id, engine, wav}]` and optional shared `text`. Paths are relative to the manifest. Compare the same passage when choosing voices.

```bash
python scripts/production.py audition voices.json --out build/listen
# Only after an actual listening decision:
python scripts/production.py select-voice build/listen/auditions.json \
  --voice chosen-id --note "Accepted for this production after listening; recheck technical terms." \
  --out build/voice-selection.json
```

TTS `request.json`:

```json
{"mode":"scene","clips":[
  {"scene":0,"text":"The first scene narration.","voice":"selected-local-voice","language":"en"},
  {"scene":1,"text":"The second scene narration.","voice":"selected-local-voice","language":"en"}
]}
```

Use already-installed software and a reviewed local adapter following [the contract](../references/voice.md). Planning does not run it; execution is explicit:

```bash
python scripts/production.py tts request.json --adapter adapter.json --out build/tts-plan
python scripts/production.py tts request.json --adapter adapter.json --out build/speech --execute
python scripts/production.py prepare-audio story.json --audio build/speech/audio.json --out build/prepared-speech
```

For whole-script synthesis, use `mode: whole` and one clip containing the entire narration; add reviewed `boundaries` per scene to generated `audio.json`. No automatic segmentation is claimed. Correct unaccepted speech before finalization.

## Optional ASR

Existing Whisper-style JSON needs no model:

```bash
python scripts/production.py asr-check build/prepared-speech \
  --transcript checked-transcript.json --out build/asr-differences.json
```

To invoke an installed recognizer, configure `{audio_wav}`/`{output_json}` argv placeholders. `asr` plans by default and executes only with `--execute`:

```bash
python scripts/production.py asr build/prepared-speech/narration.wav \
  --adapter asr-adapter.json --out build/transcription --execute
python scripts/production.py asr-check build/prepared-speech \
  --transcript build/transcription/transcript.json --out build/asr-differences.json
```

Listen for omissions, repetition, terms and dates. Correct the script/audio and regenerate affected timing. ASR similarity is not a pronunciation score or forced alignment.

## Publication package and receipt

Metadata needs `title`, `description`, `platform`, `account`, `rights_note` and a string list of `tags`; include `sources` URLs when relevant. Keep credentials, private paths and internal notes out. Pattern scanning is only a limited aid to review.

Review `handoff.json`, the exact account, rights, captions, cover and final film. Obtain explicit authorization for the exact outward action. An existing browser capability or a person may upload; this repository does not control browsers or expose a platform API. A creation request or `package` command is not upload permission.

After an actual action, prepare a receipt:

```json
{
  "outcome":"published",
  "target":{"platform":"reviewed-platform","account":"reviewed-account"},
  "media_sha256":"video-hash-from-handoff.json",
  "recorded_at":"2026-10-16T12:00:00Z",
  "url":"https://actual-platform.example/confirmed-post",
  "authorization_note":"Record the real user's approval for this exact action.",
  "note":"Record what was actually verified in the browser."
}
```

```bash
python scripts/production.py record-publication build/handoff --receipt receipt.json --authorized
```

`--authorized` records the caller's statement; it does not create consent or perform an external action. Never use `published` without observed success. Other outcomes: `draft`, `failed`, `unknown`, `denied`, `not_attempted`; the last four can be recorded without the flag. Target/hash must match, changed handoff files are rejected, and existing receipts are never overwritten. Inspect uncertain external outcomes before retrying.


## Concrete optional engines and timing helpers

[Optional voice tools](optional-voice.md) provide Qwen 0.6B Serena / Whisper small local CPU adapters, pre-import offline and telemetry guards, pinned weight checks, energy/semantic caption estimates and quiet splicing. They reuse reviewed upstream source; portable inference has not been rerun here. The model-free fixture remains the reproducible baseline. Use `align-captions` output audio.json with `prepare-audio`; estimates retain a review-required label.
