#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""逐分镜生成中文配音，并用 ffprobe 读取真实时长"""
import asyncio, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(ROOT, "audio")
FFPROBE = "ffprobe"


def dur(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


async def main():
    import edge_tts
    cfg = json.load(open(os.path.join(ROOT, "scenes.json"), encoding="utf-8"))
    voice = cfg.get("voice", "zh-CN-XiaoxiaoNeural")
    rate = cfg.get("rate", "+0%")
    os.makedirs(AUDIO, exist_ok=True)
    gaps = cfg.get("gap", 0.35)
    timeline, t = [], 0.0
    for sc in cfg["scenes"]:
        p = os.path.join(AUDIO, "s%s.mp3" % sc["id"])
        if not (os.path.exists(p) and os.path.getsize(p) > 2000):
            for attempt in range(3):
                try:
                    c = edge_tts.Communicate(sc["narration"], voice, rate=rate)
                    await c.save(p)
                    if os.path.getsize(p) > 2000:
                        break
                except Exception as e:
                    print("  tts retry %d: %s" % (attempt + 1, e))
                    await asyncio.sleep(2)
        d = dur(p)
        timeline.append({"id": sc["id"], "start": round(t, 3), "dur": round(d, 3),
                         "narration": sc["narration"], "prompt": sc["prompt"],
                         "motion": sc["motion"]})
        print("  %s  %.2fs" % (sc["id"], d))
        t += d + gaps
    total = t - gaps
    json.dump({"timeline": timeline, "gap": gaps, "total": round(total, 2)},
              open(os.path.join(ROOT, "timings.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("TOTAL narration+gap = %.1fs  (%d scenes)" % (total, len(timeline)))


asyncio.run(main())
