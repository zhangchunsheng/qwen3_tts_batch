#!/usr/bin/env python3
"""Qwen3-TTS Voice Design（ComfyUI / TTS-Audio-Suite）—— 输入音色描述，输出本地音频文件。

只依赖标准库（urllib），managed python 可直接跑。

用法：
  python voice_design.py --instruct "成熟中年男性声线，低沉醇厚..." \
      [--text "样本文本"] [--lang Chinese] [--seed 1] \
      [--save-as my_voice_key] [--out D:/out/voice.flac] [--host http://192.168.31.197:10003]

参数：
  --instruct   音色描述（必填，越具体越好）
  --text       用来发声的样本文本；默认一段含陈述/疑问/感叹的中文文本（约 10s）
  --lang       Chinese / English / Japanese / Korean ... 默认 Chinese
  --seed       0=随机；固定非零值可复现同一音色
  --save-as    把音色存成 ComfyUI Character Voice（英文 key），同名会自动覆盖
  --out        本地保存路径；扩展名留空则沿用 ComfyUI 输出的扩展名
  --host       ComfyUI 地址
  --timeout    轮询超时秒数，默认 900
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

DEFAULT_HOST = "http://192.168.31.197:10003"
DEFAULT_TEXT = (
    "今天天气真不错，你那边呢？……真的吗？我简直不敢相信！"
    "好吧，既然这样，那就按你说的办吧。"
)
AUDIO_EXT = (".flac", ".wav", ".mp3", ".ogg", ".m4a", ".opus", ".webm")


def http_json(url: str, data=None, timeout: int = 30):
    if data is None:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
    else:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def http_bytes(url: str, timeout: int = 180):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def build_graph(instruct: str, text: str, lang: str, seed: int, save_as: str | None) -> dict:
    graph = {
        "2": {
            "inputs": {
                "model_variant": "Voice Design - 1.7B VoiceDesign",
                "device": "auto",
                "voice_preset": "Vivian",
                "language": lang,
                "instruct": "",
                "top_k": 50,
                "top_p": 1,
                "temperature": 0.9,
                "repetition_penalty": 1.05,
                "max_new_tokens": 2048,
                "dtype": "auto",
                "attn_implementation": "auto",
                "x_vector_only_mode": False,
                "use_torch_compile": True,
                "use_cuda_graphs": False,
                "compile_mode": "default",
                "asr_use_forced_aligner": True,
                "asr_translate_target_language": "English",
                "asr_translate_instruction_override": (
                    "Translate the speech from {source_language} into {target_language} "
                    "text. Return only the translated text."
                ),
                "runtime_mode": "⚠️ Shared Runtime",
            },
            "class_type": "Qwen3TTSEngineNode",
            "_meta": {"title": "Qwen3-TTS Engine"},
        },
        "6": {
            "inputs": {
                "reference_text": text,
                "seed": seed,
                "voice_instruction": instruct,
                "TTS_engine": ["2", 0],
            },
            "class_type": "UnifiedVoiceDesignerNode",
            "_meta": {"title": "Voice Designer"},
        },
        "7": {
            "inputs": {"audio": ["6", 1]},
            "class_type": "PreviewAudio",
            "_meta": {"title": "Preview Audio"},
        },
    }
    if save_as:
        graph["3"] = {
            "inputs": {
                "character_name": save_as,
                "overwrite_character": True,
                "opt_narrator": ["6", 0],
            },
            "class_type": "SaveCharacterVoiceNode",
            "_meta": {"title": "Save Character Voice"},
        }
    return graph


def find_audio(history_entry: dict):
    """在 history 的 outputs 里找音频文件描述（filename/subfolder/type）。"""
    outputs = history_entry.get("outputs") or {}
    fallback = None
    for _node_id, out in outputs.items():
        for _key, val in out.items():
            if not isinstance(val, list):
                continue
            for item in val:
                if not isinstance(item, dict) or "filename" not in item:
                    continue
                fn = str(item.get("filename", "")).lower()
                if fn.endswith(AUDIO_EXT):
                    return item
                if fallback is None:
                    fallback = item
    return fallback


def main() -> int:
    ap = argparse.ArgumentParser(description="Qwen3-TTS Voice Design via ComfyUI")
    ap.add_argument("--instruct", required=True, help="音色描述")
    ap.add_argument("--text", default=DEFAULT_TEXT, help="样本文本")
    ap.add_argument("--lang", default="Chinese")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--save-as", default=None, help="保存为 Character Voice 的英文 key")
    ap.add_argument("--out", default=None, help="本地输出路径")
    ap.add_argument("--host", default=os.environ.get("COMFY_HOST", DEFAULT_HOST))
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    host = args.host.rstrip("/")

    # 1. 探活 + 看队列
    try:
        stats = http_json(f"{host}/system_stats")
    except Exception as e:
        print(f"[ERROR] 连不上 ComfyUI {host}: {e}", file=sys.stderr)
        return 2
    gpu = (stats.get("devices") or [{}])[0].get("name", "?")
    print(f"[OK] ComfyUI 在线：{gpu}")

    try:
        q = http_json(f"{host}/queue")
        running = len(q.get("queue_running") or [])
        pending = len(q.get("queue_pending") or [])
        if running or pending:
            print(f"[WARN] 队列中已有任务 running={running} pending={pending}，本次会排队等待")
            for item in q.get("queue_running") or []:
                print(f"       running: {str(item)[:200]}")
    except Exception:
        pass

    # 2. 提交
    graph = build_graph(args.instruct, args.text, args.lang, args.seed, args.save_as)
    client_id = str(uuid.uuid4())
    t0 = time.time()
    try:
        res = http_json(f"{host}/prompt", {"prompt": graph, "client_id": client_id})
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:2000]
        print(f"[ERROR] 提交失败 HTTP {e.code}: {detail}", file=sys.stderr)
        return 3
    prompt_id = res.get("prompt_id")
    if not prompt_id:
        print(f"[ERROR] 提交未返回 prompt_id: {res}", file=sys.stderr)
        return 3
    print(f"[OK] 已提交 prompt_id={prompt_id}")

    # 3. 轮询 history
    entry = None
    while time.time() - t0 < args.timeout:
        time.sleep(3)
        try:
            hist = http_json(f"{host}/history/{prompt_id}")
        except Exception:
            continue
        got = hist.get(prompt_id)
        if got:
            entry = got
            break
    if entry is None:
        print(f"[ERROR] 超时 {args.timeout}s 未拿到结果，prompt_id={prompt_id}", file=sys.stderr)
        return 4

    status = (entry.get("status") or {}).get("status_str", "")
    if status == "error":
        msgs = (entry.get("status") or {}).get("messages") or []
        for m in msgs:
            print(m, file=sys.stderr)
        print(f"[ERROR] 工作流执行失败: {status}", file=sys.stderr)
        return 5

    audio = find_audio(entry)
    if not audio:
        print(f"[ERROR] history 里没找到音频输出: {json.dumps(entry)[:1500]}", file=sys.stderr)
        return 6

    # 4. 下载（输出目录可能是 UNC 网络路径，必须走 /view）
    filename = audio["filename"]
    subfolder = audio.get("subfolder", "")
    ftype = audio.get("type", "output")
    url = f"{host}/view?" + urllib.parse.urlencode(
        {"filename": filename, "subfolder": subfolder, "type": ftype}
    )
    data = http_bytes(url)
    ext = os.path.splitext(filename)[1] or ".flac"
    out = args.out or os.path.abspath(f"voice_design_{int(time.time())}{ext}")
    if not os.path.splitext(out)[1]:
        out += ext
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "wb") as f:
        f.write(data)

    print(f"[DONE] {out}  ({len(data)/1024:.0f} KB, {time.time()-t0:.1f}s)")
    if args.save_as:
        print(f"[DONE] Character Voice 已保存：{args.save_as}")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
