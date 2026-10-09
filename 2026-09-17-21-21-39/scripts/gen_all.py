#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量生成分镜图（1080x1920），双口并行：10003 / 10004"""
import itertools, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_image import generate, PORTS  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
IMGS = os.path.join(ROOT, "images")
SIZE = "1080x1920"
WORKERS = 1                      # 两口共用一个 ComfyUI，并发会被去重 -> 必须串行
_lock = threading.Lock()
_ctr = itertools.count()


def one(sc, style):
    out = os.path.join(IMGS, "s%s.png" % sc["id"])
    if os.path.exists(out) and os.path.getsize(out) > 50000:
        return "%s skip" % sc["id"]
    with _lock:
        port = PORTS[next(_ctr) % len(PORTS)]
    prompt = "%s, %s" % (sc["prompt"], style)
    seed = 1000 + int(sc["id"]) * 137        # 每个分镜固定且不重复的 seed
    for attempt in range(4):
        try:
            _, dt, n = generate(prompt, SIZE, out, port=port, seed=seed)
            return "%s ok  %.1fs  %4.0fKB  [:%d]" % (sc["id"], dt, n / 1024, port)
        except Exception as e:
            if attempt == 3:
                return "%s FAILED: %s" % (sc["id"], e)
            time.sleep(4)


def main():
    cfg = json.load(open(os.path.join(ROOT, "scenes.json"), encoding="utf-8"))
    style = cfg["style"]
    os.makedirs(IMGS, exist_ok=True)
    scenes = cfg["scenes"]
    if len(sys.argv) > 1:                 # 只返修指定镜：gen_all.py 03 07
        want = set(sys.argv[1:])
        scenes = [s for s in scenes if s["id"] in want]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(lambda s: one(s, style), scenes):
            print("  " + r, flush=True)
    print("done %.1fs" % (time.time() - t0))


main()
