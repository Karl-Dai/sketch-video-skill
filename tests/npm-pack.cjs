// Exercise the actual npm tarball, not just files in the checkout.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const pkg = require('../package.json');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sketch-pack-'));
const npm = process.env.npm_execpath;
assert.ok(npm, 'Run with npm run test:pack');
const env = { ...process.env, npm_config_cache: path.join(tmp, 'cache') };
function run(command, args, cwd = tmp) {
  const r = spawnSync(command, args, { cwd, env, encoding: 'utf8', shell: false });
  assert.equal(r.status, 0, `${path.basename(command)} failed: ${r.stderr}\n${r.stdout}`);
  return r.stdout;
}
const pattern = value => new RegExp('^' + value.split('*').map(part => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('[^/]*') + '$');
try {
  const packed = JSON.parse(run(process.execPath, [npm, 'pack', '--ignore-scripts', '--json', '--pack-destination', tmp], root))[0];
  const allowed = [...pkg.files.map(pattern), /^package\.json$/, /^README\.md$/];
  for (const file of packed.files) {
    assert.ok(allowed.some(rule => rule.test(file.path)), `Unexpected packed file: ${file.path}`);
    assert.ok(!/(?:^|\/)(?:\.git|\.npmrc|node_modules|__pycache__|build)(?:\/|$)/.test(file.path));
  }
  for (const hook of ['preinstall', 'install', 'postinstall', 'prepare', 'prepack', 'postpack', 'prepublishOnly']) assert.equal(pkg.scripts[hook], undefined, `Unexpected lifecycle hook: ${hook}`);
  const archive = path.join(tmp, packed.filename);
  run('tar', ['-xzf', archive, '-C', tmp]);
  const cli = path.join(tmp, 'package/bin/sketch-video.js');
  assert.match(run(process.execPath, [cli, '--help']), /sketch-video/);
  const project = path.join(tmp, 'project with spaces');
  run(process.execPath, [cli, 'init', project, '--example', 'hd']);
  const skill = path.join(tmp, 'installed-skill');
  run(process.execPath, [cli, 'install-skill', skill]);
  assert.ok(fs.existsSync(path.join(skill, 'scripts/render.py')));
  const installed = path.join(tmp, 'npm-consumer');
  fs.mkdirSync(installed);
  run(process.execPath, [npm, 'install', archive, '--ignore-scripts', '--offline', '--no-audit', '--no-fund'], installed);
  assert.equal(run(process.execPath, [npm, 'exec', '--offline', '--', 'sketch-video', '--version'], installed).trim(), pkg.version);
  assert.match(run(process.execPath, [npm, 'exec', '--offline', '--yes', `--package=${archive}`, '--', 'sketch-video', '--help']), /install-skill/);
  let decodedFrames = null;
  if (process.env.TEST_PYTHON && process.env.TEST_FONT) {
    const python = path.resolve(process.env.TEST_PYTHON);
    run(process.execPath, [cli, 'doctor', '--python', python]);
    const out = path.join(tmp, 'render output');
    run(process.execPath, [cli, 'render', '--python', python, path.join(project, 'story.json'), '--out', out, '--font', process.env.TEST_FONT]);
    run(process.execPath, [cli, 'verify', '--python', python, out]);
    decodedFrames = JSON.parse(fs.readFileSync(path.join(out, 'verification.json'))).decoded_frames;
    assert.equal(decodedFrames, 48);
  }
  console.log(JSON.stringify({ status: 'passed', version: pkg.version, tarball_files: packed.files.length, tarball_bytes: packed.size, unpacked_bytes: packed.unpackedSize, whitelist: 'passed', extracted_cli: 'passed', npm_install_local_tarball: 'passed', npm_exec_local_tarball: 'passed', decoded_frames: decodedFrames }, null, 2));
} finally { fs.rmSync(tmp, { recursive: true, force: true }); }
