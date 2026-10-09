#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量生成真视频分镜（MCP -> minimax-h3-turbo），双口并行。

时长由配音驱动：clip_dur = 口播时长 + gap（最后一镜 + TAIL），
否则画面会比音轨短，导致字幕错位、结尾黑屏。
"""
import json, math, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
VIDEOS = os.path.join(ROOT, "videos")
TAIL = 0.9
DONE = {"completed", "succeeded", "success", "done", "finished"}
FAIL = {"failed", "failure", "cancelled", "canceled"}


class MCP:
    def __init__(self, port):
        self.base = "http://192.168.31.197:%d" % port
        self.h = {"Content-Type": "application/json",
                  "Accept": "application/json, text/event-stream"}
        r = requests.post(self.base + "/mcp", timeout=60, headers=self.h,
                          json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                           "clientInfo": {"name": "genvid", "version": "1.0"}}})
        self.h["mcp-session-id"] = r.headers.get("mcp-session-id")
        requests.post(self.base + "/mcp", timeout=30, headers=self.h,
                      json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._id = 10

    def _sse(self, r):
        i = r.text.find("data:")
        return json.loads(r.text[i + 5:].strip()) if i >= 0 else None

    def call(self, name, args, timeout=300):
        self._id += 1
        r = requests.post(self.base + "/mcp", timeout=timeout, headers=self.h,
                          json={"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                                "params": {"name": name, "arguments": args}})
        j = self._sse(r)
        if not j or "result" not in j:
            return {"_err": (j or {}).get("error") or r.text[:300]}
        c = j["result"].get("content")
        if isinstance(c, list):
            c = "".join(x.get("text", "") for x in c)
        try:
            return json.loads(c)
        except Exception:
            return {"_raw": c}


def main():
    tim = json.load(open(os.path.join(ROOT, "timings.json"), encoding="utf-8"))
    cfg = json.load(open(os.path.join(ROOT, "videoscenes.json"), encoding="utf-8"))
    tl = tim["timeline"]
    gap = tim["gap"]
    lasts = tl[-1]["id"]
    durs = {s["id"]: s["dur"] for s in tl}
    os.makedirs(VIDEOS, exist_ok=True)

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    want = set(args) or set(cfg["clips"])
    jobs = []
    for sid, c in cfg["clips"].items():
        if sid not in want:
            continue
        d = durs[sid] + (TAIL if sid == lasts else gap)
        dur = max(1, min(15, int(math.ceil(d))))
        jobs.append((sid, c, dur))
    print("clips:", [(s, "%ds" % d) for s, _, d in jobs], flush=True)

    def work(job):
        sid, c, dur = job
        out = os.path.join(VIDEOS, "s%s.mp4" % sid)
        if os.path.exists(out) and os.path.getsize(out) > 100000:
            return "%s skip" % sid
        try:
            m = MCP(c.get("port", 10003))
        except Exception as e:
            return "%s MCP-INIT-FAILED %s" % (sid, e)
        # 坑A：必须 background=pending，否则同步挂 300s 且任务不进异步表
        r = m.call("generate_video", {
            "model": cfg.get("model", "minimax-h3-turbo"),
            "prompt": c["prompt"], "duration": dur,
            "size": cfg.get("size", "720p-9:16"),
            "background": "pending", "response_format": "url",
        }, timeout=300)
        tid = r.get("id") or r.get("task_id")
        if not tid:
            return "%s SUBMIT-FAILED %s" % (sid, json.dumps(r, ensure_ascii=False)[:300])
        t0 = time.time()
        while time.time() - t0 < 40 * 60:
            time.sleep(10)
            st = m.call("get_task", {"task_id": tid})
            s = str(st.get("status", "")).lower()
            if s in DONE:
                url = ((st.get("output") or {}).get("data") or [{}])[0].get("url")
                if not url:
                    return "%s NO-URL %s" % (sid, json.dumps(st, ensure_ascii=False)[:300])
                with open(out, "wb") as f:
                    f.write(requests.get(url, timeout=300).content)
                return "%s ok  %ds-source  gen %.0fs  %.0fKB" % (
                    sid, dur, time.time() - t0, os.path.getsize(out) / 1024)
            if s in FAIL or st.get("error"):
                return "%s FAILED %s" % (sid, json.dumps(st, ensure_ascii=False)[:300])
        return "%s TIMEOUT" % sid

    # 并发会报 hostbuf_file_reader_read failed（多任务同时加载模型冲突），
    # 所以严格串行：一次只跑一个视频任务。--par 可强制并发做对比实验。
    workers = 2 if "--par" in sys.argv else 1
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(work, jobs):
            print("  " + r, flush=True)
    print("done %.1fs" % (time.time() - t0))


main()
