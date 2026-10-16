"""Deterministic signal tests; these do not validate spoken-word correspondence."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import importlib.util
if not importlib.util.find_spec("numpy") or not importlib.util.find_spec("soundfile"):
    raise unittest.SkipTest("optional audio tests require requirements-voice-tools.txt")
import numpy as np

from voice_support.alignment import AlignmentConfig, Caption, align_audio, align_file, captions_from_scene
from voice_support.alignment.pause_align import _features, _srt_time, text_weight


SR = 8000


def signal(parts, consonant_gaps=False):
    """parts is (duration, speech_bool). Speech is a deterministic 180-Hz tone."""
    output = []
    for duration, speech in parts:
        samples = round(duration * SR)
        x = 0.15 * np.sin(np.arange(samples) * 2 * np.pi * 180 / SR) if speech else np.zeros(samples)
        if speech and consonant_gaps:
            for t in np.arange(0.2, duration, 0.24):
                x[round(t * SR):round((t + 0.035) * SR)] = 0
        output.append(x)
    return np.concatenate(output)


class AlignmentTests(unittest.TestCase):
    def assert_chronological(self, result, count):
        self.assertEqual(len(result["captions"]), count)
        self.assertEqual(result["captions"][0]["start_seconds"], 0)
        self.assertAlmostEqual(result["captions"][-1]["end_seconds"], result["duration_seconds"])
        previous = 0
        for caption in result["captions"]:
            self.assertEqual(caption["start_seconds"], previous)
            self.assertGreater(caption["duration_seconds"], 0)
            self.assertGreater(caption["end_seconds"], caption["start_seconds"])
            previous = caption["end_seconds"]
        json.dumps(result, allow_nan=False)

    def test_three_clean_phrases_and_consonant_gaps(self):
        x = signal([(0.2, False), (1.0, True), (0.5, False), (1.0, True),
                    (0.6, False), (1.0, True), (0.3, False)], consonant_gaps=True)
        result = align_audio(x, SR, ["春夏秋冬。", "东南西北。", "日月星辰。"])
        self.assert_chronological(result, 3)
        self.assertAlmostEqual(result["boundaries"][0]["time_seconds"], 1.45, delta=0.03)
        self.assertAlmostEqual(result["boundaries"][1]["time_seconds"], 3.0, delta=0.03)
        self.assertEqual(len(result["vad"]["pauses"]), 2)
        self.assertTrue(all(b["source"] == "energy_pause_midpoint" for b in result["boundaries"]))

    def test_internal_full_stop_does_not_add_caption_boundary(self):
        x = signal([(1, True), (0.6, False), (1, True), (0.6, False),
                    (1, True), (0.6, False), (1, True)])
        result = align_audio(x, SR, ["春夏秋冬。", "东南西北。日月星辰。", "山川河流。"])
        self.assert_chronological(result, 3)
        self.assertEqual(result["punctuation_unit_count"], 4)
        self.assertAlmostEqual(result["boundaries"][0]["time_seconds"], 1.3, delta=0.03)
        self.assertAlmostEqual(result["boundaries"][1]["time_seconds"], 4.5, delta=0.03)

    def test_no_pauses_is_explicitly_low_confidence(self):
        x = signal([(4.0, True)], consonant_gaps=True)
        result = align_audio(x, SR, ["春夏秋冬。", "东南西北。"])
        self.assert_chronological(result, 2)
        self.assertEqual(result["vad"]["pauses"], [])
        self.assertEqual(result["overall_confidence"], "low")
        self.assertTrue(result["boundaries"][0]["ambiguous"])
        self.assertEqual(result["boundaries"][0]["source"], "text_weight_fallback")

    def test_one_caption_covers_audio(self):
        x = signal([(0.2, False), (1, True), (0.4, False)])
        result = align_audio(x, SR, ["春夏秋冬。"])
        self.assert_chronological(result, 1)
        self.assertEqual(result["boundaries"], [])
        self.assertEqual(result["overall_confidence"], "not_applicable")
        self.assertAlmostEqual(result["speech_like_window_seconds"][0], 0.2, delta=0.02)
        self.assertAlmostEqual(result["speech_like_window_seconds"][1], 1.2, delta=0.02)

    def test_gain_invariance(self):
        x = signal([(1, True), (0.5, False), (1, True)])
        a = align_audio(x, SR, ["春夏秋冬。", "东南西北。"])
        b = align_audio(x * 0.1, SR, ["春夏秋冬。", "东南西北。"])
        self.assertEqual(a["captions"], b["captions"])
        self.assertAlmostEqual(a["vad"]["threshold_dbfs"] - b["vad"]["threshold_dbfs"], 20, places=4)

    def test_antiphase_stereo_does_not_cancel(self):
        x = signal([(1, True), (0.5, False), (1, True)])
        mono = align_audio(x, SR, ["春夏秋冬。", "东南西北。"])
        stereo = align_audio(np.stack([x, -x], axis=1), SR, ["春夏秋冬。", "东南西北。"])
        self.assertEqual(mono["captions"], stereo["captions"])

    def test_weighted_global_path_ignores_unrelated_long_pause(self):
        x = signal([(1, True), (0.9, False), (3, True), (0.45, False), (1, True)])
        result = align_audio(x, SR, ["春夏，秋冬东南西北日月星辰山川。", "大江大河。"])
        self.assert_chronological(result, 2)
        self.assertAlmostEqual(result["boundaries"][0]["time_seconds"], 5.125, delta=0.04)

    def test_display_and_spoken_text_separate(self):
        x = signal([(1, True), (0.5, False), (1, True)])
        result = align_audio(x, SR, [Caption("1950 年。", "一九五零。", 7),
                                    {"text": "2025 年。", "spoken_text": "二零二五。", "id": 8}])
        self.assertEqual(result["captions"][0]["text"], "1950 年。")
        self.assertEqual(result["captions"][0]["id"], 7)
        self.assertFalse(any("Digits remain" in w for w in result["warnings"]))

    def test_text_weights(self):
        self.assertEqual(text_weight("今天 AI，测试。"), 6)
        self.assertEqual(text_weight("S D K"), 3)
        self.assertEqual(text_weight("。！？"), 0)
        self.assertEqual(text_weight("transformer"), 3)

    def test_scene_normalization_adapter(self):
        # Generic, self-contained fixture: dates, spelled acronyms, and an
        # internal sentence boundary must preserve caption display boundaries.
        scene = {
            "captions": ["2025 年，SDK 更新。版本发布后再检查。", "API 可以读数据。"],
            "caption_ids": [10, 11],
            "script": "2025 年，SDK 更新。版本发布后再检查。API 可以读数据。",
            "spoken_text": "二零二五年，S D K 更新。版本发布后再检查。A P I 可以读数据。",
        }
        captions = captions_from_scene(scene)
        self.assertEqual("".join(c["spoken_text"] for c in captions), scene["spoken_text"])
        self.assertEqual([c["text"] for c in captions], scene["captions"])
        self.assertEqual([c["id"] for c in captions], [10, 11])
        self.assertEqual(captions[0]["spoken_text"], "二零二五年，S D K 更新。版本发布后再检查。")
        modified = dict(scene, spoken_text=scene["spoken_text"].replace("。", "！", 1))
        with self.assertRaisesRegex(ValueError, "punctuation order"):
            captions_from_scene(modified)

    def test_invalid_input_is_rejected(self):
        inputs = [([], SR, ["甲"]), (np.zeros(8000), SR, ["甲"]),
                  (np.ones(8000), 0, ["甲"]), (np.ones(8000), SR, []),
                  (np.ones(8000), SR, ["。"]), (np.ones(8000), SR, "甲"),
                  (np.ones(8000), SR, {"captions": ["甲。", "乙。"]}),
                  (np.ones(8000), SR, {"text": "甲。", "spoken_text": "甲。"}),
                  (np.full(8000, np.nan), SR, ["甲"]),
                  (np.ones((8000, 0)), SR, ["甲"])]
        for x, sr, captions in inputs:
            with self.subTest(sr=sr, captions=captions):
                with self.assertRaises(ValueError):
                    align_audio(x, sr, captions)
        with self.assertRaises(ValueError):
            align_audio(np.ones(8000), SR, ["甲"], AlignmentConfig(hop_seconds=0))
        with self.assertRaises(ValueError):
            align_audio(np.ones(80), SR, ["甲", "乙"])

    def test_very_short_file_has_valid_features(self):
        # Framing a shorter-than-window file must not index outside the signal.
        features = _features(np.ones(80), SR, AlignmentConfig(remove_bursts_seconds=0))
        self.assertAlmostEqual(features["duration"], 0.01)

    def test_feasible_caption_minimum_is_enforced_inside_dp(self):
        result = align_audio(signal([(1, True)]), SR, ["甲", "乙" * 100])
        self.assert_chronological(result, 2)
        self.assertGreaterEqual(result["captions"][0]["duration_seconds"], 0.12)
        self.assertAlmostEqual(result["captions"][0]["end_seconds"], 0.129901, places=5)

    def test_caption_minimum_is_not_applied_to_each_internal_clause(self):
        result = align_audio(signal([(1, True)]), SR, ["甲，乙，丙。", "丁" * 10],
                             AlignmentConfig(min_caption_seconds=0.25))
        self.assert_chronological(result, 2)
        self.assertGreaterEqual(result["captions"][0]["duration_seconds"], 0.25)

    def test_silence_dominated_file_does_not_mark_silence_as_speech(self):
        x = signal([(20, False), (1, True), (20, False)])
        result = align_audio(x, SR, ["春夏秋冬。"])
        self.assert_chronological(result, 1)
        self.assertAlmostEqual(result["speech_like_window_seconds"][0], 20, delta=0.02)
        self.assertAlmostEqual(result["speech_like_window_seconds"][1], 21, delta=0.02)
        self.assertAlmostEqual(result["speech_like_energy_seconds"], 1, delta=0.03)
        self.assertTrue(result["vad"]["used_sparse_signal_reference"])

    def test_millisecond_srt_rollover(self):
        self.assertEqual(_srt_time(59.9999), "00:01:00,000")
        self.assertEqual(_srt_time(3600.025), "01:00:00,025")

    def test_sample_pause_evidence_regression(self):
        root = Path(__file__).resolve().parents[1]
        audio_path = root / "qwen_serena_sample_raw.wav"
        caption_path = root / "alignment" / "sample_captions.json"
        if not audio_path.is_file() or not caption_path.is_file():
            self.skipTest("Optional local audition audio/JSON fixtures are absent; generated media is not bundled.")
        captions = json.loads(caption_path.read_text(encoding="utf-8"))
        result = align_file(audio_path, captions)
        self.assert_chronological(result, 3)
        self.assertFalse(result["asr_used"])
        self.assertFalse(result["word_level_alignment"])
        self.assertTrue(result["requires_listening_review"])
        self.assertAlmostEqual(result["boundaries"][0]["time_seconds"], 4.205, delta=0.03)
        self.assertAlmostEqual(result["boundaries"][1]["time_seconds"], 10.610, delta=0.03)
        self.assertTrue(all(b["threshold_sensitivity_max_shift_seconds"] <= 0.05 for b in result["boundaries"]))


if __name__ == "__main__":
    unittest.main()
