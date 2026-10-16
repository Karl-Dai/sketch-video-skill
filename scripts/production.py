#!/usr/bin/env python3
"""Explicit local audio, timing, mixing and publication-handoff stages. No uploader."""
import argparse
from array import array
import copy
import difflib
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata
import wave

from render import load_story, timeline, write_editorial
from verify import verify

RATE = 48000


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def new(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    return path


def save_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2)+'\n')


def run(args):
    return subprocess.run([str(x) for x in args], check=True, capture_output=True)


def pcm(path):
    """Decode the complete audio to a common PCM format; no file download."""
    return run(['ffmpeg', '-v', 'error', '-xerror', '-i', path, '-map', '0:a:0', '-ac', '1', '-ar', str(RATE), '-f', 's16le', '-']).stdout


def wav(path, samples):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples)


def audio_stats(samples):
    values = array('h')
    values.frombytes(samples)
    if sys.byteorder != 'little':
        values.byteswap()
    if not values:
        raise ValueError('empty audio')
    peak = max(abs(x) for x in values)
    rms = math.sqrt(sum(x*x for x in values)/len(values))
    return dict(duration=len(values)/RATE, sample_rate=RATE, channels=1,
                peak_dbfs=round(20*math.log10(peak/32768), 3) if peak else None,
                rms_dbfs=round(20*math.log10(rms/32768), 3) if rms else None,
                clipped_samples=sum(abs(x) >= 32767 for x in values), silent=peak == 0)


def resolve(manifest, value):
    return Path(manifest).resolve().parent/Path(value)


def audition(manifest, out):
    data = read(manifest)
    voices = data.get('voices', [])
    if not voices or len({v['id'] for v in voices}) != len(voices):
        raise ValueError('provide voices with unique ids and pre-generated wav paths')
    out = new(out)
    entries = []
    for i, voice in enumerate(voices):
        samples = pcm(resolve(manifest, voice['wav']))
        name = f'voice-{i:03}.wav'
        wav(out/name, samples)
        entries.append(dict(id=voice['id'], wav=name, engine=voice.get('engine', 'imported'),
                            stats=audio_stats(samples), listening_status='pending'))
    report = dict(text=data.get('text', ''), voices=entries, selected=None,
                  note='Technical metrics do not establish naturalness or consent.')
    write(out/'auditions.json', report)
    return report


def select_voice(manifest, voice_id, note, out):
    data = read(manifest)
    candidate = next((v for v in data['voices'] if v['id'] == voice_id), None)
    if candidate is None or not note.strip():
        raise ValueError('select an existing voice with a specific listening-review note')
    result = dict(voice_id=voice_id, audition_sha256=hashlib.sha256(resolve(manifest, candidate['wav']).read_bytes()).hexdigest(),
                  decision='accepted_for_this_production', listening_note=note,
                  scope='A recorded caller decision; not a general quality guarantee.')
    save_new(out, result)
    return result


def adapter_config(path):
    config = read(path)
    if not isinstance(config.get('command'), list) or not config['command'] or not all(isinstance(x, str) for x in config['command']):
        raise ValueError('adapter command must be an argv array')
    model = config.get('model', {})
    for key in ('id', 'source', 'license', 'cost_note'):
        if not isinstance(model.get(key), str) or not model[key].strip():
            raise ValueError(f'adapter requires model.{key}')
    if 'download_bytes' not in model or (model['download_bytes'] is not None and (type(model['download_bytes']) is not int or model['download_bytes'] < 0)):
        raise ValueError('model.download_bytes must be a nonnegative integer or null (unknown)')
    return config


def runtime_profile(config):
    allowed = config.get('platforms')
    if allowed is not None and platform.system() not in allowed:
        raise ValueError('adapter is not validated for this platform; run a supported audition first')
    dtype = config.get('dtype', 'float32')
    if dtype not in ('float32', 'bfloat16', 'auto'):
        raise ValueError('adapter dtype must be float32, bfloat16 or auto')
    flags = Path('/proc/cpuinfo').read_text() if platform.system() == 'Linux' and Path('/proc/cpuinfo').is_file() else ''
    if dtype == 'auto' or (dtype == 'bfloat16' and 'avx512_bf16' not in flags):
        dtype = 'float32'
    return dict(system=platform.system(), machine=platform.machine(), dtype=dtype,
                note='Benchmark a short audition on this device; no transferable speed claim.')


def execute_adapter(config, values):
    runtime = runtime_profile(config)
    values = dict(values, dtype=runtime['dtype'], python=sys.executable, adapter_script=Path(__file__).resolve().with_name('voice.py'))
    args = []
    for value in config['command']:
        for key, replacement in values.items():
            value = value.replace('{'+key+'}', str(replacement))
        if re.search(r'\{[a-z_]+\}', value):
            raise ValueError('unresolved adapter placeholder')
        args.append(value)
    # Only invoked by the explicit --execute path. Configuration is executable code.
    environment = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                       HF_HUB_DISABLE_TELEMETRY='1', HF_HUB_DISABLE_IMPLICIT_TOKEN='1', ORT_DISABLE_TELEMETRY='1')
    result = subprocess.run(args, check=False, capture_output=True, env=environment)
    if result.returncode:
        raise ValueError(f'local adapter failed with exit code {result.returncode}; review its configuration locally')


def tts(request, adapter, out, execute=False):
    data, config = read(request), adapter_config(adapter)
    if data.get('mode') not in ('scene', 'whole') or not data.get('clips'):
        raise ValueError('TTS request requires scene/whole mode and clips')
    out = new(out).resolve()
    clips = []
    for i, item in enumerate(data['clips']):
        if not isinstance(item.get('text'), str) or not item['text'].strip():
            raise ValueError('each request needs text')
        text = out/f'clip-{i:03}.txt'
        text.write_text(item['text'], encoding='utf-8')
        target = out/f'clip-{i:03}.wav'
        values = dict(text_file=text, output_wav=target, voice=item.get('voice', ''), language=item.get('language', ''))
        if execute:
            execute_adapter(config, values)
            samples = pcm(target)
            if audio_stats(samples)['silent']:
                raise ValueError('adapter produced silent audio')
        clip = {k: item[k] for k in ('scene', 'caption_times') if k in item}
        clip['wav'] = target.name
        clips.append(clip)
    report = dict(mode=data['mode'], clips=clips, status='generated' if execute else 'planned_only',
                  model=config['model'], downloaded_by_core=False,
                  runtime=runtime_profile(config))
    if 'boundaries' in data:
        report['boundaries'] = data['boundaries']
    write(out/'audio.json', report)
    return report


def asr(audio, adapter, out, execute=False):
    config = adapter_config(adapter)
    out = new(out).resolve()
    report = dict(status='planned_only', model=config['model'], downloaded_by_core=False)
    if execute:
        execute_adapter(config, dict(audio_wav=Path(audio).resolve(), output_json=out/'transcript.json'))
        transcript_segments(read(out/'transcript.json'))
        report['status'] = 'transcribed_for_review'
    write(out/'asr-run.json', report)
    return report


def caption_spans(scene, duration, frames, fps, times):
    if times is None:
        return None
    if not isinstance(times, list) or len(times) != len(scene['captions']):
        raise ValueError('caption_times must match scene captions')
    spans, previous, cursor = [], 0., 0
    for i, pair in enumerate(times):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError('caption_times entries must be [start, end] seconds')
        a, b = pair
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in pair) or abs(a-previous) > .001 or b <= a or b > duration+.001:
            raise ValueError('caption_times must continuously cover the source clip')
        end = frames if i == len(times)-1 else round(b*fps)
        if end <= cursor:
            raise ValueError('caption boundary collapses after frame quantization')
        spans.append([cursor, end])
        cursor, previous = end, b
    if abs(previous-duration) > .001:
        raise ValueError('caption_times must end at measured audio duration')
    return spans


def prepare_audio(story_path, manifest, out, fps=24):
    story, data = load_story(story_path), read(manifest)
    scenes = story['scenes']
    chunks, timings = [], []
    if data.get('mode') == 'scene':
        clips = data.get('clips', [])
        if len(clips) != len(scenes) or [c.get('scene') for c in clips] != list(range(len(scenes))):
            raise ValueError('scene clips must cover every scene once in order, starting at 0')
        for i, clip in enumerate(clips):
            source = resolve(manifest, clip['wav'])
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            estimated = data.get('caption_timing') in ('energy_pause_estimate', 'semantic_pause_estimate')
            if estimated and not all(clip.get(k) for k in ('audio_sha256', 'expected_text_sha256')):
                raise ValueError('estimated caption times require source audio/text hashes')
            if clip.get('audio_sha256') is not None and clip['audio_sha256'] != before:
                raise ValueError('audio changed since caption alignment; regenerate timing')
            expected_text = ''.join(scenes[i].get('spoken_captions', scenes[i]['captions'])).strip()
            if clip.get('expected_text_sha256') is not None and clip['expected_text_sha256'] != hashlib.sha256(expected_text.encode()).hexdigest():
                raise ValueError('narration text changed since caption alignment; regenerate timing')
            samples = pcm(source)
            if hashlib.sha256(source.read_bytes()).hexdigest() != before:
                raise ValueError('source audio changed while decoding')
            chunks.append(samples)
            timings.append(clip.get('caption_times'))
    elif data.get('mode') == 'whole':
        if len(data.get('clips', [])) != 1:
            raise ValueError('whole mode requires one clip')
        samples = pcm(resolve(manifest, data['clips'][0]['wav']))
        boundaries = data.get('boundaries', [])
        if len(boundaries) != len(scenes):
            raise ValueError('whole audio requires reviewed [start,end] boundaries for every scene')
        cursor = 0
        for pair in boundaries:
            if not isinstance(pair, list) or len(pair) != 2 or any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in pair):
                raise ValueError('invalid whole-audio boundary')
            a, b = [round(t*RATE) for t in pair]
            if a != cursor or b <= a or b > len(samples)//2:
                raise ValueError('whole-audio boundaries must be ordered and contiguous')
            chunks.append(samples[a*2:b*2])
            cursor = b
        if cursor != len(samples)//2:
            raise ValueError('whole-audio boundaries must cover the full file')
        timings = data.get('caption_times', [None]*len(scenes))
        if len(timings) != len(scenes):
            raise ValueError('whole caption_times must match scenes')
    else:
        raise ValueError('audio manifest mode must be scene or whole')
    adjusted = copy.deepcopy(story)
    adjusted['narrated'] = True
    joined, alignment = bytearray(), []
    for i, (scene, samples, times) in enumerate(zip(adjusted['scenes'], chunks, timings)):
        stats = audio_stats(samples)
        if stats['silent'] or stats['clipped_samples']:
            raise ValueError('source audio is silent or clipped; fix before alignment')
        frames = max(fps, math.ceil((len(samples)//2)*fps/RATE))
        if frames/fps > 120:
            raise ValueError('audio scene exceeds 120 seconds; split the scene')
        scene['duration'] = frames/fps
        scene.pop('caption_frames', None)
        spans = caption_spans(scene, stats['duration'], frames, fps, times)
        if spans is not None:
            scene['caption_frames'] = spans
        pad = round(frames*RATE/fps)-len(samples)//2
        joined.extend(samples)
        joined.extend(b'\x00\x00'*pad)
        alignment.append(dict(scene=i, measured_seconds=stats['duration'], frame_duration=frames/fps,
                              padded_seconds=pad/RATE, caption_timing=(data.get('caption_timing', 'provided_boundaries_review_required') if spans else 'text_length_heuristic'), audio=stats))
    clock = timeline(adjusted, fps)
    out = new(out)
    write(out/'retimed.json', adjusted)
    write_editorial(out, adjusted, clock)
    wav(out/'narration.wav', joined)
    report = dict(fps=fps, frames=clock['frames'], duration=clock['duration'], scenes=alignment,
                  speech_alignment_verified=False, listening_review='required')
    write(out/'alignment.json', report)
    return report


def transcript_segments(data):
    segments = data.get('segments')
    if not isinstance(segments, list) or not segments:
        raise ValueError('ASR JSON requires nonempty segments with start/end/text')
    previous = 0
    for segment in segments:
        a, b = segment.get('start'), segment.get('end')
        if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in (a, b)) or a < previous or b <= a or not isinstance(segment.get('text'), str):
            raise ValueError('invalid ASR segment text or timing')
        previous = b
    return segments


def asr_check(prepared, transcript, out):
    clock = read(Path(prepared)/'timeline.json')
    segments = transcript_segments(read(transcript))
    if segments[-1]['end'] > clock['duration']+.08:
        raise ValueError('ASR timing exceeds prepared audio')
    normalize = lambda s: ''.join(c for c in unicodedata.normalize('NFKC', s).casefold() if c.isalnum())
    expected = normalize(''.join(c['text'] for c in clock['captions']))
    observed = normalize(''.join(s['text'] for s in segments))
    matcher = difflib.SequenceMatcher(None, expected, observed, autojunk=False)
    differences = [dict(kind=tag, expected=expected[a:b], observed=observed[c:d]) for tag, a, b, c, d in matcher.get_opcodes() if tag != 'equal']
    report = dict(status='review_required', normalized_text_agrees=expected == observed,
                  sequence_similarity=matcher.ratio(), differences=differences,
                  note='ASR is a fallible cross-check, not proof of pronunciation, meaning or word-level sync.')
    save_new(out, report)
    return report


def mux(rendered, prepared, out):
    rendered, prepared = Path(rendered), Path(prepared)
    verify(rendered)
    a, b = read(rendered/'timeline.json'), read(prepared/'timeline.json')
    if any(a[k] != b[k] for k in ('fps', 'frames', 'captions')):
        raise ValueError('render timeline differs from prepared audio; rerender retimed.json at its fps')
    samples = pcm(prepared/'narration.wav')
    if abs(len(samples)/2/RATE-a['duration']) > 1/RATE:
        raise ValueError('prepared WAV does not match frame clock')
    out = new(out)
    run(['ffmpeg', '-v', 'error', '-i', rendered/'video.mp4', '-i', prepared/'narration.wav', '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', out/'video.mp4'])
    for name in ('timeline.json', 'captions.srt', 'narration.txt'):
        shutil.copyfile(rendered/name, out/name)
    cover = sorted(rendered.glob('scene-*-middle.jpg'))
    if cover:
        shutil.copyfile(cover[0], out/'cover.jpg')
    report = read(rendered/'render-report.json')
    report.update(silent=False, sha256=hashlib.sha256((out/'video.mp4').read_bytes()).hexdigest(), bytes=(out/'video.mp4').stat().st_size)
    write(out/'render-report.json', report)
    return verify_av(out)


def verify_av(out):
    out = Path(out)
    report = verify(out, expected_audio=True, save_report=False)
    stats = audio_stats(pcm(out/'video.mp4'))
    if stats['silent'] or stats['clipped_samples']:
        raise ValueError('final audio is silent or contains clipped PCM samples')
    report.update(audio=stats, human_review='Listen through and inspect scene-boundary sync; technical checks cannot validate naturalness or semantic synchronization.')
    write(out/'av-verification.json', report)
    return report


def public_text(data):
    serialized = json.dumps(data, ensure_ascii=False)
    patterns = [r'libfile[_-][A-Za-z0-9]+', r'gh[pousr]_[A-Za-z0-9]{20,}', r'github_pat_[A-Za-z0-9_]+', r'/Users/[^/\s]+', r'/workspace/', r'/mnt/data', r'BEGIN (?:RSA |OPENSSH )?PRIVATE KEY']
    if any(re.search(p, serialized) for p in patterns):
        raise ValueError('potential private path or credential in publication text; review locally')


def make_package(final, metadata, out):
    final = Path(final)
    report = verify_av(final)
    meta = read(metadata)
    for key in ('title', 'description', 'platform', 'account', 'rights_note'):
        if not isinstance(meta.get(key), str) or not meta[key].strip():
            raise ValueError(f'publication metadata needs {key}; use explicit review placeholders until decided')
    if not isinstance(meta.get('tags'), list) or not all(isinstance(t, str) for t in meta['tags']):
        raise ValueError('publication tags must be a list of strings')
    public_text(meta)
    for name in ('timeline.json', 'render-report.json'):
        public_text(read(final/name))
    public_text((final/'narration.txt').read_text())
    out = new(out)
    for name in ('video.mp4', 'captions.srt', 'narration.txt', 'cover.jpg'):
        if (final/name).is_file():
            shutil.copyfile(final/name, out/name)
    write(out/'metadata.json', meta)
    write(out/'av-verification.json', report)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
    handoff = dict(status='ready_for_review', uploaded=False, target=dict(platform=meta['platform'], account=meta['account']),
                   files=hashes, authorization=None, checklist=[
                       'Review script facts, captions, cover, rights and privacy.',
                       'Listen to the complete final audio and inspect AV sync at scene boundaries.',
                       'Confirm platform/account, exact files and explicit current user authorization.',
                       'Use an existing authorized browser/session or upload manually; stop at login, CAPTCHA or uncertain state.',
                       'Check draft/published result, URL and media hash; save an accurate receipt. No automatic upload API is provided.'])
    write(out/'handoff.json', handoff)
    return handoff


def record_receipt(bundle, receipt, authorized=False):
    bundle = Path(bundle)
    handoff, data = read(bundle/'handoff.json'), read(receipt)
    for name, digest in handoff['files'].items():
        if Path(name).name != name or hashlib.sha256((bundle/name).read_bytes()).hexdigest() != digest:
            raise ValueError('handoff files changed; rebuild and review the bundle')
    if data.get('outcome') not in ('published', 'draft', 'failed', 'unknown', 'denied', 'not_attempted'):
        raise ValueError('invalid receipt outcome')
    if data.get('target') != handoff['target'] or data.get('media_sha256') != handoff['files']['video.mp4']:
        raise ValueError('receipt target/media differs from the reviewed bundle')
    for key in ('recorded_at', 'note'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError('receipt needs recorded_at and note')
    if data['outcome'] in ('published', 'draft'):
        if not authorized or not data.get('authorization_note') or not re.match(r'^https://[^\s]+$', data.get('url', '')):
            raise ValueError('successful publication receipt needs real authorization, evidence URL and authorization_note')
    data['authorization_recorded_by_caller'] = authorized
    data['external_action_performed_by_this_tool'] = False
    save_new(bundle/'publication-receipt.json', data)
    handoff.update(status=data['outcome'], uploaded=data['outcome'] in ('published', 'draft'))
    write(bundle/'handoff.json', handoff)
    return data


def fixture(out):
    """Generate clearly labelled sine-tone media for testing, never synthetic speech."""
    out = new(out)
    chunks = []
    for i, duration in enumerate((1.1, 1.3)):
        values = array('h', (int(4000*math.sin(2*math.pi*(330+i*110)*n/RATE)) for n in range(round(duration*RATE))))
        if sys.byteorder != 'little': values.byteswap()
        chunks.append(values.tobytes())
        wav(out/f'scene-{i}.wav', chunks[-1])
    wav(out/'whole.wav', b''.join(chunks))
    story = dict(version=1, title='TONE FIXTURE - NOT SPEECH', scenes=[
        dict(title='First test tone.', duration=2, layout='process', labels=['Test', 'Inspect'], captions=['Tone one.']),
        dict(title='Second test tone.', duration=2, layout='cycle', labels=['Check', 'Review'], captions=['Tone two.'])])
    write(out/'story.json', story)
    write(out/'audio.json', dict(mode='scene', clips=[dict(scene=i, wav=f'scene-{i}.wav', caption_times=[[0, duration]]) for i, duration in enumerate((1.1, 1.3))]))
    write(out/'whole-audio.json', dict(mode='whole', clips=[dict(wav='whole.wav')], boundaries=[[0, 1.1], [1.1, 2.4]]))
    write(out/'voices.json', dict(text='Sine tone fixture, not a voice audition.', voices=[dict(id='tone-test', engine='fixture-not-tts', wav='scene-0.wav')]))
    write(out/'transcript.json', dict(segments=[dict(start=0, end=1.1, text='Tone one.'), dict(start=1.125, end=2.425, text='Tone two.')], note='Hand-authored test transcript, not ASR output.'))
    write(out/'publication.json', dict(title='Technical fixture, not narration', description='Local sine-tone test. Review before any publication.', tags=['fixture'], platform='manual-demo', account='REVIEW_TARGET_BEFORE_PUBLISHING', rights_note='Original code-generated test tones and diagrams; font software is not included.', sources=[]))
    return dict(status='fixture_created', speech=False, model_download_bytes=0, files=sorted(p.name for p in out.iterdir()))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    def inputs(name, *names):
        s = sub.add_parser(name)
        for value in names:
            s.add_argument(value, type=Path)
        return s
    s = inputs('audition', 'manifest'); s.add_argument('--out', required=True, type=Path)
    s = inputs('select-voice', 'auditions'); s.add_argument('--voice', required=True); s.add_argument('--note', required=True); s.add_argument('--out', required=True, type=Path)
    for name, source in [('tts', 'request'), ('asr', 'audio')]:
        s = inputs(name, source); s.add_argument('--adapter', required=True, type=Path); s.add_argument('--out', required=True, type=Path); s.add_argument('--execute', action='store_true')
    s = inputs('prepare-audio', 'story'); s.add_argument('--audio', required=True, type=Path); s.add_argument('--out', required=True, type=Path); s.add_argument('--fps', type=int, choices=(12, 24, 30), default=24)
    s = inputs('asr-check', 'prepared'); s.add_argument('--transcript', required=True, type=Path); s.add_argument('--out', required=True, type=Path)
    s = inputs('mux', 'rendered', 'prepared'); s.add_argument('--out', required=True, type=Path)
    inputs('verify-av', 'output')
    s = inputs('package', 'final'); s.add_argument('--metadata', required=True, type=Path); s.add_argument('--out', required=True, type=Path)
    s = inputs('record-publication', 'bundle'); s.add_argument('--receipt', required=True, type=Path); s.add_argument('--authorized', action='store_true')
    s = inputs('fixture'); s.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    if a.command == 'fixture': result = fixture(a.out)
    elif a.command == 'audition': result = audition(a.manifest, a.out)
    elif a.command == 'select-voice': result = select_voice(a.auditions, a.voice, a.note, a.out)
    elif a.command == 'tts': result = tts(a.request, a.adapter, a.out, a.execute)
    elif a.command == 'asr': result = asr(a.audio, a.adapter, a.out, a.execute)
    elif a.command == 'prepare-audio': result = prepare_audio(a.story, a.audio, a.out, a.fps)
    elif a.command == 'asr-check': result = asr_check(a.prepared, a.transcript, a.out)
    elif a.command == 'mux': result = mux(a.rendered, a.prepared, a.out)
    elif a.command == 'verify-av': result = verify_av(a.output)
    elif a.command == 'package': result = make_package(a.final, a.metadata, a.out)
    elif a.command == 'record-publication': result = record_receipt(a.bundle, a.receipt, a.authorized)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f'production failed: {error}', file=sys.stderr)
        sys.exit(1)
