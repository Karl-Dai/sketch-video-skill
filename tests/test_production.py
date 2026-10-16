from pathlib import Path
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import production as prod
from render import load_story, timeline


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root/'inputs'
        prod.fixture(self.inputs)

    def test_scene_and_whole_audio_use_measured_duration(self):
        a = self.root/'scene'
        result = prod.prepare_audio(self.inputs/'story.json', self.inputs/'audio.json', a)
        self.assertEqual(result['frames'], 59)
        self.assertEqual(result['scenes'][0]['measured_seconds'], 1.1)
        clock = timeline(load_story(a/'retimed.json'), 24)
        self.assertEqual(clock['captions'][1]['start_frame'], 27)
        b = self.root/'whole'
        prod.prepare_audio(self.inputs/'story.json', self.inputs/'whole-audio.json', b)
        self.assertEqual(prod.pcm(a/'narration.wav'), prod.pcm(b/'narration.wav'))

    def test_bad_boundaries_and_audio_are_rejected(self):
        manifest = prod.read(self.inputs/'whole-audio.json')
        manifest['boundaries'][1][0] = 1.2
        prod.write(self.inputs/'bad.json', manifest)
        with self.assertRaisesRegex(ValueError, 'contiguous'):
            prod.prepare_audio(self.inputs/'story.json', self.inputs/'bad.json', self.root/'bad')
        prod.wav(self.inputs/'scene-0.wav', b'\x00\x00'*48000)
        with self.assertRaisesRegex(ValueError, 'silent'):
            prod.prepare_audio(self.inputs/'story.json', self.inputs/'audio.json', self.root/'silence')
        prod.wav(self.inputs/'scene-0.wav', b'\xff\x7f'*48000)
        with self.assertRaisesRegex(ValueError, 'clipped'):
            prod.prepare_audio(self.inputs/'story.json', self.inputs/'audio.json', self.root/'clipped')

    def test_review_and_asr_never_claim_quality_approval(self):
        out = self.root/'audition'
        report = prod.audition(self.inputs/'voices.json', out)
        self.assertIsNone(report['selected'])
        with self.assertRaises(ValueError):
            prod.select_voice(out/'auditions.json', 'missing', 'test', self.root/'selection.json')
        prod.select_voice(out/'auditions.json', 'tone-test', 'Technical fixture selection only.', self.root/'selection.json')
        prepared = self.root/'prepared'
        prod.prepare_audio(self.inputs/'story.json', self.inputs/'audio.json', prepared)
        result = prod.asr_check(prepared, self.inputs/'transcript.json', self.root/'asr.json')
        self.assertTrue(result['normalized_text_agrees'])
        self.assertEqual(result['status'], 'review_required')
        data = prod.read(self.inputs/'transcript.json')
        data['segments'][0]['text'] = 'A wrong word'
        prod.write(self.inputs/'wrong.json', data)
        self.assertFalse(prod.asr_check(prepared, self.inputs/'wrong.json', self.root/'diff.json')['normalized_text_agrees'])

    def test_local_adapters_require_execute_and_keep_model_metadata(self):
        adapter = self.root/'fake.py'
        adapter.write_text('import sys,wave,math,struct,json\nif sys.argv[1]=="tts":\n w=wave.open(sys.argv[2],"wb");w.setparams((1,2,48000,0,"NONE","not compressed"));w.writeframes(b"".join(struct.pack("<h",int(3000*math.sin(n*.1))) for n in range(48000)));w.close()\nelse:\n open(sys.argv[2],"w").write(json.dumps({"segments":[{"start":0,"end":1,"text":"Fixture"}]}))\n')
        model = dict(id='fixture-not-model', source='local test code', license='MIT', download_bytes=0, cost_note='No model; CPU test only.')
        config = dict(command=[sys.executable, str(adapter), 'tts', '{output_wav}'], model=model)
        prod.write(self.root/'adapter.json', config)
        prod.write(self.root/'request.json', dict(mode='scene', clips=[dict(scene=0, text='Fixture', voice='test', language='en')]))
        prod.tts(self.root/'request.json', self.root/'adapter.json', self.root/'plan')
        self.assertFalse((self.root/'plan/clip-000.wav').exists())
        prod.tts(self.root/'request.json', self.root/'adapter.json', self.root/'generated', True)
        self.assertTrue((self.root/'generated/clip-000.wav').exists())
        config['command'][2:] = ['asr', '{output_json}']
        prod.write(self.root/'asr-adapter.json', config)
        prod.asr(self.inputs/'whole.wav', self.root/'asr-adapter.json', self.root/'asr-output', True)
        self.assertTrue((self.root/'asr-output/transcript.json').exists())

    def test_caption_clock_rejects_invalid_explicit_spans(self):
        story = load_story(self.inputs/'story.json')
        story['scenes'][0]['caption_frames'] = [[1, 48]]
        with self.assertRaises(ValueError): timeline(story, 24)
        with self.assertRaises(ValueError): prod.caption_spans(story['scenes'][0], 1.1, 27, 24, [[0, .9]])

    def test_full_av_pipeline_and_publication_authorization(self):
        font = os.environ.get('TEST_FONT')
        if not font: self.skipTest('TEST_FONT not set')
        prepared, rendered, final = [self.root/x for x in ('prepared', 'rendered', 'final')]
        prod.prepare_audio(self.inputs/'story.json', self.inputs/'audio.json', prepared)
        subprocess.run([sys.executable, str(ROOT/'scripts/render.py'), str(prepared/'retimed.json'), '--out', str(rendered), '--font', font, '--size', '360x640'], check=True, capture_output=True)
        result = prod.mux(rendered, prepared, final)
        self.assertEqual(result['decoded_frames'], 59)
        self.assertEqual(result['audio_streams'], 1)
        clock = prod.read(prepared/'timeline.json')
        wrong = copy.deepcopy(clock)
        wrong['frames'] += 1
        prod.write(prepared/'timeline.json', wrong)
        with self.assertRaisesRegex(ValueError, 'differs'):
            prod.mux(rendered, prepared, self.root/'mismatched')
        prod.write(prepared/'timeline.json', clock)
        bundle = self.root/'bundle'
        handoff = prod.make_package(final, self.inputs/'publication.json', bundle)
        self.assertFalse(handoff['uploaded'])
        receipt = dict(outcome='published', target=handoff['target'], media_sha256=handoff['files']['video.mp4'], recorded_at='2026-10-16T00:00:00Z', note='Fixture only; no upload occurred.', url='https://example.invalid/fixture', authorization_note='Unit test; not real publication approval.')
        prod.write(self.root/'receipt.json', receipt)
        with self.assertRaisesRegex(ValueError, 'authorization'):
            prod.record_receipt(bundle, self.root/'receipt.json')
        receipt['outcome'] = 'not_attempted'
        prod.write(self.root/'receipt.json', receipt)
        saved = prod.record_receipt(bundle, self.root/'receipt.json')
        self.assertFalse(saved['external_action_performed_by_this_tool'])
        self.assertEqual(prod.read(bundle/'handoff.json')['status'], 'not_attempted')
        with self.assertRaises(ValueError): prod.public_text(dict(description='lib'+'file_'+'private123'))


if __name__ == '__main__': unittest.main()
