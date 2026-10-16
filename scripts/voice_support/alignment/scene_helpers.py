"""Validated adapter for scene_narration_plan.json; no text normalization guesses."""

from __future__ import annotations

import re


_PUNCTUATION = re.compile(r"[，、。！？；：,.!?;:]")


def captions_from_scene(scene: dict) -> list[dict]:
    """Partition normalized scene speech using unchanged punctuation order.

    This adapter deliberately fails if normalization changes punctuation, if
    caption display text does not concatenate to the source script, or if a
    caption does not end in punctuation. Then callers must provide explicit
    normalized spoken text for each caption instead of trusting guessed cuts.
    """
    captions = scene["captions"]
    spoken = scene["spoken_text"]
    script = scene["script"]
    ids = scene.get("caption_ids", list(range(len(captions))))
    if len(ids) != len(captions) or not captions or "".join(captions) != script:
        raise ValueError("caption list/IDs do not exactly reproduce this scene's script")
    source_punctuation = _PUNCTUATION.findall(script)
    spoken_marks = list(_PUNCTUATION.finditer(spoken))
    if source_punctuation != [m.group() for m in spoken_marks]:
        raise ValueError("normalization changed punctuation order; provide per-caption spoken_text")
    result = []
    count = 0
    start = 0
    for index, text in enumerate(captions):
        if not text or not _PUNCTUATION.fullmatch(text[-1]):
            raise ValueError("caption must end in punctuation; provide per-caption spoken_text")
        count += len(_PUNCTUATION.findall(text))
        end = spoken_marks[count - 1].end()
        result.append({"id": ids[index], "text": text, "spoken_text": spoken[start:end]})
        start = end
    if start != len(spoken):
        raise ValueError("spoken text has unmatched trailing content")
    return result
