"""Small exhaustive regressions for the nested caption/clause dynamic program.

These tests check optimization and marginals, not spoken-word correspondence.
They create deterministic signals in memory and never write media files.
"""

from __future__ import annotations

from pathlib import Path
import itertools
import math
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import importlib.util
if not importlib.util.find_spec("numpy") or not importlib.util.find_spec("soundfile"):
    raise unittest.SkipTest("optional audio tests require requirements-voice-tools.txt")
import numpy as np

from voice_support.alignment import AlignmentConfig
from voice_support.alignment.pause_align import _captions, _features, _mass_at, _solve, _units


SR = 8000


def _signal(parts):
    chunks = []
    for duration, active in parts:
        n = round(duration * SR)
        chunks.append(0.15 * np.sin(np.arange(n) * 2 * np.pi * 180 / SR)
                      if active else np.zeros(n))
    return np.concatenate(chunks)


def _huber_scalar(value):
    value = abs(float(value))
    return 0.5 * value * value if value <= 1 else value - 0.5


def _enumerate_paths(features, units, layers, config):
    """Score every candidate combination directly, without either DP."""
    weights = np.array([unit.weight for unit in units])
    expected = features["active_seconds"] * weights / weights.sum()
    cumulative = np.cumsum(expected)
    paths = []
    for middle in itertools.product(*(range(len(layer)) for layer in layers[1:-1])):
        path = (0,) + middle + (0,)
        times = [layer[index].time for layer, index in zip(layers, path)]
        caption_times = ([0.0] +
                         [times[i + 1] for i, unit in enumerate(units[:-1])
                          if unit.caption_end] + [features["duration"]])
        if any(right - left < config.min_caption_seconds - 1e-9
               for left, right in zip(caption_times, caption_times[1:])):
            continue
        cost = 0.0
        for i, unit in enumerate(units):
            mass = float(_mass_at(features, times[i + 1]) -
                         _mass_at(features, times[i]))
            if (times[i + 1] - times[i] < config.min_unit_seconds - 1e-9 or
                    mass < min(0.03, expected[i] * 0.15)):
                break
            cost += 0.85 * _huber_scalar((mass - expected[i]) /
                                          max(0.12, expected[i] * 0.30))
            if i < len(units) - 1:
                candidate = layers[i + 1][path[i + 1]]
                prior_error = (float(_mass_at(features, candidate.time)) - cumulative[i])
                prior_error /= max(0.35, features["active_seconds"] * 0.065)
                acoustic = 0.45 + 2.2 * unit.strength
                if candidate.pause_index is not None:
                    pause = features["pauses"][candidate.pause_index]
                    acoustic *= 1 - min(1.0, pause.duration / (0.16 + 0.34 * unit.strength))
                cost += 0.35 * _huber_scalar(prior_error) + acoustic
        else:
            paths.append((cost, path))
    return paths


class ExactDynamicProgramTests(unittest.TestCase):
    def assert_matches_exhaustive(self, parts, captions, minimum=0.12):
        config = AlignmentConfig(min_caption_seconds=minimum, sensitivity_db=0)
        features = _features(_signal(parts), SR, config)
        units = _units(_captions(captions))
        solution = _solve(features, units, config)
        paths = _enumerate_paths(features, units, solution["layers"], config)
        self.assertTrue(paths)
        best = min(cost for cost, _ in paths)
        self.assertAlmostEqual(solution["cost"], best, places=9)
        selected = [cost for cost, path in paths if path == tuple(solution["chosen"])]
        self.assertEqual(len(selected), 1)
        self.assertAlmostEqual(selected[0], best, places=9)
        for layer_index, unit in enumerate(units[:-1], 1):
            if not unit.caption_end:
                continue
            marginals = solution["forward"][layer_index] + solution["backward"][layer_index]
            for candidate_index, marginal in enumerate(marginals):
                exhaustive = min((cost for cost, path in paths
                                  if path[layer_index] == candidate_index), default=math.inf)
                if math.isinf(exhaustive):
                    self.assertEqual(marginal, math.inf)
                else:
                    self.assertAlmostEqual(marginal, exhaustive, places=9)

    def test_duration_constraints_and_outer_quiet(self):
        cases = [
            ([(1.0, True)], ["甲", "乙" * 100], 0.12),
            ([(1.0, True)], ["甲，乙，丙。", "丁" * 10], 0.25),
            ([(0.5, False), (0.2, True), (0.2, False), (0.2, True), (0.5, False)],
             ["甲。", "乙。"], 0.45),
            ([(0.6, True), (0.3, False), (0.6, True), (0.3, False),
              (0.6, True), (0.3, False), (0.6, True)],
             ["甲甲。", "乙乙，丙丙。", "丁丁。"], 0.3),
        ]
        for index, (parts, captions, minimum) in enumerate(cases):
            with self.subTest(case=index):
                self.assert_matches_exhaustive(parts, captions, minimum)

    def test_seeded_small_candidate_graphs(self):
        rng = np.random.default_rng(431)
        for trial in range(6):
            unit_count = int(rng.integers(3, 5))
            split = int(rng.integers(1, unit_count))
            captions = [
                "，".join("甲" * int(rng.integers(1, 9)) for _ in range(split)) + "。",
                "，".join("乙" * int(rng.integers(1, 9))
                         for _ in range(unit_count - split)) + "。",
            ]
            parts = [(0.1, False)]
            for _ in range(unit_count):
                parts += [(float(rng.uniform(0.15, 0.7)), True),
                          (float(rng.uniform(0.05, 0.5)), False)]
            minimum = float(rng.choice([0.12, 0.3, 0.6]))
            with self.subTest(trial=trial):
                self.assert_matches_exhaustive(parts, captions, minimum)


if __name__ == "__main__":
    unittest.main()
