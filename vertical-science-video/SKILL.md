---
name: vertical-science-video
description: 用本地 OpenAI 兼容生图接口 + edge-tts + ffmpeg 制作竖屏（9:16）科普动画短视频。当用户要给一段科普/知识/解说文案做成 1-3 分钟竖屏短视频、要求配音+字幕+镜头运动，或提到"生图接口做视频""批量出图配旁白""720p 竖屏成片"时使用。也适用于把一段图文资料转成口播短视频。
agent_created: true
---

# 竖屏科普动画短视频流水线

把一段科普文案变成 **720×1280 / 30fps / 配音 + 字幕 + 运镜** 的成片。
纯本地管线：生图走内网 OpenAI 兼容接口，配音走 edge-tts，合成走 ffmpeg。**不需要视频生成模型**。

## 何时用

- 用户给一段科普/知识类文案，要求做成 1-3 分钟竖屏短视频
- 内网有 ComfyUI 或其它 OpenAI 兼容生图接口（`/v1/images/generations`，返回 `b64_json`）
- 用户的"生视频"接口不可用时（这条管线是最稳的兜底方案）

## 前置探测（永远先做）

```bash
curl -s -m 20 http://HOST:PORT/v1/models          # 看有哪些模型
curl -s -m 20 http://HOST:PORT/                    # 看是不是 ComfyUI
ffmpeg -version && ffprobe -version                # 合成依赖
```

端口连不上就探相邻端口（用户常同时给多个端口，其中视频口可能是挂的）。

### 别只看 /v1/models 就判定"不能生视频"

**`/v1/models` 不区分模态能力**，很多网关的视频能力只挂在 **MCP 工具** 上。
只要网关是 `comfyui-roundabout`（或任何暴露 `/mcp` 的 ComfyUI 网关），必须再查 MCP：

1. `POST /mcp`，头带 `Content-Type: application/json` + `Accept: application/json, text/event-stream`
2. `initialize` → **从响应头取 `mcp-session-id` 并在后续每个请求回传**，否则 `400 Missing session ID`
3. `tools/list` → 找 `generate_video`；`tools/call list_models` → 看每个模型 `mode: image|video`

响应是 SSE：`data: {...}`，用 `text.find("data:")` 之后整段 `json.loads`（**不要按行取**，JSON 会跨行）。
可视化页面：`GET /roundabout/view` 或调 `get_view_url` 工具。

### minimax-h3 实测（comfyui-roundabout 网关）

| 项 | 结论 |
|---|---|
| 可用模型 | `minimax-h3`（25 步）。**注意：turbo 系列是否可用取决于网关 models.yaml**，用 MCP `list_models` 实测，别信旧结论 |
| `minimax-h3-turbo`（8 步）| 实测**可用**且质量过关（无乱码、运镜平滑），3s 片段 ≈70s 出片（**≈24 倍实时**），比 base 快 5 倍多。优先用它 |
| 竖屏 | 原生支持，`size="720p-9:16"` → **720×1280 / 24fps** |
| 时长 | `duration` 1–15s |
| 返回 | 异步模式给 task_id；产物是 **url**（`/view?filename=...&subfolder=video&type=output`） |
| 长任务 | ⚠️ **必须传 `background="pending"`** |

 turbo 速度下全视频方案可行：2 分钟成片（120s 素材）≈ 48 分钟生成。
若混合，真视频时长 × 24 就是生成耗时。

### 轮询任务的两个坑

- 判定完成**只能看 `status` 字段的值**（in `{"completed","succeeded",...}`），不能 `"error" in json_str`——
  正常返回里就有 `"error": null`，会误判成失败提前退出。
- 每次新建会话都要重新 `initialize` 拿新的 `mcp-session-id`（旧 session 会过期）。

### 视频生成的六个坑（每条都实际踩过）

**坑 A：不传 `background="pending"` 会拿到"孤儿任务"**
默认同步模式会挂住客户端约 300s 才返回，而且任务**不进网关异步任务表**
（`has_workflow: false`），之后 `get_task` 一律报 `Error executing tool get_task`。
补救：用 ComfyUI 原生 `GET /history/<prompt_id>` 读 `outputs` 拿 filename，再
`GET /view?filename=...` 下载。但正解是一开始就传 `background="pending"`。

**坑 B：`reference_images` 传大图直接失败**
传 1080×1920 PNG 的 dataURL（约 1.8MB）→ 400。**视频一律走纯文本提示词**，
靠全局 style 后缀对齐风格。

**坑 C：片段长度必须算上场景间隙**
`clip_dur = 口播时长 + gap`（最后一镜 `+ tail`）。只做口播时长会让画面比音轨短
`gap*(n-1)+tail` 秒（16 镜约 7.8s），字幕整体错位、结尾黑屏。
**合成后必须核对 `ffprobe duration` 与 `build_timeline` 算出的 total 是否一致。**

**坑 D：x264 在内存紧张时崩**
与视频生成并行合成时 ffmpeg 报 `x264 [error]: malloc of size N failed` /
`Error while opening encoder`。给每处 `-c:v libx264` 加 `-threads 2`，
并且**合成前确认没有视频任务在跑**。

**坑 E：视频模型会自己往画面里加乱码文字**
提示词里出现 `scan sheet / document / calendar / chart / infographic` 这类"平面纸状"物件时，
H3 会往上面写英文乱码（实测出现 `Screensustr Eseoening`）。
**规避：视频镜头的提示词要写成电影感的立体画面（cinematic / volumetric / 3D form），
明确 `no text, no letters, no labels, no paper`。**
静帧分镜可以继续用 infographic/diagram 风格，但**真视频镜头必须换成纯视觉的 prompt**。
出片后抽帧检查，发现乱码就退回静帧+运镜——静帧+运镜是永远干净的兜底。

**坑 F：视频任务不能并发**
4 个任务同时提交（每口 2 个）→ 3 个失败，报
`ComfyUI execution failed at node 136 (MiniMaxH3ReferenceToVideo): RuntimeError: hostbuf_file_reader_read failed`（code 502）。
这是多任务同时加载模型导致的资源冲突，**与端口无关**。
**必须严格串行提交（一次一个任务）**，实测串行后全部成功。
耗时参考：h3-turbo 约 **27 倍实时**（12s 片段 → 321s）。实测 7s→160~170s、12s→320s、13s→380s，即 **23~29 倍实时**。

**坑 G：真视频里的人体会被渲染成裸体（健康类选题的红线）**
`translucent human silhouette` / `human figure` 这类词，h3-turbo 会渲染成**清晰的裸体人体**（实测女性轮廓，
胸部与下体可辨）。肿瘤/乳腺/妇科等健康科普一旦用上就是事故。
**规避：真视频镜头的提示词里彻底不出现人体**——连 `silhouette` 都算。改写成纯抽象科技画面
（发光神经/血管网络、粒子流、玻璃球群），并在负面词写 `no people, no human figure, no face`。
例外：**人体占比很小时的远距离逆光剪影是安全的**（实测结尾麦田中的小人没有细节问题）。
静帧走的是另一条渲染路径，静帧的人形示意图向来干净——**真人形画面优先用静帧+运镜，别交给视频模型**。

**坑 H：`different colors` 会让画面跑色**
提示词写 `each holding a different soft colored glow`，玻璃球立刻变彩虹色（紫/绿/橙），
与全片"青绿+琥珀"基调直接冲突，整段看起来像另一支片子。
**统一色调的片子里，视频镜头只写主色 + 一个强调色**，不要出现 different / various colors。

**坑 I：首轮偶发失败，原样重试即可**
批量串行时首个任务可能报 `MiniMaxH3ReferenceToVideo` 执行失败（同坑 F 的资源冲突，不是提示词问题）。
**不要改提示词**，隔几分钟单独重跑同一镜，一次就过（实测 160s 出片）。

⚠️ 视频生成仍只适合点缀（h3-turbo 出现后成本大降，但风格漂移与自加乱码的风险还在）。
16 镜里用 2–4 镜真视频（开场、一个演示、结尾）性价比仍最高；全视频 ≈48 分钟也可接受。


### 依赖安装（隔离环境，别污染用户环境）

```bash
PY=C:/Users/<user>/.workbuddy/binaries/python/versions/3.13.12/python.exe
$PY -m venv C:/Users/<user>/.workbuddy/binaries/python/envs/default
C:/Users/<user>/.workbuddy/binaries/python/envs/default/Scripts/python.exe -m pip install edge-tts pillow numpy requests
```
先单独试一条 edge-tts（确认能连微软的 TTS 端点），再跑全量。

## 五个阶段

### 1. 写 `scenes.json`

结构：全局 `style`（**统一风格后缀**，每条 prompt 都拼在末尾）+ `voice` + `rate` + `scenes[]`。

每个场景：`id` / `narration`（口播句）/ `prompt`（只写画面内容，不写风格）/ `motion`（`in|out|panup|pandown`）。

要点：
- **风格后缀必须固定**，否则 15 张图会风格漂移。必含 `no text, no letters, no numbers, no watermark, no logo`——否则模型会画出一堆乱码中文。
- **总字数控制**：中文 TTS 约 4.7 字/秒（rate=+8%）。2 分钟 ≈ 530 字，拆 13-15 个分镜最舒服。
- 场景间留 `gap`（默认 0.35s），最后留 `TAIL`（0.9s）。
- 画面提示词写成"抽象解剖图 / 图标级"比写成"写实照片"更稳、更统一、更像科普动画。

### 2. 批量出图 `scripts/gen_all.py`

- **分辨率策略**：用 `size=1080x1920` 出图（比 720×1280 更锐），交给 ffmpeg 降采样到 720×1280。
- `z-image-turbo` 实测 1080×1920 ≈ 7s/张，15 张串行约 2 分钟。
- ⚠️ **多个端口若 `/v1/models` 列表完全相同，说明它们背后是同一个 ComfyUI**（只是网关
  开了两个端口），**并发请求会被网关去重：不同 prompt 返回同一张图**。
  实测 192.168.31.197:10003/10004 用 `ThreadPoolExecutor(max_workers=4)` 出 19 张，
  **只有 3 张唯一**（s01=s04、s05=s06、s07=s08……成对完全一样，md5 相同）。
  正解：**`WORKERS = 1` 串行**，并给每个分镜传**不同 seed**（如 `1000 + id*137`）。
  串行 19 张 1080×1920 约 **136 秒**（≈7.2s/张），19/19 唯一。
  **出图后必须 `md5sum images/*.png | awk '{print $1}' | sort -u | wc -l` 核对唯一数**，
  等于分镜数才往下走——只看文件大小相同也能提前发现（重复图 size 完全一致）。
- 每张 4 次重试；已存在的图跳过（方便只返修个别分镜）。
- 出图后先 **md5 查重**（唯一数必须 = 分镜数），再**拼成 montage 看一眼**（见下方检查清单）。

### 3. 配音 + 时长 `scripts/tts_build.py`

- edge-tts 逐分镜存 mp3，用 `ffprobe -show_entries format=duration` 取**真实时长**
- 输出 `timings.json`，含每个分镜的 `start` / `dur`
- **画面时长必须由配音时长驱动**，不要反过来硬凑
- 全跑完打印总时长，落在目标区间（2 分钟 → 115~125s）再往下走

### 4. 合成 `scripts/assemble.py`

1. 每个分镜做成独立片段：`scale → crop → zoompan` 运镜，`-loop 1 -framerate 30 -t D`
2. concat demuxer 拼接片段（同名参数，`-c copy`）
3. 配音按 `s01 + silence + s02 + ...` 拼接（静音用 `anullsrc` 生成，码率参数要和 edge-tts 输出一致才能 `-c copy`）
4. 生成 ASS 字幕 → `subtitles` 滤镜烧录 + 首尾 `fade`
5. `apad,atrim` 把音轨补齐到视频总长

### 5. 验证（必做）

```bash
# 抽帧检查
ffmpeg -ss 25 -i out.mp4 -frames:v 1 check/f25.png -y
# 拼 montage 一次看完所有分镜
```

**拼 montage 的正确写法（本机实测）**：
- 本机 ffmpeg **不支持 `-pattern_type glob`**（报 `globbing is not supported`）
- `tile` 滤镜**没有 `inputs` 选项**（报 `Option not found`），传多个 `-i` 会报
  `More input link labels specified for filter 'tile' than it has inputs`
- 正解：多个 `-i` + `scale` 后 `hstack=inputs=N` 分行，再 `vstack=inputs=M` 合成。
  凑不满一行的格子用 `-f lavfi -i color=c=black:s=WxH:d=1` 补黑块。
- ⚠️ 实测 ffmpeg 多输入 hstack/vstack 拼图**可能直接崩溃**（exit 127/2，无任何错误信息，
  4 输入能过、12 输入挂）。**更稳的兜底：用 PIL 拼图**（venv 里必有 Pillow）：
  `Image.open(...).resize((tw,th))` → `paste` 到网格 → `save(quality=88)`，一次成功零玄学。
  视频抽帧网格建议直接跳过 ffmpeg 走 PIL。

**检查清单**：
- [ ] 字幕有没有横向溢出？→ 看 `WrapStyle` 和单条字数
- [ ] 字幕有没有被画面底部裁掉？→ 看 `MarginV`
- [ ] 顶部标签文字对不对（别串场）
- [ ] 有没有画面明显崩掉的分镜（手部、器械、比例）→ 改 prompt 单独返修
- [ ] `ffprobe` 确认 `width/height/r_frame_rate/duration`

## 两个必踩的坑

**坑 1：`fontsdir` 的盘符冒号必须转义**
```
subtitles='C\:/path/sub.ass':fontsdir='C\:/Windows/Fonts'
```
不转义会报 `Unable to open /Windows/Fonts` + `Permission denied`。两个参数都要转义。

**坑 2：ASS `WrapStyle` 别用 2**
`WrapStyle: 2` = 不自动换行，长中文句会横向冲出画面被裁。
中文竖屏字幕配置：
```
WrapStyle: 0
Style: Sub,Microsoft YaHei,38,...,Alignment=2,MarginL=48,MarginR=48,MarginV=150
```
- 字号 38 / 画宽 720 / 左右边距 48 → **单条字幕上限 16 字**，正好一行
- 按标点（`，。；、：？！`）切分再合并到 16 字以内，按字数比例分配时间
- **写分镜文案时就要埋好逗号**：一整句中间没有标点就会超过 16 字（实测
  `是体重在短时间内不明原因地明显下降。` = 18 字 → 折两行），split_cues 没法自动切开。
  改文案要重跑 tts_build + assemble，所以第一遍就写对更省事。
- 最后一条字幕延伸到下一分镜开始前 0.06s，下一分镜首条延后 0.12s，避免静音间隙字幕闪断、也不会重叠

## 运镜写法（zoompan）

`d=1` + `-loop 1 -framerate 30`，用 `on`（输出帧号）驱动：
- `in`：`z='1+0.14*on/N'`，居中
- `out`：`z='1.14-0.14*on/N'`，居中
- `panup`：`z='1.12'`，`y='(ih-ih/zoom)*(1-on/N)'`
- `pandown`：`z='1.12'`，`y='(ih-ih/zoom)*(on/N)'`

源图先放大到 1080×1920 再 zoompan，输出 `s=720x1280`，等效超采样，边缘更干净。
运镜类型在相邻分镜间交替，避免连续同向推拉造成疲劳。

## 背景音乐

默认**不加**。用 ffmpeg 合成 pad 听起来廉价，比没有更糟。
用户提供了 BGM 文件再用 `amix` 以 `-22dB` 左右混入。要主动提醒用户这个选项。

## 脚本

`gen_image.py`（单张出图，PORTS 列表自动切换）/ `gen_all.py`（**双口并行**批量，
`gen_all.py 14 16` 可只返修指定镜）→ `tts_build.py`（配音+时长）→
`assemble.py`（合成，**`videos/s{id}.mp4` 存在时自动用真视频片段替代静帧**）→ `storyboard.py`（分镜审阅表）

视频支线（可选）：
`scripts/mcp_probe.py`（列 MCP 工具）/ `mcp_caps.py`（查模型能力）/ `gen_videos.py`（批量生视频）/
`mcp_task.py`（轮询任务）/ `harvest.py`（按 prompt_id 捞产物）/ `mcp_vtest.py`（单次参数验证）

改 `common.py` 的 `ROOT`/`API`/`MODEL`/`SIZE` 常量即可复用。

## 出片后的验收清单

1. `ffprobe` 确认 `width×height / r_frame_rate / duration`，时长要对上 `build_timeline` 的 total
2. 抽 6~8 帧拼成一张图看字幕：有没有横向溢出、有没有被底部裁掉、有没有串场
3. 若有真视频镜头，**逐段抽帧确认没有模型自加的乱码文字**
4. 确认音轨存在且 `sample_rate/channels` 正常

