"""Estimate caption timing from text weights and energy pauses, without ASR.

The dynamic program matches *all* punctuation-delimited clauses, including
punctuation inside a caption. Only requested caption ends become subtitles.
Acoustic candidates must survive a minimum-duration gate; fallback candidates
keep the optimization feasible when a narrator does not pause at punctuation.
Neither the confidence score nor the uncertainty interval is statistical.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
import json
import math
from pathlib import Path
import re
from typing import Any, Sequence
import unicodedata

import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class AlignmentConfig:
    frame_seconds: float = 0.030
    hop_seconds: float = 0.010
    threshold_db: float | None = None
    relative_threshold_db: float = 24.0
    close_silences_seconds: float = 0.070
    remove_bursts_seconds: float = 0.040
    min_pause_seconds: float = 0.150
    min_unit_seconds: float = 0.040
    min_caption_seconds: float = 0.120
    sensitivity_db: float = 3.0
    alternative_cost_window: float = 2.0

    def validate(self) -> None:
        values = asdict(self)
        for key, value in values.items():
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{key} must be finite")
        for key in ("frame_seconds", "hop_seconds", "relative_threshold_db",
                    "min_pause_seconds", "min_unit_seconds",
                    "min_caption_seconds", "alternative_cost_window"):
            if values[key] <= 0:
                raise ValueError(f"{key} must be positive")
        for key in ("close_silences_seconds", "remove_bursts_seconds", "sensitivity_db"):
            if values[key] < 0:
                raise ValueError(f"{key} must be nonnegative")
        if self.frame_seconds < self.hop_seconds:
            raise ValueError("frame_seconds must be at least hop_seconds")


@dataclass(frozen=True)
class Caption:
    text: str
    spoken_text: str | None = None
    id: Any = None


@dataclass(frozen=True)
class _Unit:
    caption_index: int
    text: str
    weight: float
    strength: float
    caption_end: bool


@dataclass(frozen=True)
class _Pause:
    start: float
    end: float

    @property
    def midpoint(self) -> float:
        return (self.start + self.end) / 2

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class _Candidate:
    time: float
    pause_index: int | None = None


_PUNCTUATION = re.compile(r"([^，、。！？；：,.!?;:]+)([，、。！？；：,.!?;:]*)")
_TOKENS = re.compile(r"[A-Za-z]+|\d+|[^\W_]", re.UNICODE)


def text_weight(text: str) -> float:
    """Approximate spoken duration units, not phonemes or recognized words.

    CJK characters count as one; uppercase abbreviations count by letter;
    other Latin words use vowel groups. Supply normalized spoken_text for
    years, abbreviations and mathematical expressions where possible.
    """
    weight = 0.0
    for token in _TOKENS.findall(text):
        if token.isascii() and token.isalpha():
            if token.isupper() and len(token) <= 6:
                weight += len(token)
            else:
                weight += max(1, len(re.findall(r"[aeiouy]+", token.lower())))
        elif token.isdigit():
            weight += len(token)
        elif unicodedata.category(token[0])[0] in "LN":
            weight += 1
    return weight


def _captions(values: Sequence[str | Caption | dict[str, Any]]) -> list[Caption]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise ValueError("captions must be a nonempty sequence of caption blocks")
    result = []
    for index, value in enumerate(values):
        if isinstance(value, Caption):
            caption = value
        elif isinstance(value, str):
            caption = Caption(value)
        elif isinstance(value, dict):
            caption = Caption(value.get("text", ""), value.get("spoken_text"), value.get("id"))
        else:
            raise ValueError(f"caption {index} must be a string, Caption or dict")
        if not isinstance(caption.text, str) or not caption.text.strip():
            raise ValueError(f"caption {index} has no display text")
        spoken = caption.spoken_text if caption.spoken_text is not None else caption.text
        if not isinstance(spoken, str) or text_weight(spoken) <= 0:
            raise ValueError(f"caption {index} has no usable spoken text")
        result.append(caption)
    return result


def _units(captions: list[Caption]) -> list[_Unit]:
    result = []
    for index, caption in enumerate(captions):
        spoken = caption.spoken_text if caption.spoken_text is not None else caption.text
        units = []
        for match in _PUNCTUATION.finditer(spoken):
            content, punctuation = match.groups()
            weight = text_weight(content)
            if weight <= 0:
                continue
            strength = (1.0 if any(p in punctuation for p in "。！？.!?") else
                        0.70 if any(p in punctuation for p in "；;：:") else
                        0.45 if any(p in punctuation for p in "，,") else
                        0.20 if "、" in punctuation else 0.0)
            units.append(_Unit(index, match.group().strip(), weight, strength, False))
        units[-1] = replace(units[-1], caption_end=True)
        result.extend(units)
    return result


def _runs(mask: np.ndarray):
    changes = np.diff(np.r_[False, mask, False].astype(np.int8))
    return zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1))


def _features(audio: np.ndarray, sample_rate: int, cfg: AlignmentConfig) -> dict:
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim not in (1, 2) or not len(x) or (x.ndim == 2 and not x.shape[1]):
        raise ValueError("audio must be nonempty mono or samples-by-channels audio")
    if not isinstance(sample_rate, (int, np.integer)) or sample_rate < 100:
        raise ValueError("sample_rate must be an integer of at least 100 Hz")
    if not np.isfinite(x).all():
        raise ValueError("audio contains non-finite values")
    # Channel energy pooling avoids cancellation of antiphase stereo speech.
    power = x * x if x.ndim == 1 else np.mean(x * x, axis=1)
    if float(np.max(power)) < 1e-18:
        raise ValueError("audio has no detectable signal; cannot estimate caption timing")
    count = len(x)
    hop = max(1, round(cfg.hop_seconds * sample_rate))
    frame = max(hop, round(cfg.frame_seconds * sample_rate))
    edges_samples = np.r_[np.arange(0, count, hop), count]
    centers = (edges_samples[:-1] + edges_samples[1:]) // 2
    left = np.maximum(0, centers - frame // 2)
    right = np.minimum(count, centers + (frame + 1) // 2)
    prefix = np.r_[0.0, np.cumsum(power)]
    rms = np.sqrt(np.maximum(0, prefix[right] - prefix[left]) / (right - left))
    db = 20 * np.log10(np.maximum(rms, 1e-12))
    p10, p95 = np.percentile(db, [10, 95])
    # A clip with >95% silence can put both quantiles at the numerical floor.
    # In that case derive the reference from actual non-floor signal frames.
    reference = float(p95)
    sparse_signal = p95 < float(np.max(db)) - 40.0
    if sparse_signal:
        reference = float(np.percentile(db[db >= float(np.max(db)) - 40.0], 95))
    threshold = (float(cfg.threshold_db) if cfg.threshold_db is not None else
                 float(min(reference - 14.0, max(reference - cfg.relative_threshold_db, p10 + 6.0))))
    speech = (db >= threshold) & (rms > 1e-12)
    edges = edges_samples / sample_rate
    # Remove tiny high-energy blips; then bridge short consonant-level gaps.
    for start, end in list(_runs(speech)):
        if edges[end] - edges[start] < cfg.remove_bursts_seconds:
            speech[start:end] = False
    for start, end in list(_runs(~speech)):
        if start > 0 and end < len(speech) and edges[end] - edges[start] <= cfg.close_silences_seconds:
            speech[start:end] = True
    active = np.flatnonzero(speech)
    if not len(active):
        raise ValueError("no speech-like energy remains at this threshold")
    speech_start, speech_end = float(edges[active[0]]), float(edges[active[-1] + 1])
    pauses = [_Pause(float(edges[a]), float(edges[b])) for a, b in _runs(~speech)
              if a > active[0] and b <= active[-1] and
              edges[b] - edges[a] >= cfg.min_pause_seconds - 1e-9]
    mass = np.r_[0.0, np.cumsum(np.diff(edges) * speech)]
    return dict(duration=count / sample_rate, edges=edges, mass=mass, pauses=pauses,
                start=speech_start, end=speech_end, threshold=threshold,
                energy_range_db=float(reference - p10), global_energy_range_db=float(p95 - p10),
                reference_level_db=reference, sparse_reference=sparse_signal,
                active_seconds=float(mass[-1]))


def _mass_at(features: dict, time):
    return np.interp(time, features["edges"], features["mass"])


def _time_at_mass(features: dict, amount: float) -> float:
    # A flat mass interval is a pause. Its midpoint is a neutral visual cut.
    masses, edges = features["mass"], features["edges"]
    matches = np.flatnonzero(np.isclose(masses, amount, rtol=0, atol=1e-9))
    if len(matches):
        return float((edges[matches[0]] + edges[matches[-1]]) / 2)
    return float(np.interp(amount, masses, edges))


def _huber(value):
    value = np.abs(value)
    return np.where(value <= 1.0, 0.5 * value * value, value - 0.5)


def _solve(features: dict, units: list[_Unit], cfg: AlignmentConfig) -> dict:
    start, end = features["start"], features["end"]
    weights = np.array([unit.weight for unit in units])
    expected = features["active_seconds"] * weights / weights.sum()
    cumulative = np.cumsum(expected)
    priors = [_time_at_mass(features, float(value)) for value in cumulative[:-1]]
    layers: list[list[_Candidate]] = [[_Candidate(start)]]
    node_costs = [np.zeros(1)]
    global_sigma = max(0.35, features["active_seconds"] * 0.065)
    for i, prior in enumerate(priors):
        # All plausible acoustic pauses remain available to the global path.
        # Fallbacks are sampled in speech-mass space, not inside a long silence.
        window = max(1.5, 0.24 * (end - start))
        candidates = [_Candidate(p.midpoint, j) for j, p in enumerate(features["pauses"])
                      if abs(p.midpoint - prior) <= window]
        spread = max(0.12, min(0.6, expected[i] * 0.3))
        for offset in (-spread, -spread / 2, 0, spread / 2, spread):
            target = min(features["active_seconds"], max(0.0, cumulative[i] + offset))
            time = _time_at_mass(features, float(target))
            # A fallback inside an identified pause uses that pause's midpoint.
            matching = next((j for j, p in enumerate(features["pauses"])
                             if p.start <= time <= p.end), None)
            if matching is not None:
                time = features["pauses"][matching].midpoint
            candidates.append(_Candidate(time, matching))
        unique = {round(c.time, 7): c for c in candidates
                  if start + cfg.min_unit_seconds <= c.time <= end - cfg.min_unit_seconds}
        layer = sorted(unique.values(), key=lambda c: c.time)
        if not layer:
            raise ValueError("audio is too short for the punctuation units")
        costs = []
        for candidate in layer:
            prior_error = (_mass_at(features, candidate.time) - cumulative[i]) / global_sigma
            strength = units[i].strength
            if candidate.pause_index is None:
                acoustic_cost = 0.45 + 2.2 * strength
            else:
                pause = features["pauses"][candidate.pause_index]
                ideal_pause = 0.16 + 0.34 * strength
                support = min(1.0, pause.duration / ideal_pause)
                acoustic_cost = (1 - support) * (0.45 + 2.2 * strength)
            costs.append(float(0.35 * _huber(prior_error) + acoustic_cost))
        layers.append(layer)
        node_costs.append(np.array(costs))
    layers.append([_Candidate(end)])
    node_costs.append(np.zeros(1))

    # Each transition accounts for one clause's duration and lexical weight.
    # Requiring positive speech mass stops one pause absorbing two clauses.
    transitions = []
    for i in range(len(units)):
        left = np.array([c.time for c in layers[i]])
        right = np.array([c.time for c in layers[i + 1]])
        elapsed = right[None, :] - left[:, None]
        actual = _mass_at(features, right)[None, :] - _mass_at(features, left)[:, None]
        sigma = max(0.12, expected[i] * 0.30)
        transition = 0.85 * _huber((actual - expected[i]) / sigma)
        valid = (elapsed >= cfg.min_unit_seconds - 1e-9) & (actual >= min(0.03, expected[i] * 0.15))
        transition = np.where(valid, transition, np.inf)
        transitions.append(transition)

    # Solve each caption's latent clauses conditioned on every possible caption
    # start/end pair, then run a second DP across captions. This enforces true
    # caption minima without incorrectly imposing that minimum on every clause.
    # Outer display duration includes leading/trailing silence, as the API does.
    caption_layers = [0] + [i + 1 for i, unit in enumerate(units) if unit.caption_end]
    caption_costs = []
    clause_parents = []
    for left_layer, right_layer in zip(caption_layers, caption_layers[1:]):
        start_count = len(layers[left_layer])
        costs = np.full((start_count, start_count), np.inf)
        np.fill_diagonal(costs, 0.0)
        parents = []
        for i in range(left_layer, right_layer):
            options = costs[:, :, None] + transitions[i][None, :, :]
            parents.append(np.argmin(options, axis=1))
            costs = np.min(options, axis=1) + node_costs[i + 1][None, :]
        left_times = np.array([c.time for c in layers[left_layer]])
        right_times = np.array([c.time for c in layers[right_layer]])
        if left_layer == 0:
            left_times[:] = 0.0
        if right_layer == len(units):
            right_times[:] = features["duration"]
        caption_duration = right_times[None, :] - left_times[:, None]
        costs = np.where(caption_duration >= cfg.min_caption_seconds - 1e-9, costs, np.inf)
        caption_costs.append(costs)
        clause_parents.append(parents)

    outer_forward = [np.zeros(1)]
    outer_parents = []
    for costs in caption_costs:
        options = outer_forward[-1][:, None] + costs
        outer_parents.append(np.argmin(options, axis=0))
        outer_forward.append(np.min(options, axis=0))
    best_cost = float(outer_forward[-1][0])
    if not math.isfinite(best_cost):
        raise ValueError("no chronological alignment satisfies duration minima; use fewer captions/clauses or longer audio")
    outer_chosen = [0] * len(caption_layers)
    for i in range(len(caption_costs) - 1, -1, -1):
        outer_chosen[i] = int(outer_parents[i][outer_chosen[i + 1]])
    chosen = [0] * len(layers)
    for block_index, (left_layer, right_layer) in enumerate(zip(caption_layers, caption_layers[1:])):
        start_index = outer_chosen[block_index]
        chosen[right_layer] = outer_chosen[block_index + 1]
        for i in range(right_layer - 1, left_layer - 1, -1):
            chosen[i] = int(clause_parents[block_index][i - left_layer][start_index, chosen[i + 1]])
    outer_backward = [None] * len(caption_layers)
    outer_backward[-1] = np.zeros(1)
    for i in range(len(caption_costs) - 1, -1, -1):
        outer_backward[i] = np.min(caption_costs[i] + outer_backward[i + 1][None, :], axis=1)
    # Boundary marginals are needed only at caption boundaries, never words.
    forward = [None] * len(layers)
    backward = [None] * len(layers)
    for i, layer in enumerate(caption_layers):
        forward[layer] = outer_forward[i]
        backward[layer] = outer_backward[i]
    return dict(layers=layers, chosen=chosen, forward=forward, backward=backward,
                cost=best_cost, priors=priors, expected=expected)


def _round(value: float) -> float:
    return round(float(value), 6)


def align_audio(audio: np.ndarray, sample_rate: int,
                captions: Sequence[str | Caption | dict[str, Any]],
                config: AlignmentConfig | None = None) -> dict[str, Any]:
    """Return contiguous scene-local subtitle estimates and diagnostic evidence.

    Audio is read only. Captions cover the whole input, including leading and
    trailing quiet; internal cuts use pause midpoints. Supply one scene at a
    time, with matching spoken text in order. Text/audio mismatch is undetectable
    here. Review all results against listening before any final video render.
    """
    cfg = config or AlignmentConfig()
    cfg.validate()
    caption_list = _captions(captions)
    units = _units(caption_list)
    features = _features(audio, sample_rate, cfg)
    if features["duration"] < len(caption_list) * cfg.min_caption_seconds:
        raise ValueError("audio is too short for minimum positive caption durations")
    solution = _solve(features, units, cfg)
    boundary_layers = [i + 1 for i, unit in enumerate(units[:-1]) if unit.caption_end]
    warnings = ["Energy/punctuation timing estimate only: no ASR, transcript verification or word-level alignment.",
                "Confidence scores and ranges are heuristic, not calibrated probabilities or confidence intervals."]
    if any(re.search(r"\d", c.spoken_text if c.spoken_text is not None else c.text)
           for c in caption_list):
        warnings.append("Digits remain in spoken text; normalize the actual pronunciation for more reliable duration weights.")
    if features["energy_range_db"] < 12:
        warnings.append("Low energy contrast: background sound or compressed audio may defeat the pause detector.")
    if not features["pauses"]:
        warnings.append("No qualifying internal pauses found; boundaries rely on text-duration estimates.")

    variants = []
    sensitivity_failures = []
    if cfg.sensitivity_db > 0:
        for delta in (-cfg.sensitivity_db, cfg.sensitivity_db):
            try:
                varied = _features(audio, sample_rate, replace(cfg, threshold_db=features["threshold"] + delta))
                solved = _solve(varied, units, cfg)
                variants.append({layer: solved["layers"][layer][solved["chosen"][layer]].time
                                 for layer in boundary_layers})
            except ValueError as error:
                sensitivity_failures.append({"threshold_delta_db": delta, "error": str(error)})
    if sensitivity_failures:
        warnings.append("At least one threshold sensitivity rerun failed; review the timing manually.")

    boundaries = []
    for layer_index in boundary_layers:
        layer = solution["layers"][layer_index]
        selected = layer[solution["chosen"][layer_index]]
        pause = features["pauses"][selected.pause_index] if selected.pause_index is not None else None
        totals = solution["forward"][layer_index] + solution["backward"][layer_index]
        excess = np.maximum(0, totals - solution["cost"])
        different = [i for i, c in enumerate(layer) if abs(c.time - selected.time) > 0.20 and
                     (pause is None or c.pause_index != selected.pause_index)]
        margin = min((float(excess[i]) for i in different), default=math.inf)
        plausible = [c.time for c, cost in zip(layer, excess) if cost <= cfg.alternative_cost_window]
        varied_times = [variant[layer_index] for variant in variants]
        all_times = [selected.time] + plausible + varied_times
        # The whole detected pause is valid for a visual switch; this is not a
        # claim that the last/next spoken word ended/began at its midpoint.
        if pause:
            all_times += [pause.start, pause.end]
        spread = max([abs(t - selected.time) for t in varied_times], default=0.0)
        support = min(1.0, pause.duration / 0.45) if pause else 0.0
        expected_mass = float(np.sum(solution["expected"][:layer_index]))
        prior_error = abs(float(_mass_at(features, selected.time)) - expected_mass)
        prior_support = math.exp(-prior_error / max(0.5, features["active_seconds"] * 0.10))
        margin_support = 1.0 if math.isinf(margin) else 1 - math.exp(-margin / 2)
        stability = math.exp(-spread / 0.20) if variants else 0.0
        score = min(0.85, 0.40 * support + 0.25 * prior_support + 0.20 * margin_support + 0.15 * stability)
        reasons = []
        if pause is None:
            score = min(score, 0.35)
            reasons.append("No silence anchor; interpolated from text weights.")
        elif pause.duration < 0.25:
            score = min(score, 0.60)
            reasons.append("Short pause may be within a word or phrase.")
        if margin < 1.0:
            score = min(score, 0.59)
            reasons.append("A materially different global alignment has similar cost.")
        elif margin < 2.0:
            score = min(score, 0.74)
            reasons.append("A competing global alignment remains plausible.")
        if spread > 0.25:
            score = min(score, 0.49)
            reasons.append("Boundary moves by more than 250 ms under threshold sensitivity checks.")
        elif spread > 0.10:
            score = min(score, 0.74)
            reasons.append("Pause midpoint moves by more than 100 ms under threshold sensitivity checks.")
        if features["energy_range_db"] < 12 or sensitivity_failures:
            score = min(score, 0.40)
        if not reasons:
            reasons.append("Pause, text order and neighboring clause durations agree; listening is still required.")
        ambiguous = score < 0.75 or margin < 2.0 or pause is None or spread > 0.10
        boundaries.append({
            "after_caption_index": units[layer_index - 1].caption_index,
            "time_seconds": _round(selected.time),
            "source": "energy_pause_midpoint" if pause else "text_weight_fallback",
            "pause_span_seconds": [_round(pause.start), _round(pause.end)] if pause else None,
            "text_prior_seconds": _round(solution["priors"][layer_index - 1]),
            "heuristic_score": _round(score),
            "confidence": "high" if score >= 0.75 else "medium" if score >= 0.50 else "low",
            "ambiguous": ambiguous,
            "plausible_range_seconds": [_round(min(all_times)), _round(max(all_times))],
            "alternative_path_margin_cost": _round(margin) if math.isfinite(margin) else None,
            "threshold_sensitivity_max_shift_seconds": _round(spread) if variants else None,
            "threshold_variant_times_seconds": [_round(t) for t in varied_times],
            "review_reasons": reasons,
        })

    cuts = [0.0] + [b["time_seconds"] for b in boundaries] + [features["duration"]]
    if any(right - left < cfg.min_caption_seconds - 1e-6 for left, right in zip(cuts, cuts[1:])):
        raise ValueError("estimated captions violate minimum duration; merge short captions or review manually")
    subtitle_rows = [{"index": i, "id": c.id, "text": c.text,
                      "spoken_text": c.spoken_text if c.spoken_text is not None else c.text,
                      "start_seconds": _round(cuts[i]), "end_seconds": _round(cuts[i + 1]),
                      "duration_seconds": _round(cuts[i + 1] - cuts[i])}
                     for i, c in enumerate(caption_list)]
    return {
        "method": "energy_pause_text_weight_dynamic_programming",
        "schema_version": 1,
        "asr_used": False,
        "word_level_alignment": False,
        "requires_listening_review": True,
        "duration_seconds": _round(features["duration"]),
        "sample_rate": int(sample_rate),
        "speech_like_window_seconds": [_round(features["start"]), _round(features["end"])],
        "speech_like_energy_seconds": _round(features["active_seconds"]),
        "vad": {"type": "adaptive_energy_only", "threshold_dbfs": _round(features["threshold"]),
                "p95_minus_p10_db": _round(features["global_energy_range_db"]),
                "reference_level_dbfs": _round(features["reference_level_db"]),
                "reference_minus_p10_db": _round(features["energy_range_db"]),
                "used_sparse_signal_reference": bool(features["sparse_reference"]),
                "pauses": [{"start_seconds": _round(p.start), "end_seconds": _round(p.end),
                            "duration_seconds": _round(p.duration)} for p in features["pauses"]]},
        "punctuation_unit_count": len(units),
        "optimization_cost": _round(solution["cost"]),
        "threshold_sensitivity_reruns": len(variants),
        "threshold_sensitivity_failures": sensitivity_failures,
        "confidence_note": "High means consistent heuristic pause evidence, not verified correspondence to spoken words.",
        "overall_confidence": min((b["confidence"] for b in boundaries),
                                  key={"low": 0, "medium": 1, "high": 2}.get) if boundaries else "not_applicable",
        "has_ambiguous_boundaries": any(b["ambiguous"] for b in boundaries),
        "warnings": warnings,
        "config": asdict(cfg),
        "boundaries": boundaries,
        "captions": subtitle_rows,
    }


def align_file(audio_path: str | Path,
               captions: Sequence[str | Caption | dict[str, Any]],
               config: AlignmentConfig | None = None) -> dict[str, Any]:
    """Read one audio file without changing it, then estimate its caption cuts."""
    audio, sample_rate = sf.read(audio_path, dtype="float64", always_2d=False)
    result = align_audio(audio, sample_rate, captions, config)
    result["audio_file"] = str(audio_path)
    return result


def _srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    seconds, ms = divmod(milliseconds, 1000)
    minutes, sec = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    return f"{hour:02}:{minute:02}:{sec:02},{ms:03}"


def write_srt(result: dict, path: str | Path) -> None:
    """Write a review-only SRT. It is not a final, verified subtitle track."""
    rows = [f"{i + 1}\n{_srt_time(c['start_seconds'])} --> {_srt_time(c['end_seconds'])}\n{c['text']}\n"
            for i, c in enumerate(result["captions"])]
    with Path(path).open("x", encoding="utf-8") as file:
        file.write("\n".join(rows))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("captions", type=Path, help="JSON array of strings or {text, spoken_text?, id?}")
    parser.add_argument("--output", type=Path, required=True, help="Estimated boundaries and uncertainty JSON")
    parser.add_argument("--srt", type=Path, help="Optional review-only estimated subtitle track")
    parser.add_argument("--threshold-db", type=float, help="Override adaptive energy threshold in dBFS")
    args = parser.parse_args()
    outputs = [p.resolve() for p in (args.output, args.srt) if p is not None]
    inputs = {args.audio.resolve(), args.captions.resolve()}
    if len(set(outputs)) != len(outputs) or any(p in inputs for p in outputs):
        parser.error("outputs must be distinct and must not overwrite input audio or caption files")
    try:
        captions = json.loads(args.captions.read_text(encoding="utf-8"))
        result = align_file(args.audio, captions, AlignmentConfig(threshold_db=args.threshold_db))
    except (ValueError, OSError, RuntimeError) as error:
        parser.error(str(error))
    if any(p.exists() for p in (args.output, args.srt) if p is not None):
        parser.error("choose new output paths; existing files are refused")
    with args.output.open("x", encoding="utf-8") as file:
        file.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    if args.srt is not None:
        write_srt(result, args.srt)
    print(json.dumps({"output": str(args.output), "caption_count": len(result["captions"]),
                      "boundaries_seconds": [b["time_seconds"] for b in result["boundaries"]],
                      "overall_confidence": result["overall_confidence"],
                      "requires_listening_review": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
