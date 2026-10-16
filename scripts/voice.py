#!/usr/bin/env python3
"""Optional offline voice tools. No model downloads; ML imports happen only on explicit inference."""
import os
# These must run before importing Qwen, Transformers, ONNX Runtime or their dependencies.
for _key in ('ORT_DISABLE_TELEMETRY', 'HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE',
             'HF_HUB_DISABLE_TELEMETRY', 'HF_HUB_DISABLE_IMPLICIT_TOKEN'):
    os.environ[_key] = '1'

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys
import time

MODELS = {
    'qwen': {'id': 'Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice',
             'revision': '85e237c12c027371202489a0ec509ded67b5e4b5', 'license': 'Apache-2.0',
             'weights': {'model.safetensors': 'bc3c7e785eb961179c25450d1acff03f839e0002f2f3a5aeb67b5735c0fa2adb',
                         'speech_tokenizer/model.safetensors': '836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258'}},
    'whisper': {'id': 'openai/whisper-small',
                'revision': '973afd24965f72e36ca33b3055d56a652f456b4d', 'license': 'MIT',
                'weights': {'model.safetensors': '1d7734884874f1a1513ed9aa760a4f8e97aaa02fd6d93a3a85d27b2ae9ca596b'}}
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(8*1024*1024), b''):
            h.update(part)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, data):
    with Path(path).open('x', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write('\n')


def verify_model(kind, directory):
    """Verify pinned weight bytes locally. Config/tokenizer JSON is not authenticated by these hashes."""
    directory = Path(directory)
    if not directory.is_dir() or not (directory/'config.json').is_file():
        raise ValueError('provide a complete trusted local model directory with config.json')
    for name, expected in MODELS[kind]['weights'].items():
        if digest(directory/name) != expected:
            raise ValueError(f'{kind}: weight checksum mismatch: {name}')
    return dict(model=MODELS[kind], status='pinned_weights_verified', downloaded=False,
                note='Acquire all configuration/tokenizer files from the pinned official revision too.')


def profile(dtype, threads):
    if not 1 <= threads <= 64:
        raise ValueError('threads must be between 1 and 64')
    flags = Path('/proc/cpuinfo').read_text() if platform.system() == 'Linux' and Path('/proc/cpuinfo').is_file() else ''
    selected = 'bfloat16' if dtype == 'bfloat16' and 'avx512_bf16' in flags else 'float32'
    return dict(system=platform.system(), machine=platform.machine(), device='cpu', dtype=selected, threads=threads)


def qwen(args):
    if args.output.exists() or args.output.with_suffix('.json').exists():
        raise FileExistsError('choose a new WAV and sidecar path')
    if not 1 <= args.max_new_tokens <= 4096:
        raise ValueError('max_new_tokens must be between 1 and 4096')
    text = args.text_file.read_text(encoding='utf-8').strip()
    if not text:
        raise ValueError('empty narration text')
    verified = verify_model('qwen', args.model_dir)  # Fail before importing ML.
    runtime = profile(args.dtype, args.threads)
    os.environ['OMP_NUM_THREADS'] = os.environ['MKL_NUM_THREADS'] = str(args.threads)
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.manual_seed(args.seed)
    started = time.perf_counter()
    model = Qwen3TTSModel.from_pretrained(str(args.model_dir.resolve()), device_map='cpu',
                dtype=getattr(torch, runtime['dtype']), attn_implementation='sdpa',
                local_files_only=True, trust_remote_code=False, use_safetensors=True)
    speakers = model.get_supported_speakers()
    if args.voice.casefold() not in [s.casefold() for s in speakers]:
        raise ValueError('voice is not supported by this local checkpoint')
    steps = [0]
    def count(*unused): steps[0] += 1
    hook = model.model.talker.register_forward_hook(count)
    try:
        with torch.inference_mode():
            waves, rate = model.generate_custom_voice(text=text, language=args.language, speaker=args.voice,
                         non_streaming_mode=True, max_new_tokens=args.max_new_tokens)
    finally:
        hook.remove()
    if steps[0] >= args.max_new_tokens:
        raise ValueError('generation reached token limit; split the narration and review before retrying')
    if not isinstance(rate, (int, np.integer)) or rate <= 0:
        raise ValueError('invalid generated audio sample rate')
    audio = np.asarray(waves[0], dtype=np.float32)
    if audio.ndim != 1 or not len(audio) or not np.isfinite(audio).all() or np.max(np.abs(audio)) >= 1 or not np.any(audio):
        raise ValueError('generated audio is empty, nonfinite, silent or clipped')
    with args.output.open('xb') as file:
        sf.write(file, audio, rate, format='WAV', subtype='PCM_24')
    result = dict(verified, runtime=runtime, voice=args.voice, style_instruction=None,
                  text_sha256=hashlib.sha256(text.encode()).hexdigest(), audio_sha256=digest(args.output),
                  duration_seconds=len(audio)/rate, elapsed_seconds=time.perf_counter()-started,
                  decoding_steps=steps[0], listening_review='required')
    save(args.output.with_suffix('.json'), result)
    return result


def whisper(args):
    if args.output.exists():
        raise FileExistsError('choose a new transcript path')
    verified = verify_model('whisper', args.model_dir)
    runtime = profile('float32', args.threads)
    os.environ['OMP_NUM_THREADS'] = os.environ['MKL_NUM_THREADS'] = str(args.threads)
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    import torch
    from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq, pipeline
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    started = time.perf_counter()
    processor = AutoProcessor.from_pretrained(str(args.model_dir.resolve()), local_files_only=True, trust_remote_code=False)
    model = AutoModelForSpeechSeq2Seq.from_pretrained(str(args.model_dir.resolve()), dtype=torch.float32,
                attn_implementation='eager', local_files_only=True, trust_remote_code=False, use_safetensors=True).to('cpu')
    audio, rate = sf.read(args.audio, dtype='float32')
    if audio.ndim != 1 or not len(audio) or not np.isfinite(audio).all():
        raise ValueError('Whisper adapter requires finite, nonempty mono audio')
    original_duration = len(audio)/rate
    divisor = math.gcd(rate, 16000)
    if rate != 16000:
        audio = resample_poly(audio, 16000//divisor, rate//divisor).astype(np.float32)
    runner = pipeline('automatic-speech-recognition', model=model, tokenizer=processor.tokenizer,
                      feature_extractor=processor.feature_extractor, device=-1, dtype=torch.float32)
    raw = runner({'array': audio, 'sampling_rate': 16000}, return_timestamps='word',
                 generate_kwargs={'language': args.language, 'task': 'transcribe', 'num_beams': 1,
                                  'do_sample': False, 'max_new_tokens': 440})
    segments = []
    for chunk in raw.get('chunks', []):
        stamp = chunk.get('timestamp')
        if not stamp or any(t is None or not math.isfinite(t) for t in stamp):
            raise ValueError('ASR returned incomplete timestamps; review raw output with an engine-specific runner')
        segments.append(dict(start=float(stamp[0]), end=float(stamp[1]), text=chunk['text']))
    from production import transcript_segments
    transcript_segments(dict(segments=segments))
    if segments[-1]['end'] > original_duration+.08:
        raise ValueError('ASR timestamp exceeds source audio duration')
    result = dict(verified, segments=segments, text=raw.get('text', ''), audio_sha256=digest(args.audio),
                  audio_duration_seconds=original_duration, runtime=runtime, prompt_used=False,
                  elapsed_seconds=time.perf_counter()-started, listening_review='required',
                  timestamp_note='Chinese word chunks can be phrases; not forced alignment or measured character times.')
    if args.expected_text_file:
        expected = args.expected_text_file.read_text(encoding='utf-8').strip()
        result['expected_text_sha256'] = hashlib.sha256(expected.encode()).hexdigest()
    save(args.output, result)
    return result


def align(story_path, manifest_path, out, asr_manifest=None):
    from render import load_story
    from voice_support.alignment import align_file
    from voice_support.semantic import support_boundaries
    story, manifest = load_story(story_path), read(manifest_path)
    clips = manifest.get('clips', [])
    if manifest.get('mode') != 'scene' or [c.get('scene') for c in clips] != list(range(len(story['scenes']))):
        raise ValueError('alignment needs one ordered source WAV per scene')
    reports = {}
    if asr_manifest:
        rows = read(asr_manifest)['scenes']
        if [r.get('scene') for r in rows] != list(range(len(clips))):
            raise ValueError('ASR manifest must cover all scenes in order')
        reports = {r['scene']: Path(asr_manifest).resolve().parent/r['transcript'] for r in rows}
    out.mkdir(parents=True, exist_ok=False)
    aligned = []
    for i, (scene, clip) in enumerate(zip(story['scenes'], clips)):
        audio = Path(manifest_path).resolve().parent/clip['wav']
        spoken = scene.get('spoken_captions', scene['captions'])
        if not isinstance(spoken, list) or len(spoken) != len(scene['captions']) or any(not isinstance(x, str) or not x.strip() for x in spoken):
            raise ValueError('spoken_captions must match display captions')
        captions = [dict(text=text, spoken_text=speech) for text, speech in zip(scene['captions'], spoken)]
        report = align_file(audio, captions)
        report.pop('audio_file', None)
        report['audio_sha256'] = digest(audio)
        report['expected_text_sha256'] = hashlib.sha256(''.join(spoken).strip().encode()).hexdigest()
        if reports:
            report = support_boundaries(report, read(reports[i]), spoken)
        save(out/f'scene-{i:03}.json', report)
        aligned.append(dict(scene=i, wav=str(audio.resolve()), caption_times=[
            [c['start_seconds'], c['end_seconds']] for c in report['captions']]))
    result = dict(mode='scene', clips=aligned, caption_timing='semantic_pause_estimate' if reports else 'energy_pause_estimate',
                  listening_review='required', forced_alignment=False)
    save(out/'audio.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('voice-doctor')
    s = sub.add_parser('verify-model'); s.add_argument('kind', choices=MODELS); s.add_argument('--model-dir', required=True, type=Path)
    for name in ('qwen', 'whisper'):
        s = sub.add_parser(name); s.add_argument('--model-dir', required=True, type=Path)
        s.add_argument('--output', required=True, type=Path); s.add_argument('--threads', type=int, default=6 if name == 'qwen' else 3)
        s.add_argument('--language', default='Chinese' if name == 'qwen' else 'chinese')
        if name == 'qwen':
            s.add_argument('--text-file', required=True, type=Path); s.add_argument('--voice', default='Serena')
            s.add_argument('--dtype', choices=('float32','bfloat16','auto'), default='float32')
            s.add_argument('--seed', type=int, default=20261016); s.add_argument('--max-new-tokens', type=int, default=900)
        else:
            s.add_argument('--audio', required=True, type=Path); s.add_argument('--expected-text-file', type=Path)
    s = sub.add_parser('align-captions'); s.add_argument('story', type=Path); s.add_argument('--audio', required=True, type=Path)
    s.add_argument('--asr-manifest', type=Path); s.add_argument('--out', required=True, type=Path)
    s = sub.add_parser('splice-audio')
    for name in ('prefix','suffix','output'): s.add_argument('--'+name, required=True, type=Path)
    for name in ('prefix-cut','suffix-cut'): s.add_argument('--'+name, required=True, type=float)
    args = parser.parse_args()
    if args.command == 'voice-doctor':
        result = dict(python=sys.version.split()[0], platform=platform.system(), models_downloaded=False,
                      modules={m: importlib.util.find_spec(m) is not None for m in ('numpy','soundfile','scipy','pypinyin','torch','qwen_tts','transformers')},
                      environment={k: os.environ[k] for k in ('ORT_DISABLE_TELEMETRY','HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','HF_HUB_DISABLE_TELEMETRY','HF_HUB_DISABLE_IMPLICIT_TOKEN')},
                      note='Module presence does not establish model availability, compatibility or quality.')
    elif args.command == 'verify-model': result = verify_model(args.kind, args.model_dir)
    elif args.command == 'qwen': result = qwen(args)
    elif args.command == 'whisper': result = whisper(args)
    elif args.command == 'align-captions': result = align(args.story, args.audio, args.out, args.asr_manifest)
    elif args.command == 'splice-audio':
        from voice_support.splice_audio import write_composite
        result = write_composite(args.prefix, args.suffix, args.prefix_cut, args.suffix_cut, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, ImportError, RuntimeError) as exc:
        print(f'voice tools failed: {exc}', file=sys.stderr)
        sys.exit(1)
