const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const cli = path.resolve(__dirname, '../bin/sketch-video.js');
const run = (...args) => spawnSync(process.execPath, [cli, ...args], { encoding: 'utf8' });

test('help and version work without Python; unknown command fails', () => {
  assert.equal(run('--help').status, 0);
  assert.match(run('--help').stdout, /install-skill/);
  assert.equal(run('--version').stdout.trim(), '0.1.0');
  assert.notEqual(run('unknown').status, 0);
});

test('init copies real examples and refuses existing directories and symlinks', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sketch-cli-'));
  try {
    const dest = path.join(tmp, 'space and 中文');
    assert.equal(run('init', dest, '--example', 'water').status, 0);
    const before = fs.readFileSync(path.join(dest, 'story.json'), 'utf8');
    assert.equal(JSON.parse(before).title, '一滴水的旅行');
    assert.notEqual(run('init', dest).status, 0);
    assert.equal(fs.readFileSync(path.join(dest, 'story.json'), 'utf8'), before);
    const link = path.join(tmp, 'link');
    fs.symlinkSync(dest, link, 'dir');
    assert.notEqual(run('init', link).status, 0);
    assert.notEqual(run('init', path.join(tmp, 'bad'), '--example', '../secret').status, 0);
    assert.equal(fs.existsSync(path.join(tmp, 'bad')), false);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test('skill installation is explicit and includes portable Python resources', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sketch-skill-'));
  try {
    const dest = path.join(tmp, 'sketch-video-skill');
    assert.equal(run('install-skill', dest).status, 0);
    for (const name of ['SKILL.md', 'scripts/render.py', 'scripts/verify.py', 'references/storyboard.md', 'README.md']) assert.ok(fs.existsSync(path.join(dest, name)));
    assert.equal(fs.existsSync(path.join(dest, '.git')), false);
    assert.notEqual(run('install-skill', dest).status, 0);
    assert.notEqual(run('install-skill').status, 0);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test('Python selection fails clearly and arguments are passed without a shell', () => {
  assert.match(run('doctor', '--python', '/missing/python').stderr, /Cannot start/);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sketch-argv-'));
  try {
    const fake = path.join(tmp, 'fake-python');
    fs.symlinkSync(process.execPath, fake);
    // Node is deliberately used as a non-Python interpreter: no shell interprets metacharacters.
    const marker = path.join(tmp, 'MUST_NOT_EXIST');
    const result = run('render', '--python', fake, `;touch ${marker}`, '--out', 'unused');
    assert.notEqual(result.status, 0);
    assert.equal(fs.existsSync(marker), false);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});
