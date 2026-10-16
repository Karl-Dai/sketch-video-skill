"""Synthetic signals and mocked engine imports, never speech/model quality claims."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from contextlib import nullcontext
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import voice


class VoiceGuardTests(unittest.TestCase):
    def test_import_guards_before_optional_modules(self):
        code = "import os,sys; import voice; assert all(os.environ[k]=='1' for k in ('ORT_DISABLE_TELEMETRY','HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','HF_HUB_DISABLE_TELEMETRY','HF_HUB_DISABLE_IMPLICIT_TOKEN')); assert not any(m in sys.modules for m in ('torch','qwen_tts','transformers','onnxruntime','numpy')); print('guarded')"
        result = subprocess.run([sys.executable, '-c', code], env=dict(os.environ, PYTHONPATH=str(Path(voice.__file__).parent), ORT_DISABLE_TELEMETRY='0'), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pinned_weights_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'config.json').write_text('{}'); (root/'model.safetensors').write_bytes(b'synthetic-not-a-model')
            with self.assertRaises(ValueError): voice.verify_model('whisper', root)
            fake = copy.deepcopy(voice.MODELS)
            fake['whisper']['weights']['model.safetensors'] = hashlib.sha256(b'synthetic-not-a-model').hexdigest()
            with patch.object(voice, 'MODELS', fake):
                self.assertFalse(voice.verify_model('whisper', root)['downloaded'])
            with patch('voice.platform.system', return_value='Darwin'):
                self.assertEqual(voice.profile('bfloat16', 3)['dtype'], 'float32')

    def test_new_commands_help_without_models(self):
        cli = Path(voice.__file__).parents[1]/'bin/sketch-video.js'
        for command in ('qwen','whisper','verify-model','align-captions','splice-audio'):
            result = subprocess.run(['node', str(cli), command, '--python', sys.executable, '--help'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(importlib.util.find_spec('numpy') and importlib.util.find_spec('soundfile') and importlib.util.find_spec('pypinyin'), 'install requirements-voice-tools.txt for optional audio tests')
class VoiceTimingTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.sr = 8000
        self.audio = np.concatenate([.1*np.sin(2*np.pi*180*np.arange(8000)/8000), np.zeros(4000), .1*np.sin(2*np.pi*180*np.arange(8000)/8000)])
        self.spoken = ['春夏秋冬。','东南西北。']

    def report(self):
        from voice_support.alignment import align_audio
        report = align_audio(self.audio, self.sr, self.spoken)
        report['audio_sha256'] = 'a'*64
        return report

    def transcript(self):
        return dict(segments=[dict(start=0, end=1, text=self.spoken[0]),dict(start=1.5, end=2.5, text=self.spoken[1])],
                    prompt_used=False, audio_sha256='a'*64, audio_duration_seconds=2.5,
                    expected_text_sha256=hashlib.sha256(''.join(self.spoken).encode()).hexdigest())

    def test_semantic_support_and_stale_hash_rejection(self):
        from voice_support.semantic import support_boundaries
        report = support_boundaries(self.report(), self.transcript(), self.spoken)
        self.assertEqual(report['boundaries'][0]['semantic_confidence'], 'high')
        self.assertAlmostEqual(report['boundaries'][0]['time_seconds'], 1.25, delta=.02)
        self.assertTrue(report['requires_listening_review'])
        for key in ('audio_sha256','expected_text_sha256','audio_duration_seconds','prompt_used'):
            transcript = self.transcript(); transcript[key] = None
            with self.subTest(key=key), self.assertRaises((ValueError,TypeError)):
                support_boundaries(self.report(), transcript, self.spoken)

    def test_nonfinite_semantic_duration_is_refused(self):
        from voice_support.semantic import support_boundaries
        for duration in (float('nan'),float('inf'),True,-1):
            transcript = self.transcript(); transcript['audio_duration_seconds'] = duration
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                support_boundaries(self.report(),transcript,self.spoken)

    def test_phrase_internal_boundary_is_low_confidence(self):
        from voice_support.semantic import support_boundaries
        transcript = self.transcript(); transcript['segments'] = [dict(start=0,end=2.5,text=''.join(self.spoken))]
        report = support_boundaries(self.report(), transcript, self.spoken)
        self.assertEqual(report['boundaries'][0]['semantic_confidence'], 'low')
        self.assertEqual(report['overall_confidence'], 'low')
        self.assertTrue(report['asr_used'])

    def test_mocked_qwen_local_loading_and_wav(self):
        import numpy as np
        captured = {}
        model = SimpleNamespace()
        model.get_supported_speakers = lambda: ['serena']
        model.model = SimpleNamespace(talker=SimpleNamespace(register_forward_hook=lambda fn: SimpleNamespace(remove=lambda: None)))
        def generate(**kwargs):
            captured['generate'] = kwargs
            return [self.audio.astype(np.float32)], self.sr
        model.generate_custom_voice = generate
        def load(*args, **kwargs):
            captured['load'] = kwargs
            self.assertEqual(os.environ['ORT_DISABLE_TELEMETRY'], '1')
            return model
        torch = SimpleNamespace(float32='float32', bfloat16='bfloat16', set_num_threads=lambda n: None,
                                set_num_interop_threads=lambda n: None, manual_seed=lambda n: None, inference_mode=nullcontext)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root/'text.txt').write_text('Synthetic adapter test, not an actual inference.')
            args = SimpleNamespace(output=root/'out.wav',text_file=root/'text.txt',model_dir=root,threads=2,dtype='float32',seed=1,voice='Serena',language='Chinese',max_new_tokens=100)
            with patch.object(voice,'verify_model',return_value={'mocked_model':True}), patch.dict(sys.modules,{'torch':torch,'qwen_tts':SimpleNamespace(Qwen3TTSModel=SimpleNamespace(from_pretrained=load))}):
                report = voice.qwen(args)
            self.assertTrue(captured['load']['local_files_only'])
            self.assertFalse(captured['load']['trust_remote_code'])
            self.assertTrue(captured['load']['use_safetensors'])
            self.assertNotIn('instruct',captured['generate'])
            self.assertEqual(report['listening_review'],'required')
            self.assertTrue(args.output.is_file())
            with self.assertRaises(FileExistsError): voice.qwen(args)

    def test_mocked_whisper_is_unprompted_and_hash_bound(self):
        import soundfile as sf
        from scipy.signal import resample_poly  # Load compiled dependencies before patch.dict restores sys.modules.
        captured = {}; mutate = [False]
        def load(*args, **kwargs):
            self.assertTrue(kwargs['local_files_only']); self.assertFalse(kwargs['trust_remote_code'])
            return SimpleNamespace(to=lambda device: object())
        processor = SimpleNamespace(from_pretrained=lambda *a, **kw: SimpleNamespace(tokenizer=object(),feature_extractor=object()))
        def pipeline(*pipe_args, **kwargs):
            def runner(audio, **options):
                captured.update(options)
                if mutate[0]: sf.write(args.audio, self.audio[::-1]*.5, self.sr)
                return dict(text=''.join(self.spoken),chunks=[dict(text=text,timestamp=(i*1.5,min(2.5,i*1.5+1))) for i,text in enumerate(self.spoken)])
            return runner
        torch = SimpleNamespace(Tensor=type('MockTensor', (), {}),float32='float32',set_num_threads=lambda n:None,set_num_interop_threads=lambda n:None)
        transformers = SimpleNamespace(AutoProcessor=processor,AutoModelForSpeechSeq2Seq=SimpleNamespace(from_pretrained=load),pipeline=pipeline)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); sf.write(root/'audio.wav',self.audio,self.sr); (root/'expected.txt').write_text(''.join(self.spoken))
            args = SimpleNamespace(output=root/'asr.json',audio=root/'audio.wav',model_dir=root,threads=3,language='chinese',expected_text_file=root/'expected.txt')
            with patch.object(voice,'verify_model',return_value={'mocked_model':True}), patch.dict(sys.modules,{'torch':torch,'transformers':transformers}):
                result = voice.whisper(args)
            self.assertFalse(result['prompt_used'])
            self.assertEqual(result['audio_sha256'],voice.digest(args.audio))
            self.assertEqual(result['expected_text_sha256'],self.transcript()['expected_text_sha256'])
            self.assertNotIn('prompt_ids',captured['generate_kwargs'])
            self.assertNotIn('initial_prompt',captured['generate_kwargs'])
            mutate[0] = True; args.output = root/'stale-asr.json'
            with patch.object(voice,'verify_model',return_value={'mocked_model':True}), patch.dict(sys.modules,{'torch':torch,'transformers':transformers}):
                with self.assertRaisesRegex(ValueError, 'changed during recognition'):
                    voice.whisper(args)
            self.assertFalse(args.output.exists())

    def test_aligned_manifest_retimes_existing_renderer(self):
        import soundfile as sf
        from production import prepare_audio
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); sf.write(root/'scene.wav', self.audio, self.sr, subtype='PCM_24')
            story = dict(version=1,title='Synthetic timing fixture',scenes=[dict(title='Test',duration=4,layout='comparison',labels=['Before','After'],captions=self.spoken)])
            (root/'story.json').write_text(json.dumps(story)); (root/'audio.json').write_text(json.dumps(dict(mode='scene',clips=[dict(scene=0,wav='scene.wav')])))
            result = voice.align(root/'story.json',root/'audio.json',root/'aligned')
            self.assertFalse(result['forced_alignment'])
            report = prepare_audio(root/'story.json',root/'aligned/audio.json',root/'prepared')
            self.assertEqual(report['scenes'][0]['caption_timing'],'energy_pause_estimate')
            retimed = json.loads((root/'prepared/retimed.json').read_text())
            self.assertEqual(retimed['scenes'][0]['layout'],'comparison')
            self.assertEqual(len(retimed['scenes'][0]['caption_frames']),2)
            with self.assertRaises(FileExistsError): voice.align(root/'story.json',root/'audio.json',root/'aligned')
            transcript = self.transcript(); transcript['audio_sha256'] = voice.digest(root/'scene.wav')
            (root/'asr.json').write_text(json.dumps(transcript)); (root/'asr-scenes.json').write_text(json.dumps(dict(scenes=[dict(scene=0,transcript='asr.json')])))
            semantic = voice.align(root/'story.json',root/'audio.json',root/'semantic',root/'asr-scenes.json')
            self.assertEqual(semantic['caption_timing'],'semantic_pause_estimate')
            prepare_audio(root/'story.json',root/'semantic/audio.json',root/'semantic-prepared')
            # Same duration, different source bytes: old estimates must never be accepted.
            sf.write(root/'scene.wav',self.audio*.5,self.sr,subtype='PCM_24')
            with self.assertRaisesRegex(ValueError,'audio changed'):
                prepare_audio(root/'story.json',root/'aligned/audio.json',root/'stale-prepared')
            sf.write(root/'scene.wav',self.audio,self.sr,subtype='PCM_24')
            story['scenes'][0]['captions'][0] = 'Changed script.'
            (root/'story.json').write_text(json.dumps(story))
            with self.assertRaisesRegex(ValueError,'narration text changed'):
                prepare_audio(root/'story.json',root/'aligned/audio.json',root/'stale-text-prepared')


if __name__ == '__main__': unittest.main()
