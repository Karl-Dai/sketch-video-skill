# Node CLI and package distribution

The CLI wraps the Python drawing and production scripts. It has no Node dependencies or install/prepare hooks, does not download models and does not install Python/FFmpeg. Silent rendering remains supported; the [production extension](production.md) supports imported WAVs, explicit local TTS/ASR adapters, retiming, mixing, AV checks and publication handoffs. Actual model quality is separate from the model-free fixture tests.

## Current publication status

Version `0.1.0` is distributed directly from this public GitHub repository. There is no npm registry publication and no npm login is required. `private: true` prevents accidental registry publication; it does not make the GitHub repository private or prevent GitHub installation. Do not use a bare registry package name: use an explicit GitHub URL and the `sketch-video` binary.

## Commands

Tested, immutable GitHub entry point (requires Node 22+ and Git):

```bash
npx --yes --ignore-scripts --package="git+https://github.com/Karl-Dai/sketch-video-skill.git#3e7e94259864588ff5ac815d1cc608bb42ac532f" sketch-video --help
```

Use the same prefix with any command below. `--ignore-scripts` disables dependency lifecycle scripts; it does not suppress the explicitly requested CLI. This package defines no install/prepare hook in any case.

| Command | Effect |
| --- | --- |
| `sketch-video --help` / `--version` | Show usage/version, without Python |
| `sketch-video init my-video --example idea` | Create a new project with JSON, reference brief/ledger and Python requirements; `water` and `hd` are also available |
| `sketch-video install-skill /path/to/new-skill` | Copy Skill instructions and supporting resources to an explicit new directory |
| `sketch-video doctor --python /path/to/python` | Check Python ≥3.10, Pillow, fontTools, FFmpeg, ffprobe and libx264; nonzero exit if missing |
| `sketch-video render --python /path/to/python story.json --out new-output` | Call the packaged Python renderer; supports its existing flags |
| `sketch-video verify --python /path/to/python new-output` | Check captions and fully decode the generated video |
| `fixture`, `audition`, `select-voice` | Make labelled test tones, inspect pre-generated auditions, record a specific listening decision |
| `tts`, `asr` | Plan local adapter requests; execute only with `--execute` |
| `prepare-audio`, `asr-check` | Measure WAVs, build the retimed storyboard/subtitle clock, review imported recognition differences |
| `mux`, `verify-av` | Mix matching video/audio and check both complete streams |
| `package`, `record-publication` | Create a local handoff and store observed receipts; no upload |

`SKETCH_PYTHON` selects an executable without passing `--python` each time. Pass an executable path, not a shell command with arguments. Input/output paths resolve from the current working directory, while bundled scripts resolve from the package directory. No shell is used to launch Python. Existing init/install/render destinations are refused.

## Run versus install

`npx --package=<explicit-package-spec> sketch-video ...` runs the CLI. Installing a package with `npm install` makes that CLI available through `npm exec -- sketch-video ...`; neither action registers an Agent Skill. Run `install-skill` separately to copy `SKILL.md` and its resources into your Agent's configured skills directory. Loading the Skill alone does not install Python dependencies.

The repository keeps a valid `SKILL.md` at its root. No third-party `skills` installer has been validated as part of this package; the bundled explicit-destination installer is the tested path.

## Packaging and validation

`package.json#files` is a whitelist of the CLI, Skill resources, Python source, examples and selected docs/previews. Raw archives, build outputs, caches, tokens, private paths, models and fonts are excluded. `npm run test:pack` packs a tarball, audits every member, extracts it, runs the extracted CLI, checks init/Skill installation, installs the tarball into an isolated npm consumer and runs `npm exec`. With `TEST_PYTHON` and `TEST_FONT`, it also checks dependencies, renders two seconds and fully decodes 48 frames. Test temp directories and cache are removed afterwards.

Local development commands:

```bash
npm test
TEST_PYTHON=/path/to/python TEST_FONT=/path/to/font.ttf npm run test:pack
npm pack --ignore-scripts --dry-run
```

For the remote end-to-end test, set `GITHUB_NPX_SPEC` to the exact 40-character GitHub commit spec above, `TEST_PYTHON` to your environment's Python and `TEST_FONT` to a local font, then run `npm run test:github`. It runs actual npx help, init, Skill installation, doctor, rendering and verification from the remote package, and separately checks `npm install` from GitHub. Local execution passed with 48 fully decoded frames at 1080×1920/24 fps. A fresh temporary npm cache is used and removed with the test workspace.

Node 22+ is the declared minimum. Local validation uses macOS ARM64, Node 26.9.0 and npm 11.19.1; Linux CI checks Node 22/24. Windows has not been tested. No registry publication is planned. `README.md` is Chinese-first, `README_EN.md` is English, and `README.zh-CN.md` remains a synchronized Chinese compatibility entry.

The implementation follows the official npm documentation for [bin/files metadata](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/), [npm exec/npx](https://docs.npmjs.com/cli/v11/commands/npm-exec/), [Git/tarball package specs](https://docs.npmjs.com/cli/v11/using-npm/package-spec/) and [publishing](https://docs.npmjs.com/cli/v11/commands/npm-publish/).
