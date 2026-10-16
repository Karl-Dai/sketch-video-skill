import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from render import load_story, timeline, timestamp, check_glyphs, Painter

ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.story = load_story(ROOT/'examples/idea-to-video.json')

    def test_clock_quantizes_and_covers_every_frame(self):
        self.story['scenes'][0]['duration'] = 4.015
        self.story['scenes'][0]['captions'] = ['First thought.', 'A longer second thought.']
        clock = timeline(self.story, 24)
        self.assertEqual(clock['frames'], sum(round(s['duration']*24) for s in self.story['scenes']))
        intervals = clock['captions']
        self.assertEqual(intervals[0]['start_frame'], 0)
        self.assertEqual(intervals[-1]['end_frame'], clock['frames'])
        for a, b in zip(intervals, intervals[1:]):
            self.assertEqual(a['end_frame'], b['start_frame'])
        self.assertEqual(timestamp(clock['frames'], 24), '00:00:12,000')

    def test_bad_story_fails_before_render(self):
        for field, value in [('duration', float('nan')), ('duration', True), ('layout', 'unknown'), ('labels', ['Only one']), ('captions', [])]:
            story = copy.deepcopy(self.story)
            story['scenes'][0][field] = value
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp)/'bad.json'
                p.write_text(json.dumps(story))
                with self.assertRaises(ValueError):
                    load_story(p)

    def test_missing_font_glyphs_and_overflow(self):
        import os
        font = os.environ.get('TEST_FONT')
        if not font:
            self.skipTest('TEST_FONT not set')
        check_glyphs(self.story, font, 0)
        painter = Painter(self.story, timeline(self.story, 24), font, 0)
        for n in (0, 48, 95, 96, 160, 191, 192, 240, 287):
            self.assertEqual(painter.frame(n).size, (1080, 1920))
        self.story['title'] = chr(0x10ffff)
        with self.assertRaisesRegex(ValueError, 'glyphs'):
            check_glyphs(self.story, font, 0)
        self.story['title'] = 'overflow ' * 200
        with self.assertRaisesRegex(ValueError, 'overflows'):
            Painter(self.story, timeline(self.story, 24), font, 0)


if __name__ == '__main__':
    unittest.main()
