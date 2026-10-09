---
name: qwen3-tts-voice-batch
description: 通过 ComfyUI API 批量生成 Qwen3-TTS Voice Design 音色库（不同年龄/性别/音色的角色语音），并产出可试听的对比页面。当用户要用 ComfyUI 上的 Qwen3-TTS / TTS-Audio-Suite 批量做音色设计、克隆角色、批量配音，或需要复用已保存的 Character Voice 时使用。
agent_created: true
---

# Qwen3-TTS 批量音色生成（ComfyUI）

## 适用前提

- ComfyUI 装了 `TTS-Audio-Suite` 自定义节点（本例：`http://192.168.31.197:10003`）。
- 有一个 Voice Design 的 API 格式工作流（含 `Qwen3TTSEngineNode` + `UnifiedVoiceDesignerNode` + `SaveCharacterVoiceNode`）。

## 核心 API 流程

1. `GET /system_stats` —— 探活，同时能看到 `--output-directory`（可能是 UNC 网络路径，本地直读不了）。
2. `GET /object_info/<NodeName>` —— 确认参数名与可选项，别靠猜。
3. `POST /prompt {"prompt": <graph>, "client_id": <uuid>}` —— 提交，返回 `prompt_id`。
4. 轮询 `GET /history/<prompt_id>`，直到返回值里出现该 `prompt_id`。
5. `GET /view?filename=..&subfolder=..&type=output` —— **必须**用这个下载音频，输出目录可能是 NAS UNC 路径。

## 关键参数坑

- `Qwen3TTSEngineNode.model_variant` 必须选 `Voice Design - 1.7B VoiceDesign`，否则 Voice Designer 报错。
- `Qwen3TTSEngineNode.language` 默认 `English`，中文文案要显式设 `Chinese`。
- `voice_preset` 对 VoiceDesign 模型无效，忽略即可。
- `UnifiedVoiceDesignerNode`：`reference_text`（用来生成参考音频的样本文本，建议 10s 以上、含陈述/疑问/感叹以便暴露语调）、`seed`（0=随机；固定非零 seed 可复现）、`voice_instruction`（音色描述，越具体越好：年龄+性别+音高+音色质感+语速+语调+气质+排除项）。
- `SaveCharacterVoiceNode.overwrite_character` 设 true 才会覆盖同名角色，否则会存成 `name_1`。角色文件落在 ComfyUI 的 `models/voices`。
- `character_name` 用英文 key 命名，避免 NAS/Windows 路径编码问题。
- **必须串行提交**：单 GPU + Shared Runtime，并发会被排队或出错。

## 实测性能（RTX 4090）

- 单条 18–38s（老年/沙哑类最慢），20 个音色约 8 分钟。
- 老年角色语速慢，flac 文件明显更大（700KB vs 370KB），属正常。

## 环境注意

managed python 无 `requests`，用 `C:/Users/AI-Space001/miniconda3/python.exe` 跑脚本。

## 音色矩阵设计经验

按「年龄组 × 性别 × 音色标签」组织，每个组合写一段 80–120 字的中文 voice_instruction，
必须包含：年龄、性别、音高低、音色质感（清亮/醇厚/沙哑/磁性）、语速、语调起伏、气质类比（像电台主播/老者）、排除项（无沙哑/不油腻）。

### 儿童要细分到具体岁数

3 / 6 / 8 岁差别很大，别只写一个"儿童"：
- 3 岁：音调极高、吐字含混、句子短且碎、夹着"嗯/那个"、气声重
- 6 岁：音调高、吐字清楚但奶声奶气、句尾上扬
- 8 岁：吐字已清晰标准、保留童声稚嫩、朗读感强

### 方言（关键）

**reference_text 必须也写成方言**，否则模型只会用方言口音念普通话书面语（"塑料方言"）。
例：东北话要写"今天天气老好了，咋样，咱俩去公园溜达溜达呗？……啥？你说明儿个就走啊？"
粤语要写"今日天气真系好，你要唔要一齐去公园行下？……咩话？你听日就要出发呀？"

已验证可用：东北 / 四川 / 粤语 / 北京 / 上海 / 河南 / 台湾腔。instruction 里要写清方言片区、
典型音变（平翘舌不分、n/l 不分、儿化、入声、连续变调）和句尾语气词（呗/噻/嘞/啦/欸）。
方言准确度靠训练数据，VoiceDesign 不保证，**务必让用户试听确认**。

### 情绪变体

换用一段"情绪弹性大"的专用文本，别用中性陈述句（"今天天气真不错"配愤怒会很怪）：
  "啊？真的吗？我……我简直不敢相信。等一下，你说的是认真的？好吧，既然是这样，那就这样吧。"
靠 instruction 描述演播状态：音高、语速、气息、咬字力度、句尾走向、身体状态（哽咽/倒吸气/笑意/喘息）。

## 批量前先看队列

`GET /queue` —— 如果 `queue_running` 里有**别人**的工作流（尤其带 ASR/SRT 的），
它会阻塞你后续所有提交（实测被一个 25 节点的 TTS+SRT 任务卡了 952s）。
不要擅自清别人的队列，先告知用户或错峰跑。

## 可复用脚本

`qwen3_tts_batch/batch_voice_design.py`（支持 `--only key1,key2` / `--limit` / `--seed0` / `--lang`），
`qwen3_tts_batch/make_preview.py` 读 manifest.csv 生成 `index.html` 分组试听页（grid + <audio> + 描述折叠）。
