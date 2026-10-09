"""单次视频生成参数验证：确认模型/尺寸/background 参数是否可用，并测速。

用法: mcp_vtest.py <base_url> <model> <duration> <size> [prompt]
"""
import json, sys, time, requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.31.197:10004"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "minimax-h3-turbo"
DUR = int(sys.argv[3]) if len(sys.argv) > 3 else 3
SIZE = sys.argv[4] if len(sys.argv) > 4 else "720p-9:16"
PROMPT = sys.argv[5] if len(sys.argv) > 5 else (
    "A glowing blue neuron network pulsing with light, abstract scientific "
    "visualization, clean dark background, smooth camera push in, no text, "
    "no letters, no watermark")

MCP = BASE + "/mcp"
H = {"Content-Type": "application/json",
     "Accept": "application/json, text/event-stream"}


def sse(r):
    t = r.text
    i = t.find("data:")
    return json.loads(t[i + 5:].strip()) if i >= 0 else None


r = requests.post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                        "clientInfo": {"name": "vtest", "version": "1.0"}}},
                  headers=H, timeout=60)
sid = r.headers.get("mcp-session-id")
H2 = {**H, "mcp-session-id": sid}
requests.post(MCP, json={"jsonrpc": "2.0", "method": "notifications/initialized"},
              headers=H2, timeout=30)

_id = [10]


def call(name, args):
    _id[0] += 1
    r = requests.post(MCP, json={"jsonrpc": "2.0", "id": _id[0], "method": "tools/call",
                                 "params": {"name": name, "arguments": args}},
                      headers=H2, timeout=300)
    rj = sse(r)
    if not rj:
        return {"raw": r.text[:500]}
    if "error" in rj:
        return rj["error"]
    c = rj["result"].get("content")
    if isinstance(c, list):
        c = "".join(x.get("text", "") for x in c)
    return c


t0 = time.time()
res = call("generate_video", {
    "model": MODEL, "prompt": PROMPT, "duration": DUR, "size": SIZE,
    "background": "pending",          # 坑A：必须传，否则同步挂300s且任务不进异步表
    "response_format": "url",
})
print("submit %.1fs ->" % (time.time() - t0), json.dumps(res, ensure_ascii=False)[:600])

task_id = None
if isinstance(res, str):
    try:
        task_id = json.loads(res).get("task_id") or json.loads(res).get("id")
    except Exception:
        pass
if not task_id and isinstance(res, dict):
    task_id = res.get("task_id") or res.get("id")
print("task_id:", task_id)

if task_id:
    for i in range(120):
        time.sleep(10)
        st = call("get_task", {"task_id": task_id})
        s = json.dumps(st, ensure_ascii=False)
        if '"status"' in s or '"state"' in s:
            print("[%3ds] %s" % ((i + 1) * 10, s[:300]))
        if any(k in s for k in ("completed", "succeeded", "success", "failed", "error")):
            print("FINAL %.1fs:" % (time.time() - t0), s[:800])
            break
    else:
        print("timeout 20min, last:", s[:400])

print("total %.1fs" % (time.time() - t0))
