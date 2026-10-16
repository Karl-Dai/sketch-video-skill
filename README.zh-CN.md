# Sketch Video Skill

**从一个想法，到一支有逻辑、有动画、有字幕的科普视频。**

用代码把知识画出来：纸张底色、手绘线条、逐步生长的关系图，再配上一条可以核对的字幕时间线。

[English](README_EN.md) · [Skill 入口](SKILL.md) · [12 秒演示](docs/demo.mp4) · [中文示例](docs/water-cycle.mp4) · [实测记录](docs/validation.md)

![混合画面：分枝、时间线、对比、步骤和循环](docs/mixed-preview.jpg)

## 不只做出画面，也把过程交出来

这是一套可复用的 Agent Skill，附带可独立运行的本地渲染器。它从此前完成的 38 秒样片、五分钟中文手绘科普片中提炼绘图、时间线和质检方法，再用 JSON 分镜扩展到其他主题。

- **代码原创绘图**：固定纸张纹理、渐进描线、树形关系、流程、循环、时间线和双栏对比。
- **字幕共用时钟**：画内字幕、SRT、讲稿来自同一份帧时间线。
- **结果可以检查**：每镜开始／中段／结束图、联系表、完整视频解码验证。
- **本地即可渲染**：Python、Pillow、fontTools、FFmpeg；示例不需要 API Key，也不下载模型。
- **中英文示例**：显式指定字体，预先检查缺字与文字溢出。

默认输出为 **1080×1920、24 fps、H.264 无声竖屏视频**。事实核查、叙事和画面审阅由 Agent 与使用者完成；渲染器不会自动把一句提示变成经过核查的完整课程。内置五种通用图示，更具体的学科插画需要扩展绘图代码。

## 直接用 npx，不需要 npm 登录

需要 Node 22+ 和 Git。以下命令固定到包含 CLI 的提交，直接从公开 GitHub 拉取运行，不依赖 npm registry 发布：

```bash
npx --yes --ignore-scripts --package="git+https://github.com/Karl-Dai/sketch-video-skill.git#e54741d821474e417bb1f25daf13d93e393bc259" sketch-video --help
```

把 `--help` 换成 `init my-video --example water`，即可创建中文分镜示例；换成 `install-skill /path/to/new-skill-directory`，则会把技能复制到指定的新目录。**运行 CLI 和安装 Agent Skill 是两件事**，都不会自动安装 Python、FFmpeg 或模型。完整语法见[命令说明与实测范围](docs/npm.md)。

也可以把同一版本安装到自己的项目中，方便反复调用：

```bash
npm install --ignore-scripts "git+https://github.com/Karl-Dai/sketch-video-skill.git#e54741d821474e417bb1f25daf13d93e393bc259"
npm exec -- sketch-video init my-video --example water
```

配置好 Python 环境后，用 `npm exec -- sketch-video doctor --python /path/to/python` 检查依赖，再运行 `npm exec -- sketch-video render --python /path/to/python my-video/story.json --out new-output --font /path/to/font.ttc`，最后用 `npm exec -- sketch-video verify --python /path/to/python new-output` 完整解码检查。Node 仅包装现有 Python 渲染器。包配置的 `private: true` 用于防止误发 npm registry，GitHub 源码仍然公开。

## 也可直接运行 Python

需要 Python 3.10+、带 `libx264` 的 FFmpeg/ffprobe，以及本地 TTF/OTF/TTC 字体。请先用系统包管理器安装 FFmpeg。英文可用 DejaVu Sans，中文可用 Noto Sans CJK；仓库不附带字体或可执行程序。

```bash
git clone https://github.com/Karl-Dai/sketch-video-skill.git
cd sketch-video-skill
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/render.py examples/idea-to-video.json --out build/demo --size 360x640
python scripts/verify.py build/demo
```

Windows 使用 `.venv\Scripts\Activate.ps1` 激活环境，并用 `--font "C:\path\to\font.ttf"` 指定字体。其他系统若自动查找失败，可传 `--font /path/to/font.ttf` 或设置 `SKETCH_FONT`。每次指定一个**新的输出目录**，程序会拒绝覆盖已有目录。

输出包含 `video.mp4`、`captions.srt`、`narration.txt`、`timeline.json`、分镜质检图，以及渲染和验证报告。

```bash
# 先检查中文分镜，不编码视频
python scripts/render.py examples/water-cycle.zh.json --out build/water-preview \
  --font /path/to/NotoSansCJK-Regular.ttc --preview-only

# 正式渲染省略 --size，默认 1080×1920
python scripts/render.py examples/water-cycle.zh.json --out build/water-hd \
  --font /path/to/NotoSansCJK-Regular.ttc
python scripts/verify.py build/water-hd
```

中文水循环示例的事实依据见[资料清单](examples/sources.md)。还需要逐镜看图、检查字幕阅读时间并播放全片；解码通过不能替代内容与画面审阅。

## 安装为 Agent Skill

在 Codex 中，把本目录复制到配置的技能目录，通常为 `~/.codex/skills/sketch-video-skill`。保留 `SKILL.md`、`scripts/`、`references/`、`examples/` 的相对结构；如目标已存在，先检查用途。用虚拟环境安装 Python 依赖，确保 FFmpeg 可用，必要时刷新技能发现。兼容 Agent 也可以直接加载 `SKILL.md`；脚本本身不依赖特定 Agent 平台。

可以这样使用：

> 使用 $sketch-video-skill，给好奇的中学生解释电池怎样储存能量。做一支 45 秒中文无声竖屏科普视频，核对科学事实，使用代码原创示意图，保留字幕，并给我看质检分镜。

完整流程：明确目标 → 查证资料 → 写讲稿 → 分镜 → 代码动画 → 字幕 → 渲染 → 看图 → 全片解码。入口在 [SKILL.md](SKILL.md)。

## 换一个主题

1. 从[创作简报](examples/brief.md)和事实来源表开始，先确定观众看完能理解什么。
2. 修改[示例 JSON](examples/idea-to-video.json)里的标题、时长、标签和字幕。
3. 先分镜，再选画法：`tree` 表示分枝，`process` 表示步骤，`cycle` 表示循环，`timeline` 表示历史或进程，`comparison` 比较两个方案。手绘风不等于每页画树；场景插画、局部放大属于自定义代码扩展。
4. 先预览再渲染，修改讲稿时同步修改字幕和时间安排。

详细说明见[分镜格式](references/storyboard.md)、[制作方法](references/workflow.md)和[可复现实测](docs/validation.md)。字幕按文字长度分配时间，未做语音对齐。当前渲染器为单进程，没有实时渲染或长片加速承诺。

## 从想法到有声成片，再到发布交接

无声流程保持兼容。现在有可执行的后半程：音色试听与选择记录、场景或整段 WAV 导入、显式本地 TTS/ASR 适配器、按实测音长调整时间线与字幕、AAC 混流、完整 AV 检查，以及本地发布素材包和回执。[完整操作示例](docs/production.md)与[音频格式、模型许可和成本边界](references/voice.md)已提供。

先完成目标、查证、讲稿和分镜，再准备 `story.json` 与经过审阅的 `audio.json`：

```bash
python scripts/production.py audition voices.json --out build/auditions
# 实际试听并选音色；导入 WAV，或显式执行已安装的本地 TTS 适配器。
python scripts/production.py prepare-audio story.json --audio audio.json --out build/prepared
python scripts/production.py asr-check build/prepared --transcript transcript.json --out build/asr-review.json
python scripts/render.py build/prepared/retimed.json --out build/animation --font /path/to/font.ttf
python scripts/production.py mux build/animation build/prepared --out build/final
python scripts/production.py verify-av build/final
python scripts/production.py package build/final --metadata publication.json --out build/handoff
```

ASR 可跳过，也可导入已有转录或显式调用本地适配器，不会自动下载模型。未提供审阅过的字幕边界时，时间分配仍是明确标记的文字长度启发式，不冒充语音强制对齐。完整说明另附**无需模型的测试音版本**，用于复现技术流程，不代表真人配音质量已验证。

上游已完成 Qwen3-TTS Serena 配音与 Whisper 复核：358.875 秒、18 镜、54 条字幕、完整 AV 解码通过；没有逐句人工听审保证。这是来源制作记录，不是本机重新运行模型的证据。0.6B CustomVoice 不支持额外风格指令；Linux BF16 速度和安装方式也不承诺适用于 Mac。模型大小、许可及未知成本见音频说明。新增[可选离线配音工具](docs/optional-voice.md)：Qwen/Whisper 适配器、固定权重校验、停顿与语义字幕估计、静音处拼接；npx 同样可调用。模型需另行准备，默认不下载。

素材打包不会上传。核对事实、版权、隐私、账号和全片 AV 后，只有收到明确授权才交由已有浏览器能力或人工发布，再记录真实回执。未实现、也不伪称存在通用小红书发布 API。

[观看 15 秒混合视觉示例](docs/mixed-demo.mp4)，或用 `init my-video --example mixed` 取得分镜。时间线示例是明确标记的假想项目进程，未冒充历史事实。

## 开源范围

[MIT 许可](LICENSE)覆盖我们原创的代码、文档和代码绘制的演示画面。第三方依赖、模型、声音、字体和素材保留各自许可，见 [NOTICE.md](NOTICE.md)。不打包模型权重和字体。制作视频不代表授权向社交平台发布，本项目也没有外部发布功能。
