#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""调用 192.168.31.197:10003 (ComfyUI OpenAI 兼容接口) 生成图片"""
import base64, json, os, sys, time, urllib.request

PORTS = [10003, 10004]
MODEL = "z-image-turbo"


def generate(prompt, size="1080x1920", out_path=None, model=MODEL,
             timeout=900, port=None, seed=None):
    """port 为 None 时在 10003/10004 间轮询，实现双卡并行

    注意：两口背后是同一个 ComfyUI，并发请求会被去重（不同 prompt 返回同一张图），
    因此批量出图必须串行（WORKERS=1）并给每个分镜不同 seed。
    """
    ports = [port] if port else PORTS
    last = None
    for p in ports:
        api = "http://192.168.31.197:%d/v1/images/generations" % p
        payload = {"model": model, "prompt": prompt, "size": size, "n": 1}
        if seed is not None:
            payload["seed"] = int(seed)
        req = urllib.request.Request(
            api,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:          # 该口忙/挂了就换下一个
            last = e
            continue
        dt = time.time() - t0
        b64 = data["data"][0].get("b64_json")
        if not b64:
            last = RuntimeError("no b64_json: %s" % str(data)[:300])
            continue
        raw = base64.b64decode(b64)
        if out_path:
            d = os.path.dirname(os.path.abspath(out_path))
            os.makedirs(d, exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(raw)
        return out_path, dt, len(raw)
    raise last or RuntimeError("all ports failed")


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "a cute water droplet mascot"
    size = sys.argv[2] if len(sys.argv) > 2 else "1080x1920"
    out = sys.argv[3] if len(sys.argv) > 3 else "_test.png"
    path, dt, n = generate(p, size, out)
    print("saved %s  %.1fs  %d bytes" % (path, dt, n))
