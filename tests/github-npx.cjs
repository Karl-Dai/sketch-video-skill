// Opt-in remote test against an explicit, immutable commit of this repository.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const spec = process.env.GITHUB_NPX_SPEC;
assert.match(spec || '', /^git\+https:\/\/github\.com\/Karl-Dai\/sketch-video-skill\.git#[a-f0-9]{40}$/);
assert.ok(process.env.TEST_PYTHON && process.env.TEST_FONT, 'Set TEST_PYTHON and TEST_FONT');
const npm = process.env.npm_execpath;
const npx = path.join(path.dirname(npm), 'npx-cli.js');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sketch-github-'));
const env = { ...process.env, npm_config_cache: path.join(tmp, 'cache'), npm_config_update_notifier: 'false' };
function run(command, args, cwd = tmp) {
  const r = spawnSync(command, args, { cwd, env, encoding: 'utf8', shell: false });
  assert.equal(r.status, 0, `${path.basename(command)} failed: ${r.stderr}\n${r.stdout}`);
  return r.stdout;
}
const cli = (...args) => run(process.execPath, [npx, '--yes', '--ignore-scripts', `--package=${spec}`, 'sketch-video', ...args]);
try {
  assert.match(cli('--help'), /install-skill/);
  const project = path.join(tmp, 'new project');
  cli('init', project, '--example', 'hd');
  const skill = path.join(tmp, 'new skill');
  cli('install-skill', skill);
  assert.ok(fs.existsSync(path.join(skill, 'SKILL.md')));
  const python = path.resolve(process.env.TEST_PYTHON);
  cli('doctor', '--python', python);
  const out = path.join(tmp, 'new output');
  cli('render', '--python', python, path.join(project, 'story.json'), '--out', out, '--font', process.env.TEST_FONT);
  cli('verify', '--python', python, out);
  const result = JSON.parse(fs.readFileSync(path.join(out, 'verification.json')));
  assert.equal(result.decoded_frames, 48);
  let productionFrames = null;
  if (process.env.TEST_PRODUCTION === '1') {
    const call = (...args) => cli(...args, '--python', python);
    const inputs = path.join(tmp, 'audio inputs');
    call('fixture', '--out', inputs);
    if (process.env.TEST_VOICE === '1') {
      const doctor = JSON.parse(call('voice-doctor'));
      assert.equal(doctor.environment.ORT_DISABLE_TELEMETRY, '1');
      assert.ok(doctor.modules.numpy && doctor.modules.soundfile && doctor.modules.pypinyin);
      const timing = path.join(tmp, 'voice-timing');
      call('align-captions', path.join(inputs, 'story.json'), '--audio', path.join(inputs, 'audio.json'), '--out', timing);
      assert.equal(JSON.parse(fs.readFileSync(path.join(timing, 'audio.json'))).caption_timing, 'energy_pause_estimate');
      call('prepare-audio', path.join(inputs, 'story.json'), '--audio', path.join(timing, 'audio.json'), '--out', path.join(tmp, 'voice-prepared'));
    }
    const prepared = path.join(tmp, 'prepared');
    call('prepare-audio', path.join(inputs, 'story.json'), '--audio', path.join(inputs, 'audio.json'), '--out', prepared);
    const animation = path.join(tmp, 'animation');
    call('render', path.join(prepared, 'retimed.json'), '--out', animation, '--font', process.env.TEST_FONT, '--size', '360x640');
    const final = path.join(tmp, 'final');
    call('mux', animation, prepared, '--out', final);
    call('verify-av', final);
    const handoff = path.join(tmp, 'handoff');
    call('package', final, '--metadata', path.join(inputs, 'publication.json'), '--out', handoff);
    productionFrames = JSON.parse(fs.readFileSync(path.join(final, 'av-verification.json'))).decoded_frames;
    assert.equal(productionFrames, 59);
    assert.equal(JSON.parse(fs.readFileSync(path.join(handoff, 'handoff.json'))).uploaded, false);
  }
  const consumer = path.join(tmp, 'npm consumer');
  fs.mkdirSync(consumer);
  run(process.execPath, [npm, 'install', '--ignore-scripts', '--no-audit', '--no-fund', spec], consumer);
  assert.equal(run(process.execPath, [npm, 'exec', '--offline', '--', 'sketch-video', '--version'], consumer).trim(), '0.1.0');
  console.log(JSON.stringify({status: 'passed', spec, npx_help: 'passed', npx_init: 'passed', npx_install_skill: 'passed', npx_doctor: 'passed', npx_render_verify: 'passed', decoded_frames: result.decoded_frames, production_av_frames: productionFrames, size: result.size, fps: result.fps, npm_install_github: 'passed', optional_voice_checked: process.env.TEST_VOICE === '1', npm_registry_publication: false}, null, 2));
} finally { fs.rmSync(tmp, {recursive: true, force: true}); }
