"""轮询异步生成任务，直到完成/失败。

用法: mcp_task.py <task_id> [base_url] [max_minutes]
注意：判定完成要看 status 字段的值，不能用关键字 in 整串 JSON
     （"error": null 会误判为失败）。
"""
import json, sys, time, requests

TASK = sys.argv[1]
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://192.168.31.197:10004"
MAXMIN = float(sys.argv[3]) if len(sys.argv) > 3 else 30

MCP = BASE + "/mcp"
H = {"Content-Type": "application/json",
     "Accept": "application/json, text/event-stream"}


def sse(r):
    t = r.text
    i = t.find("data:")
    return json.loads(t[i + 5:].strip()) if i >= 0 else None


r = requests.post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                        "clientInfo": {"name": "task", "version": "1.0"}}},
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
    if not rj or "result" not in rj:
        return None
    c = rj["result"].get("content")
    if isinstance(c, list):
        c = "".join(x.get("text", "") for x in c)
    return c


DONE = {"completed", "succeeded", "success", "done", "finished"}
FAIL = {"failed", "failure", "cancelled", "canceled"}

t0 = time.time()
last = ""
while time.time() - t0 < MAXMIN * 60:
    s = call("get_task", {"task_id": TASK})
    if s is None:
        print("get_task 无返回"); break
    try:
        d = json.loads(s)
    except Exception:
        d = {"_raw": s}
    st = str(d.get("status", "")).lower()
    if s != last:
        print("[%5.1fs] status=%s has_workflow=%s" %
              (time.time() - t0, st, d.get("has_workflow")), flush=True)
        last = s
    if st in DONE or st in FAIL:
        print("=== FINAL %.1fs ===" % (time.time() - t0))
        print(json.dumps(d, ensure_ascii=False, indent=2)[:2000])
        break
    time.sleep(10)
else:
    print("超时 %s 分钟，最后状态: %s" % (MAXMIN, last[:300]))
