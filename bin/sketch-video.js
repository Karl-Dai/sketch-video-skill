#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const pkg = require('../package.json');

const help = `sketch-video ${pkg.version} — local hand-drawn explainers

Usage:
  sketch-video --help | --version
  sketch-video init <new-directory> [--example idea|water|hd]
  sketch-video install-skill <new-skill-directory>
  sketch-video doctor [--python <executable>]
  sketch-video render [--python <executable>] <story.json> --out <new-directory> [render options]
  sketch-video verify [--python <executable>] <render-directory>
  sketch-video fixture --out <new-directory>
  sketch-video audition | select-voice | tts | asr | prepare-audio | asr-check [options]
  sketch-video mux | verify-av | package | record-publication [options]

Rendering options are passed to the bundled Python renderer; use render --help.
Production steps use --help for their exact syntax; --python is supported on each.
TTS/ASR need a trusted local adapter and --execute; WAV import needs no model.
package creates a local handoff only; record-publication stores a caller receipt.
Python 3.10+, Pillow, fontTools, FFmpeg/libx264 and a suitable font are external.
Set SKETCH_PYTHON to a Python executable, or activate your virtual environment.
Nothing is installed or downloaded automatically. Existing destinations are refused.
`;

function fail(message) { throw new Error(message); }

function pythonArgs(args) {
  let python = process.env.SKETCH_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  const remaining = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--python') {
      if (!args[i + 1] || args[i + 1].startsWith('--')) fail('--python requires an executable path');
      python = args[++i];
    } else remaining.push(args[i]);
  }
  return { python, remaining };
}

function invoke(command, args, options = {}) {
  const result = spawnSync(command, args, { shell: false, ...options });
  if (result.error) fail(`Cannot start ${path.basename(command)}: ${result.error.code}. Check installation or --python.`);
  if (result.signal) fail(`Child process stopped by ${result.signal}`);
  return result;
}

function createNewDirectory(target, fill) {
  const dest = path.resolve(target);
  // mkdir without recursive/force reserves the leaf atomically; never follow an existing symlink.
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.mkdirSync(dest);
  try { fill(dest); } catch (error) { fs.rmSync(dest, { recursive: true }); throw error; }
  return dest;
}

function init(args) {
  const dest = args.shift();
  if (!dest || dest.startsWith('--')) fail('init requires a new directory');
  let example = 'idea';
  if (args.length) {
    if (args.length !== 2 || args[0] !== '--example') fail('Expected --example idea|water|hd');
    example = args[1];
  }
  const source = { idea: 'idea-to-video.json', water: 'water-cycle.zh.json', hd: 'smoke-hd.json' }[example];
  if (!source) fail('Unknown example; choose idea, water or hd');
  const created = createNewDirectory(dest, folder => {
    fs.copyFileSync(path.join(root, 'examples', source), path.join(folder, 'story.json'));
    for (const name of ['brief.md', 'sources.md']) fs.copyFileSync(path.join(root, 'examples', name), path.join(folder, name));
    fs.copyFileSync(path.join(root, 'requirements.txt'), path.join(folder, 'requirements.txt'));
  });
  console.log(`Created ${created}\nEdit story.json. The brief and source ledger are water-cycle reference examples; adapt them to your topic.\nCreate a Python virtual environment and install requirements.txt before rendering.`);
}

function installSkill(args) {
  if (args.length !== 1 || args[0].startsWith('--')) fail('install-skill requires an explicit new skill directory');
  const created = createNewDirectory(args[0], dest => {
    for (const name of ['SKILL.md', 'agents', 'scripts', 'references', 'examples', 'docs', 'requirements.txt', 'requirements-dev.txt', 'README.md', 'README.zh-CN.md', 'README_EN.md', 'NOTICE.md', 'LICENSE']) {
      fs.cpSync(path.join(root, name), path.join(dest, name), { recursive: true, filter: source => !source.includes('__pycache__') && !source.endsWith('.pyc') });
    }
  });
  console.log(`Installed Skill to ${created}\nInstall the Python requirements separately, then reload your Agent's skill discovery if needed.`);
}

function doctor(args) {
  const { python, remaining } = pythonArgs(args);
  if (remaining.length) fail('Unexpected doctor arguments');
  const code = `import sys, json, importlib.util, shutil, subprocess
checks={'python_3_10_or_newer': sys.version_info >= (3,10), 'Pillow': importlib.util.find_spec('PIL') is not None, 'fontTools': importlib.util.find_spec('fontTools') is not None, 'ffmpeg': shutil.which('ffmpeg') is not None, 'ffprobe': shutil.which('ffprobe') is not None}
checks['libx264'] = False
if checks['ffmpeg']:
    probe=subprocess.run(['ffmpeg','-hide_banner','-encoders'],capture_output=True,text=True)
    checks['libx264']=probe.returncode==0 and any('libx264' in line.split() for line in probe.stdout.splitlines())
print(json.dumps({'checks':checks,'font':'Select a local font with --font; glyph coverage is checked at render time.'},indent=2))
sys.exit(0 if all(checks.values()) else 1)
`;
  const result = invoke(python, ['-c', code], { stdio: 'inherit' });
  return result.status;
}

function main(args) {
  const command = args.shift();
  if (!command || ['--help', '-h', 'help'].includes(command)) { console.log(help); return 0; }
  if (['--version', '-v'].includes(command)) { console.log(pkg.version); return 0; }
  if (command === 'init') { init(args); return 0; }
  if (command === 'install-skill') { installSkill(args); return 0; }
  if (command === 'doctor') return doctor(args);
  if (['render', 'verify'].includes(command)) {
    const { python, remaining } = pythonArgs(args);
    if (!remaining.length) fail(`${command} requires arguments; use ${command} --help`);
    return invoke(python, [path.join(root, 'scripts', `${command}.py`), ...remaining], { stdio: 'inherit' }).status;
  }
  if (['fixture', 'audition', 'select-voice', 'tts', 'asr', 'prepare-audio', 'asr-check', 'mux', 'verify-av', 'package', 'record-publication'].includes(command)) {
    const { python, remaining } = pythonArgs(args);
    return invoke(python, [path.join(root, 'scripts', 'production.py'), command, ...remaining], { stdio: 'inherit' }).status;
  }
  fail(`Unknown command: ${command}. Use --help.`);
}

try { process.exitCode = main(process.argv.slice(2)); }
catch (error) { console.error(`sketch-video: ${error.message}`); process.exitCode = 1; }
