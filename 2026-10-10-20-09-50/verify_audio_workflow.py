"""连通性验证：用新的 registry 渲染音频工作流，直接提交给运行中的 ComfyUI。

不经过网关路由（那需要重启进程加载新代码），只验证三件事：
  1. models.yaml 的新条目能被解析、绑定路径都能命中；
  2. 渲染后的 API JSON 能被 ComfyUI 接受（节点名 / 输入值合法）；
  3. history 里的产物挂在 `audio` 键下（collect_images 的音频分支依赖这一点）。
"""
from __future__ import annotations

import json
import sys
import time
import types
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Work\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\ComfyUI\custom_nodes\ComfyUI-Roundabout")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.31.197:10003"

if "rb_gateway" not in sys.modules:
    pkg = types.ModuleType("rb_gateway")
    pkg.__path__ = [str(ROOT / "gateway")]
    sys.modules["rb_gateway"] = pkg

from rb_gateway.config import settings  # noqa: E402
from rb_gateway.registry import build_workflow, registry  # noqa: E402

registry.load(settings.models_file, settings.workflows_dir, settings.default_model)
spec = registry.resolve("qwen3-tts-voice-design")
print("model:", spec.name, "mode:", spec.mode, "output_node:", spec.output_node)
print("bindings:", sorted(spec.bindings))

values = {
    "prompt": "你好，这是音色设计接口的连通性测试。",
    "voice_instruction": "成熟中年男性声线，低沉醇厚，语速平缓从容，吐字清晰。",
    "seed": 1,
    "filename_prefix": "audio/RoundaboutAPITest",
}
wf = build_workflow(spec, values, None)
print("rendered nodes:", sorted(wf))
print("engine language:", wf["2"]["inputs"]["language"], "| designer text:", wf["6"]["inputs"]["reference_text"][:20])


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


try:
    res = post("/prompt", {"prompt": wf, "client_id": "roundabout-audio-verify"})
except urllib.error.HTTPError as exc:
    print("SUBMIT FAILED:", exc.code, exc.read().decode("utf-8", "replace")[:1500])
    raise SystemExit(1)

prompt_id = res.get("prompt_id")
print("submitted prompt_id:", prompt_id)
if res.get("node_errors"):
    print("node_errors:", res["node_errors"])

deadline = time.time() + 900
while time.time() < deadline:
    with urllib.request.urlopen(f"{BASE}/history/{prompt_id}", timeout=30) as resp:
        hist = json.loads(resp.read())
    entry = hist.get(prompt_id)
    if entry:
        status = (entry.get("status") or {}).get("status_str")
        if status == "error" or ((entry.get("status") or {}).get("completed") is False and (entry.get("status") or {}).get("messages")):
            print("EXEC ERROR:", json.dumps(entry["status"], ensure_ascii=False)[:1500])
            raise SystemExit(1)
        if entry.get("outputs"):
            print("outputs keys:", list(entry["outputs"]))
            print(json.dumps(entry["outputs"], ensure_ascii=False)[:800])
            raise SystemExit(0)
    time.sleep(3)

print("TIMEOUT waiting for history")
raise SystemExit(2)
