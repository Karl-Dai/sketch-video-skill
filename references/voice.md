# Audio production: executable stages and honest limits

The silent path remains supported. `scripts/production.py` adds WAV import, audition/selection records, explicit local TTS/ASR adapters, audio-based scene timing, reviewed caption boundaries, AAC mixing, full AV checks, local publication bundles and receipts. No model, font, installer or uploader is bundled. See [the complete walkthrough](../docs/production.md).

## Status

A completed upstream Linux production used Qwen3-TTS Serena and local unprompted Whisper small checks: 18 scenes, 54 continuous captions, 358.875 seconds, H.264/AAC and full decoding. This is source provenance, not a new inference run of this repository's wrappers. No sentence-by-sentence human listening result is claimed. The portable optional adapters are covered by synthetic/guard tests; see [setup, exact model revisions and validation limits](../docs/optional-voice.md). The earlier Kokoro audition is not the selected voice.

## Model-free audio contract

Paths are relative to the manifest. Inputs are decoded completely to mono 48 kHz PCM16; the core never fetches them.

```json
{"mode":"scene","clips":[
  {"scene":0,"wav":"scene-0.wav","caption_times":[[0,1.2],[1.2,3.7]]},
  {"scene":1,"wav":"scene-1.wav"}
]}
```

Scene ids cover the storyboard once, in order from 0. Optional caption times are provided clip-relative seconds (review required unless separately recorded), matching caption count and covering the measured duration continuously. They become integer frame boundaries shared by SRT and burn-in. Without them, caption timing remains a labelled text-length heuristic, not forced alignment.

Whole-file input: `{"mode":"whole","clips":[{"wav":"whole.wav"}],"boundaries":[[0,3.7],[3.7,8.2]]}`. Supply one reviewed boundary per scene, covering the entire file without gaps. Optional `caption_times` is a list of per-scene lists relative to each extracted clip. The tool does not guess cuts from a recording.

Scene durations round upward to a frame boundary with a one-second minimum; only the extra tail is padded with silence. Speech is never truncated or stretched. Split scenes over 120 seconds. Render `retimed.json` at its fps; mixing refuses a timeline different from the prepared audio.

## Local adapter contract

Adapters are trusted executable configuration, not downloaded plugins. `tts` and `asr` default to planning files only. `--execute` explicitly runs the configured local argv without a shell. Supply installed software and local weights; do not use a remote model id that silently downloads. Hugging Face offline/token/telemetry flags and ORT_DISABLE_TELEMETRY are set before launching the subprocess, but arbitrary code still needs review; these flags are not a network sandbox.

```json
{
  "command":["/path/to/model-env/python","/path/to/local_adapter.py","--text-file","{text_file}","--output","{output_wav}","--voice","{voice}","--language","{language}","--dtype","{dtype}"],
  "dtype":"auto",
  "model":{"id":"exact-local-checkpoint-and-revision","source":"official model URL","license":"exact checkpoint license","download_bytes":null,"cost_note":"Not measured; local compute/storage. No paid API invoked by core."}
}
```

TTS requests contain `mode: scene|whole` and `clips` with `text`, `voice`, `language`, and scene ids for scene mode. The adapter writes each requested WAV. Whole synthesis does not infer scene boundaries. ASR adapters use `{audio_wav}`/`{output_json}` and write Whisper-style finite, ordered `segments` with `start`, `end`, `text`. `asr-check` produces differences for review; it never silently rewrites captions or declares listening approval.

Runtime defaults to float32. Requested bfloat16 is used only with a detected Linux `avx512_bf16` CPU flag; otherwise it falls back to float32. `platforms: ["Linux"]` can restrict an adapter. GPU-specific runners need their own capability checks. The upstream benchmark used Linux/AMD CPU, AVX512 BF16, bfloat16 + SDPA, six threads; no speed or Linux `+cpu` wheel instruction transfers to macOS. Unknown devices need a short audition and measured runtime first.

## Models, licenses and resource costs

| Component | Size/cost boundary | License/source |
| --- | --- | --- |
| Core WAV/fixture pipeline | **0 model-download bytes**, no model/API cost; CPU rendering, encoding and storage still consume resources. | Original code: MIT. |
| Qwen3-TTS CustomVoice | Official variants: 0.6B and 1.7B parameters. Exact checkpoint/tokenizer download bytes and runtime depend on revision; record measured bytes. `download_bytes: null` means unknown, not zero. No weights bundled. | [Official Qwen repository](https://github.com/QwenLM/Qwen3-TTS), Apache-2.0; verify the exact checkpoint/voice distribution too. |
| Optional Whisper small | Official multilingual small: 244M parameters, approximately 2 GB VRAM in the upstream table. Checkpoint bytes and actual CPU/GPU cost depend on distribution; record measured values. No engine/weights bundled. | [Official Whisper](https://github.com/openai/whisper), MIT code/model license. |

The 0.6B CustomVoice Serena path does **not** support extra style instructions; no expressive-style control is invented here. Do not infer its capabilities from 1.7B. Before any separately authorized download, record exact id/revision, license, bytes, device/dtype and a compute estimate.

## Final checks and publication boundary

`verify-av` checks one H.264/yuv420p video and one mono 48 kHz AAC stream, frames, continuous captions, SRT consistency, AV start/duration deltas (≤80 ms), complete decoding of both streams, and PCM peak/RMS, silence and clipping. Peak/RMS is not integrated broadcast loudness certification. These checks do not prove semantic sync, pronunciation or naturalness: listen to the complete film and inspect boundaries.

`package` creates a local media/cover/subtitle/metadata/checks directory with hashes and a review checklist. It sends nothing. A platform action needs an authorized browser/session, the exact account and explicit current user approval. Stop at login/CAPTCHA/uncertainty. `record-publication` stores caller evidence and authorization notes, including draft, failure, unknown and not-attempted outcomes. It neither uploads nor independently confirms a post, and provides no generic Xiaohongshu API.


Concrete local Qwen/Whisper commands, pause/semantic alignment and quiet splicing are now provided in [the optional voice tools](../docs/optional-voice.md). `{python}` resolves to the selected interpreter and `{adapter_script}` to the bundled voice.py. No model download command exists.
