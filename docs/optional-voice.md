# 可选离线配音、ASR 与停顿字幕 / Optional offline voice tools

这部分来自已完成制作流程的源码提炼。它不是默认依赖；无声视频和导入 WAV 的主流程不需要大模型。新增工具不下载权重，不调用付费 API，不上传音频，也不发布视频。模型环境由使用者另外准备。

## 已验证到哪一步

- **上游原制作**：Linux x86 / AMD AVX512 BF16，Qwen3-TTS 0.6B CustomVoice Serena，CPU bfloat16 + SDPA / 6 线程；Whisper small CPU float32 + eager / 3 线程。最终 358.875 秒、18 镜、54 条连续字幕、1080×1920 / 24 fps / H.264 + AAC 单声道 48 kHz，记录了完整解码及局部无提示 ASR 检查。没有逐句人工听审记录，不能保证自然度、发音和语义同步。
- **源码可复用部分**：停顿/文字权重动态规划、ASR 语义边界支持、安静处拼接、固定权重哈希、离线和遥测控制。原来的题材、讲稿、音频、私有目录与生产记录未打包。
- **本仓库**：参数化适配器、合成信号回归、离线保护、哈希拒绝、字幕到现有渲染器的连通性、打包与 npx 验证。没有在本机重新运行 Qwen/Whisper 权重推理。上游参数化 ASR 副本也只做过语法/help 检查，不能据此宣称全新环境复现。

0.6B Serena 不接受额外风格指令；本工具未加入此功能。Linux BF16、轮子与运行速度不迁移承诺到 macOS、GPU 或其他语言。未知设备先做短试听并记录耗时、内存和听感。

## 环境与许可

轻量音频工具可以独立安装，不含 Torch/Qwen/Whisper：

```bash
python -m pip install -r requirements.txt -r requirements-voice-tools.txt
python scripts/voice.py voice-doctor
# npm exec -- sketch-video voice-doctor --python /path/to/python
```

`voice-doctor` 只检查模块是否存在，不导入模型、不验证推理兼容性。numpy、SciPy、soundfile 和 pypinyin 分别保留自己的许可；soundfile 的 wheel 还可能附带 libsndfile，不能用本项目 MIT 替代其条款。

原 Linux 制作环境的关键版本为 Python 3.12、torch/torchaudio 2.8.0+cpu、qwen-tts 0.1.1、transformers 4.57.3、onnxruntime 1.31.0、pypinyin 0.55.0。这是来源环境记录，不是经本仓库重新安装验证的跨平台锁文件。请在独立模型虚拟环境中按 [Qwen 官方安装说明](https://github.com/QwenLM/Qwen3-TTS)选择适用版本；不要在 Mac 上照抄 Linux CPU wheel。模型环境若要运行整个流水线，也需安装本项目基础依赖和轻量音频依赖。

下面是原环境使用的 Linux CPU 版本组合，供已批准准备模型环境时参考；本仓库没有重新安装执行，也不是 macOS 安装配方。这会安装较大的运行时依赖，须由使用者主动执行，仍不会取得模型权重：

```bash
python3.12 -m venv .voice-env
source .voice-env/bin/activate
python -m pip install torch==2.8.0+cpu torchaudio==2.8.0+cpu --index-url https://download.pytorch.org/whl/cpu
python -m pip install qwen-tts==0.1.1 transformers==4.57.3
python -m pip install -r requirements.txt -r requirements-voice-tools.txt
```

这只固定关键引擎版本，不是所有传递依赖的复现锁。完成 `voice-doctor`、固定权重校验后仍需在自己的设备做短句推理和听审。


| 本地模型 | 固定来源 revision | 许可 / 存储边界 |
| --- | --- | --- |
| Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice | `85e237c12c027371202489a0ec509ded67b5e4b5` | [Apache-2.0](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice/blob/85e237c12c027371202489a0ec509ded67b5e4b5/LICENSE)；上游记录约 2.5 GB 模型与 tokenizer，不含运行时；本仓库未测下载字节数。 |
| openai/whisper-small | `973afd24965f72e36ca33b3055d56a652f456b4d` | [Whisper MIT](https://github.com/openai/whisper/blob/main/LICENSE)；244M 参数，不含运行时；本仓库未测下载字节数。 |

模型与 tokenizer 需要在**另外取得下载授权后**，从这些官方固定 revision 获取完整快照，并保存其 LICENSE/NOTICE。此工具没有下载子命令。配置 JSON 与 tokenizer 也须来自可信快照：内置校验覆盖列出的 safetensors 权重，并非对全部文件的密码学认证。配置中的 `download_bytes: null` 表示未知。

```bash
python scripts/voice.py verify-model qwen --model-dir /path/to/local/qwen-model
python scripts/voice.py verify-model whisper --model-dir /path/to/local/whisper-small
```

权重哈希在 [voice.py](../scripts/voice.py) 中固定：Qwen 主权重和 speech_tokenizer 权重均检查，Whisper 检查主 safetensors。缺文件或哈希不符会在导入 ML 之前退出；不接受远程模型 id，不自动改用下载。所有 `from_pretrained` 设置 `local_files_only=True`、`trust_remote_code=False`，模型使用 safetensors。

在任何 ML 导入之前，工具强制设置：`ORT_DISABLE_TELEMETRY=1`、`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`、`HF_HUB_DISABLE_TELEMETRY=1`、`HF_HUB_DISABLE_IMPLICIT_TOKEN=1`。ONNX Runtime 的初始化时序依据 [官方隐私说明](https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md#disabling-telemetry)。HF 离线与 ORT 遥测控制是不同开关；这不是操作系统网络沙箱，也未做网络抓包审计。自定义适配器本身仍需可信审阅。

## 生成配音并重排时间线

可以直接运行，也可以用同名 npx 命令（所有命令支持 `--python`）：

```bash
python scripts/voice.py qwen --model-dir /path/to/local/qwen-model \
  --text-file scene-0.txt --output scene-0.wav --voice Serena --language Chinese \
  --dtype bfloat16 --threads 6
```

默认 float32；只有检测到 Linux `avx512_bf16` 才使用请求的 bfloat16，否则退回 float32。`auto` 也保守选择 float32。Qwen 逐场景生成完整段落，不按旧字幕时间拉伸/截断语音。输出新 WAV 和含文本/音频哈希、耗时、设备、dtype 的 JSON；达到 token 上限或无效波形会失败。先试听短句，确认声音与许可适合该制作；参数或数值检查不能代替听审。

可用 [Qwen 适配器配置](../examples/adapters/qwen.json)接入已有 `tts` 命令。复制配置，把 `/path/to/local/qwen-model` 换成真实路径；`{python}` 与 `{adapter_script}` 会由包解析，支持安装后路径。示例限定 Linux，其他设备先做单独试验。示例请求：[request.zh.json](../examples/adapters/request.zh.json)，与水循环分镜对应。

```bash
# 默认只计划；确认本地模型、试听与配置后才加 --execute
python scripts/production.py tts examples/adapters/request.zh.json \
  --adapter my-qwen-adapter.json --out build/speech --execute
python scripts/voice.py align-captions examples/water-cycle.zh.json \
  --audio build/speech/audio.json --out build/timing
python scripts/production.py prepare-audio examples/water-cycle.zh.json \
  --audio build/timing/audio.json --out build/prepared
# 后续 render prepared/retimed.json → mux → verify-av → package，见完整操作示例。
```

`align-captions` 只接受按顺序覆盖全部场景的 WAV manifest。可在每个分镜加入与 `captions` 等长的 `spoken_captions`（数字读法、缩写展开等）；显示文字不变，估计使用实际说法。否则直接使用显示字幕。长场景仍须遵守渲染器的 120 秒限制。

输出 `scene-000.json` 等报告与可直接输入 `prepare-audio` 的 `audio.json`。源音频与讲稿哈希保留在每个 clip 中；即使音长相同，修改音频或讲稿也会导致 `prepare-audio` 拒绝旧估计，必须重新对齐。识别过程中源音频变化也会导致 ASR 拒绝保存结果。动态规划结合文字权重、标点、能量停顿和最短时长；没有停顿时回退并降低置信度。结果是 **energy_pause_estimate**，不自动标为人工审核或强制对齐。最终帧量化仍由主流程完成，只在尾部补齐帧量化差额（场景至少一秒）。

## 无提示 ASR 与语义边界

```bash
python scripts/voice.py whisper --model-dir /path/to/local/whisper-small \
  --audio scene-0.wav --expected-text-file expected-scene-0.txt --output scene-0-asr.json
```

`expected-scene-0.txt` 是该场景所有 `spoken_captions` 无分隔连接后保存的 UTF-8 文本（未设置则连接显示字幕）。它只用于报告中的哈希绑定，**不传给识别模型作提示**。每场景单独识别；Whisper 固定 CPU float32 / eager / 3 线程，输出供复核的 segments，缺时间戳则失败，不编造字级时刻。通用 [Whisper 配置](../examples/adapters/whisper.json)也可用于 `asr --execute`；语义边界步骤另外要求带 expected-text 哈希的逐场景报告。

```json
{"scenes":[{"scene":0,"transcript":"scene-0-asr.json"},{"scene":1,"transcript":"scene-1-asr.json"},{"scene":2,"transcript":"scene-2-asr.json"}]}
```

将上面的 manifest 保存为 `asr-scenes.json`，路径相对该文件。然后：

```bash
python scripts/voice.py align-captions story.json --audio audio.json \
  --asr-manifest asr-scenes.json --out build/semantic-timing
```

语义步骤拒绝音频哈希、原文哈希或音长不一致、非明确无提示的报告。拼音映射用于容忍部分中文同音识别差异；只有匹配覆盖足够、字幕边界落在真实 ASR chunk 边缘、且 ASR 间隙与波形停顿有交集时才提高支持等级。Whisper 中文 chunk 常是短语，不把区间内部插值当独立测量的字级时间。低/中/高只是启发式支持，始终要求听审。生成标签为 **semantic_pause_estimate**。

## 安静处拼接

仅在实际听过并确认同音色、同语义位置与真实静音后使用，保留原始 WAV：

```bash
python scripts/voice.py splice-audio --prefix first.wav --prefix-cut 12.5 \
  --suffix revised.wav --suffix-cut 2.4 --output composite.wav
```

只接受有限单声道、相同采样率、源文件内部切点，默认接缝两侧 20 ms RMS 均低于 −40 dBFS。短淡出/淡入不叠加、不变速、不新增静音；保存来源哈希、样本数与接缝报告，拒绝覆盖输入/已有输出。能量低不能证明没有音素，因此工具不会自行批准语义边界。复合音频会改变哈希，必须重新 ASR、字幕对齐、渲染和全片复核。

## English usage notes

These are optional local CPU adapters and audio tools, extracted from a completed upstream production. Install `requirements-voice-tools.txt` separately for NumPy/SoundFile/SciPy/pypinyin; acquire the engines and exact model snapshots separately only with authorization. No downloader, weights, fonts, recorded speech or uploader is bundled. Use the same commands through `sketch-video` / npx with `--python` pointing at your prepared environment.

The upstream Linux Qwen/Whisper run is provenance, not a fresh inference result for this portable wrapper. Current repository checks cover synthetic pause alignment, semantic/hash guards, quiet splicing, packaging and the model-free media pipeline. Neither human listening nor a new local Qwen/Whisper inference is claimed. Qwen 0.6B Serena has no extra style-instruction support. macOS/GPU compatibility and performance remain unverified.

All five offline/telemetry flags are set before ML imports. Weight hashes fail closed; local-only, no remote code and safetensors are required. Telemetry flags are not a network sandbox. `align-captions` outputs estimated continuous clip-relative caption times usable by `prepare-audio`; optional ASR context must match audio/text hashes and duration. Estimates and ASR phrases are not forced alignment or human approval. Splicing requires quiet, semantically reviewed source cuts and writes new files only. Continue through render, mux, full AV verification and human review before any separately authorized publication.
