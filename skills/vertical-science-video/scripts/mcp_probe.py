import json, sys, requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.31.197:10004"
MCP = BASE + "/mcp"
H = {"Content-Type": "application/json",
     "Accept": "application/json, text/event-stream"}


def sse(resp):
    """SSE 响应：从第一个 'data:' 起整段 json.loads（JSON 会跨行，不能按行取）"""
    t = resp.text
    i = t.find("data:")
    if i < 0:
        return None
    return json.loads(t[i + 5:].strip())


def rpc(method, params=None, sid=None, _id=1):
    h = dict(H)
    if sid:
        h["mcp-session-id"] = sid
    body = {"jsonrpc": "2.0", "id": _id, "method": method}
    if params is not None:
        body["params"] = params
    r = requests.post(MCP, json=body, headers=h, timeout=60)
    return r, sse(r), r.headers.get("mcp-session-id")


r, init, sid = rpc("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "probe", "version": "1.0"}
})
print("initialize:", r.status_code, "session:", sid)
if not sid:
    print("!! 没有 mcp-session-id，后续会 400 Missing session ID")
    print(r.text[:500])
    sys.exit(1)

requests.post(MCP, json={"jsonrpc": "2.0", "method": "notifications/initialized"},
              headers={**H, "mcp-session-id": sid}, timeout=30)

_, tl, _ = rpc("tools/list", {}, sid, _id=2)
tools = (tl or {}).get("result", {}).get("tools", [])
print("\n=== tools (%d) ===" % len(tools))
for t in tools:
    name = t.get("name")
    desc = (t.get("description") or "")[:80].replace("\n", " ")
    print(" -", name, "|", desc)
    sch = t.get("inputSchema") or {}
    props = sch.get("properties") or {}
    if props:
        print("     args:", ", ".join(props.keys()))

print("\n=== list_models ===")
_, cap, _ = rpc("tools/call", {"name": "list_models", "arguments": {}}, sid, _id=3)
if cap and "result" in cap:
    txt = cap["result"].get("content")
    if isinstance(txt, list):
        txt = "".join(c.get("text", "") for c in txt)
    print(txt[:4000])
else:
    print(json.dumps(cap, ensure_ascii=False)[:2000])
