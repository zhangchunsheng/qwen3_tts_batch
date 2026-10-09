---
name: qwen3-voice-design
description: 用 ComfyUI 上的 Qwen3-TTS Voice Design 按音色描述生成一段试听音频，并把音频文件下载到本地交给用户。当用户描述一个声音（"成熟男声""甜美女声""东北话大爷""愤怒的语气"）想要听效果、想试音色、想给短视频/播客挑配音声线时使用。只做单条；要批量出音色库用 qwen3-tts-voice-batch。
agent_created: true
---

# Qwen3-TTS Voice Design（单音色试听）

## 这条 skill 干什么

用户给一段**音色描述** → 调本地 ComfyUI 的 Qwen3-TTS → 生成一段约 10 秒的样音 → 下载到本地 → `present_files` 交给用户试听。

## 前置

- ComfyUI：`http://192.168.31.197:10003`（装了 `TTS-Audio-Suite`，含 `Qwen3TTSEngineNode` / `UnifiedVoiceDesignerNode`）。
- 输出目录是 UNC 网络路径（`\\NAS65A682\Web\images`），**本地直读不了**，必须走 `/view` 下载 —— 脚本已处理。

## 执行方式（只有这一条路径）

```bash
"C:/Users/AI-Space001/.workbuddy/binaries/python/versions/3.13.12/python.exe" \
  "C:/Users/AI-Space001/.workbuddy/skills/qwen3-voice-design/scripts/voice_design.py" \
  --instruct "<音色描述>" \
  [--text "<样本文本>"] [--lang Chinese] [--seed 1] \
  [--save-as <英文key>] --out "<绝对路径>.flac"
```

脚本只用标准库（urllib），managed python 可直接跑，不需要 requests。
它内部做：探活 → 看队列 → 提交 → 轮询 history → `/view` 下载 → 打印最终路径。

参数说明：
- `--instruct` 音色描述，**越具体越好**（见下）。
- `--text` 默认是一段含陈述/疑问/感叹的中文文本，约 10 秒，够暴露语调，一般不用改。
- `--seed` 默认 1（可复现）；换 seed 可得到同一描述的另一种演绎，用户不满意时**先换 seed 再改描述**。
- `--save-as` 可选，把音色存成 ComfyUI Character Voice 供后续复用（key 用英文）。

## 拿到文件后

1. 用 `present_files` 把音频文件交给用户（这是交付动作，不能省）。
2. 一句话说明用了哪段描述、seed 多少，方便用户说"再温柔一点"或"换个 seed"。

## 音色描述怎么写（决定成败）

一段好的 `--instruct` 要覆盖这些维度，缺一项效果就掉一档：

> 年龄 + 性别 + 音高高低 + 音色质感（清亮/醇厚/沙哑/磁性/奶声） + 语速 + 语调起伏 + 气质类比（像电台主播/老者/邻家女孩） + 排除项（无沙哑、不油腻）

示例：
```
成熟中年男性声线，低沉醇厚，嗓音带有轻微自然胸腔共鸣，语速平缓从容，吐字清晰标准，
语调稳定克制，没有夸张起伏。气质沉稳可靠、温和内敛，略带一丝阅历感，无沙哑破音，
不生硬冰冷，也不油腻，像阅历丰富的儒雅男士，说话松弛自然，停顿合理。
```

### 方言：reference_text 必须一起改成方言
否则模型只用方言口音念普通话书面语（塑料方言）。
东北话示例 `--text "今天天气老好了，咋样，咱俩去公园溜达溜达呗？……啥？你说明儿个就走啊？"`
粤语示例 `--text "今日天气真系好，你要唔要一齐去公园行下？……咩话？你听日就要出发呀？"`
已验证：东北 / 四川 / 粤语 / 北京 / 上海 / 河南 / 台湾腔。**准确度不保证，务必让用户试听确认。**

### 情绪变体：换一段情绪弹性大的文本
中性句配"愤怒"会很怪。用：
```
啊？真的吗？我……我简直不敢相信。等一下，你说的是认真的？好吧，既然是这样，那就这样吧。
```
再在 instruct 里写演播状态：音高、语速、气息、咬字力度、句尾走向、身体状态（哽咽/倒吸气/笑意/喘息）。

### 儿童要细分岁数
3 岁（音调极高、吐字含混、气声重、夹"嗯/那个"）/ 6 岁（奶声奶气、句尾上扬）/ 8 岁（吐字清晰、朗读感强）差别很大，别只写"儿童"。

## 实测与已知坑

- 单条约 **20–55 秒**（RTX 4090，老年/沙哑类最慢）。跑之前脚本会打印队列状态，队列里有别人的任务会排队等待，**不要清别人的队列**。
- 必须串行：单 GPU + Shared Runtime，并发会排队或出错。
- `model_variant` 一定是 `Voice Design - 1.7B VoiceDesign`，否则 Voice Designer 报错；`voice_preset` 对 VoiceDesign 无效，忽略即可。
- `language` 中文必须显式设 `Chinese`（默认 English）。
- 输出是 flac；若用户要 mp3，用 ffmpeg 转：`ffmpeg -i in.flac -b:a 192k out.mp3`。
- 用户不满意时的排查顺序：换 seed → 改样本文本（更贴合使用场景）→ 细化 instruct（补缺失维度/排除项）。

## 文件

- `scripts/voice_design.py` —— 主脚本（提交 + 轮询 + 下载）。
- `workflows/voice_design_qwen3_api.json` —— API 格式工作流原稿，脚本里已内联等价图，仅作参考/手工改图用。
