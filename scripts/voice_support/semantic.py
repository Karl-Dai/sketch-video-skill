"""Support energy-pause estimates with unprompted ASR phrase edges; never forced alignment."""
import difflib
import hashlib
import math
import unicodedata


def normalize(text):
    digits = dict(zip('0123456789', '零一二三四五六七八九'))
    return ''.join(digits.get(c, c) for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


def phonetic(text):
    from pypinyin import lazy_pinyin, Style
    return [lazy_pinyin(c, style=Style.NORMAL, errors=lambda x: list(x))[0] for c in text]


def support_boundaries(report, transcript, spoken):
    from production import transcript_segments
    segments = transcript_segments(transcript)
    if transcript.get('prompt_used') is not False:
        raise ValueError('semantic alignment requires an explicitly unprompted ASR report')
    duration = transcript.get('audio_duration_seconds')
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('ASR duration must be finite and positive')
    expected_hash = hashlib.sha256(''.join(spoken).strip().encode()).hexdigest()
    if (transcript.get('audio_sha256') != report['audio_sha256'] or
            transcript.get('expected_text_sha256') != expected_hash or
            abs(transcript.get('audio_duration_seconds', -1)-report['duration_seconds']) > .001):
        raise ValueError('ASR audio/text hashes or duration differ; regenerate this scene report')
    if segments[-1]['end'] > report['duration_seconds']+.08:
        raise ValueError('ASR timestamps exceed source audio')
    expected = ''.join(normalize(text) for text in spoken)
    observed, starts, ends = '', {}, {}
    for seg in segments:
        chars = normalize(seg['text'])
        if chars:
            starts[len(observed)] = seg['start']
            observed += chars
            ends[len(observed)] = seg['end']
    matcher = difflib.SequenceMatcher(None, phonetic(expected), phonetic(observed), autojunk=False)
    mapping = {}
    for tag, a, b, c, d in matcher.get_opcodes():
        if tag == 'equal': mapping.update({a+i: c+i for i in range(b-a)})
    position = 0
    for i, boundary in enumerate(report['boundaries']):
        position += len(normalize(spoken[i]))
        left, right = mapping.get(position-1), mapping.get(position)
        edges = left is not None and right == left+1 and right in starts and right in ends
        window = list(range(max(0, position-6), min(len(expected), position+6)))
        coverage = sum(p in mapping for p in window)/max(1, len(window))
        pause = boundary.get('pause_span_seconds')
        previous, following = ends.get(right), starts.get(right)
        overlap = max(0, min(following, pause[1])-max(previous, pause[0])) if edges and pause else 0
        high = edges and coverage >= .9 and overlap >= .08
        nearby = edges and coverage >= .9 and pause and min(abs(boundary['time_seconds']-previous), abs(boundary['time_seconds']-following)) <= .6
        chosen = (max(previous, pause[0])+min(following, pause[1]))/2 if high else boundary['time_seconds']
        boundary.update(time_seconds=chosen, semantic_confidence='high' if high else 'medium' if nearby else 'low',
                        asr_boundary_at_phrase_edges=edges, local_match_coverage=coverage,
                        semantic_method='asr_gap_pause_intersection' if high else 'retained_energy_pause',
                        requires_listening_review=True)
        boundary.setdefault('warnings', []).append('ASR context supports an energy estimate; listen to this boundary.' if high or nearby else 'ASR phrase edges do not independently resolve this boundary; manual review required.')
    times = [0.] + [b['time_seconds'] for b in report['boundaries']] + [report['duration_seconds']]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('semantic estimates crossed; review source pauses manually')
    for i, caption in enumerate(report['captions']):
        caption.update(start_seconds=times[i], end_seconds=times[i+1], duration_seconds=times[i+1]-times[i])
    report.update(method='unprompted_asr_phrase_edges_plus_energy_pause', phonetic_match_ratio=matcher.ratio(),
                  confidence_note='Heuristic context support, not probability, forced alignment or human listening approval.',
                  asr_used=True, word_level_alignment=False, requires_listening_review=True,
                  overall_confidence=min((b['semantic_confidence'] for b in report['boundaries']), key={'low':0,'medium':1,'high':2}.get) if report['boundaries'] else 'not_applicable')
    report['warnings'] = [w for w in report['warnings'] if not w.startswith('Energy/punctuation timing estimate only:')]
    report['warnings'].append('ASR context plus energy estimate only: no forced alignment or human listening approval.')
    return report
