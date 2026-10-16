# Node CLI and package distribution

The CLI wraps the existing Python renderer; it does not replace it. The package has no Node dependencies or install/prepare hooks. It does not download models, execute remote setup scripts or install Python/FFmpeg. Rendering remains silent; narration is unchanged and experimental.

## Current publication status

Version `0.1.0` is distributed directly from this public GitHub repository. There is no npm registry publication and no npm login is required. `private: true` prevents accidental registry publication; it does not make the GitHub repository private or prevent GitHub installation. Do not use a bare registry package name: use an explicit GitHub URL and the `sketch-video` binary.

## Commands

| Command | Effect |
| --- | --- |
| `sketch-video --help` / `--version` | Show usage/version, without Python |
| `sketch-video init my-video --example idea` | Create a new project with JSON, reference brief/ledger and Python requirements; `water` and `hd` are also available |
| `sketch-video install-skill /path/to/new-skill` | Copy Skill instructions and supporting resources to an explicit new directory |
| `sketch-video doctor --python /path/to/python` | Check Python ≥3.10, Pillow, fontTools, FFmpeg, ffprobe and libx264; nonzero exit if missing |
| `sketch-video render --python /path/to/python story.json --out new-output` | Call the packaged Python renderer; supports its existing flags |
| `sketch-video verify --python /path/to/python new-output` | Check captions and fully decode the generated video |

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

Node 22+ is the declared minimum. Local validation uses macOS ARM64, Node 26.9.0 and npm 11.19.1; Linux CI checks additional Node versions. Windows has not been tested. Registry installation cannot be validated before an authorized registry publication.

The implementation follows the official npm documentation for [bin/files metadata](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/), [npm exec/npx](https://docs.npmjs.com/cli/v11/commands/npm-exec/), [Git/tarball package specs](https://docs.npmjs.com/cli/v11/using-npm/package-spec/) and [publishing](https://docs.npmjs.com/cli/v11/commands/npm-publish/).
