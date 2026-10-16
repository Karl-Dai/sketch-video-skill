"""Synthetic-only tests; no project audio, models or network required."""
import os
os.environ['ORT_DISABLE_TELEMETRY']='1'
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import importlib.util
if not importlib.util.find_spec("numpy") or not importlib.util.find_spec("soundfile"):
    raise unittest.SkipTest("optional audio tests require requirements-voice-tools.txt")
import numpy as np
import soundfile as sf
from voice_support.splice_audio import splice_arrays,write_composite


class SpliceTests(unittest.TestCase):
    def setUp(self):
        self.sr=24000
        self.a=np.zeros(14400,dtype=np.float32)
        self.b=np.zeros(14400,dtype=np.float32)
        self.a[:9600]=0.1*np.sin(2*np.pi*440*np.arange(9600)/self.sr)
        self.b[4800:]=0.1*np.sin(2*np.pi*660*np.arange(9600)/self.sr)

    def test_silence_join_preserves_length_and_inputs(self):
        original_a=self.a.copy();original_b=self.b.copy()
        out,meta=splice_arrays(self.a,self.sr,0.5,self.b,self.sr,0.1)
        self.assertEqual(len(out),24000)
        self.assertEqual(meta['join_sample_jump'],0)
        self.assertEqual(meta['inserted_silence_samples'],0)
        np.testing.assert_array_equal(self.a,original_a)
        np.testing.assert_array_equal(self.b,original_b)
        np.testing.assert_array_equal(out[:11952],self.a[:11952])
        np.testing.assert_array_equal(out[12048:],self.b[2448:])

    def test_refuses_non_silent_join(self):
        with self.assertRaises(ValueError):
            splice_arrays(self.a,self.sr,0.2,self.b,self.sr,0.3)

    def test_refuses_rate_mismatch(self):
        with self.assertRaises(ValueError):
            splice_arrays(self.a,24000,0.5,self.b,16000,0.1)

    def test_refuses_invalid_rate_and_threshold(self):
        for rate in (True, 24000.5):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                splice_arrays(self.a,rate,0.5,self.b,rate,0.1)
        with self.assertRaises(ValueError):
            splice_arrays(self.a,self.sr,0.5,self.b,self.sr,0.1,max_join_rms_dbfs=float('nan'))

    def test_refuses_nonfinite(self):
        self.a[1]=np.nan
        with self.assertRaises(ValueError):
            splice_arrays(self.a,self.sr,0.5,self.b,self.sr,0.1)

    def test_refuses_outside_cut(self):
        with self.assertRaises(ValueError):
            splice_arrays(self.a,self.sr,0.7,self.b,self.sr,0.1)

    def test_pcm_file_round_trip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);a=folder/'a.wav';b=folder/'b.wav';out=folder/'out.wav'
            sf.write(a,self.a,self.sr,subtype='PCM_24')
            sf.write(b,self.b,self.sr,subtype='PCM_24')
            meta=write_composite(a,b,0.5,0.1,out)
            x,sr=sf.read(out,dtype='float32')
            self.assertEqual(len(x),24000);self.assertEqual(sr,self.sr)
            self.assertTrue(meta['composite']);self.assertEqual(len(meta['output_sha256']),64)
            with self.assertRaises(FileExistsError):write_composite(a,b,0.5,0.1,out)
            with self.assertRaises(ValueError):write_composite(a,b,0.5,0.1,a)


if __name__=='__main__':
    unittest.main()
