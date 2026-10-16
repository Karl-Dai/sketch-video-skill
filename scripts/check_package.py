#!/usr/bin/env python3
"""Validate skill metadata, examples and repository-local Markdown links."""
from pathlib import Path
import re
import sys

import yaml
from render import load_story

ROOT = Path(__file__).resolve().parents[1]


def main():
    text = (ROOT/'SKILL.md').read_text()
    parts = text.split('---', 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError('SKILL.md requires YAML frontmatter')
    meta = yaml.safe_load(parts[1])
    if meta.get('name') != 'sketch-video-skill' or not meta.get('description'):
        raise ValueError('skill name or description is invalid')
    ui = yaml.safe_load((ROOT/'agents/openai.yaml').read_text())
    if '$sketch-video-skill' not in ui['interface']['default_prompt']:
        raise ValueError('UI prompt must invoke the skill')
    for path in (ROOT/'examples').glob('*.json'):
        load_story(path)
    checked = 0
    for path in ROOT.rglob('*.md'):
        if any(p in ('build', '.git', '.venv') for p in path.relative_to(ROOT).parts):
            continue
        for href in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if href.startswith(('http://', 'https://', '#', 'mailto:')):
                continue
            target = path.parent/href.split('#', 1)[0]
            if not target.is_file():
                raise ValueError(f'broken link: {path.relative_to(ROOT)} -> {href}')
            checked += 1
    print(f'PASS: skill metadata, examples, UI prompt and {checked} local Markdown links')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as exc:
        print(f'package check failed: {exc}', file=sys.stderr)
        sys.exit(1)
