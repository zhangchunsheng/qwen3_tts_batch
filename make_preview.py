# -*- coding: utf-8 -*-
"""读取 manifest.csv + out/ 生成可试听的音色对比页面 index.html"""
import csv
import os

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out")

rows = list(csv.DictReader(open(os.path.join(BASE, "manifest.csv"), encoding="utf-8-sig")))
rows = [r for r in rows if r["audio"] and os.path.exists(os.path.join(OUT, r["audio"]))]

ORDER = ["儿童", "少年", "青年", "中年", "老年", "方言", "情绪"]
GROUP_DESC = {
    "儿童": "按 3 / 6 / 8 岁细分，年龄越小吐字越含混、音调越高",
    "少年": "变声期前后的青春期音色",
    "青年": "主力音色段，覆盖温和 / 磁性 / 活力 / 知性等方向",
    "中年": "成熟音色，适合旁白、解说、权威感场景",
    "老年": "声带松弛、语速慢，含沙哑与慈祥两种方向",
    "方言": "使用方言化参考文本生成，需试听确认口音准确度",
    "情绪": "同一段情绪弹性文本，用于测试演播状态",
}

groups, seen = [], {}
for r in rows:
    g = r.get("group") or "其他"
    seen.setdefault(g, []).append(r)
for g in ORDER:
    if g in seen:
        groups.append((g, seen.pop(g)))
for g in sorted(seen):
    groups.append((g, seen[g]))

sections = []
for gname, items in groups:
    inner = []
    for r in items:
        inner.append(f"""
      <div class="card">
        <div class="card-head">
          <span class="tag">{r['timbre']}</span>
          <span class="key">{r['key']}</span>
        </div>
        <audio controls preload="none" src="out/{r['audio']}"></audio>
        <div class="meta">{r['name']} · seed {r['seed']} · {r['seconds']}s</div>
        <details><summary>音色描述</summary><p>{r['instruction']}</p></details>
      </div>""")
    sections.append(f"""
    <section>
      <h2>{gname} <span class="count">{len(items)} 个音色</span></h2>
      <p class="gdesc">{GROUP_DESC.get(gname, '')}</p>
      <div class="grid">{''.join(inner)}</div>
    </section>""")

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Qwen3-TTS 音色库 · 批量试听</title>
<style>
  :root {{ --bg:#f7f8fa; --card:#fff; --line:#e5e7eb; --txt:#1f2328; --sub:#6b7280; --accent:#2563eb; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:32px 28px 60px; background:var(--bg); color:var(--txt);
         font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }}
  h1 {{ font-size:22px; margin:0 0 6px; }}
  .lead {{ color:var(--sub); margin:0 0 8px; }}
  .sum {{ font-size:12px; color:var(--sub); margin:0 0 28px; }}
  section {{ margin-bottom:34px; }}
  h2 {{ font-size:16px; margin:0 0 4px; padding-left:10px; border-left:3px solid var(--accent); }}
  .count {{ font-weight:400; font-size:12px; color:var(--sub); margin-left:8px; }}
  .gdesc {{ font-size:12px; color:var(--sub); margin:0 0 14px; padding-left:13px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:14px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
  .card-head {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; gap:8px; }}
  .tag {{ font-weight:600; font-size:14px; }}
  .key {{ font-size:11px; color:var(--sub); font-family:ui-monospace,Consolas,monospace; }}
  audio {{ width:100%; height:36px; }}
  .meta {{ font-size:11px; color:var(--sub); margin-top:8px; }}
  details {{ margin-top:6px; }}
  summary {{ cursor:pointer; font-size:12px; color:var(--accent); }}
  details p {{ font-size:12px; color:var(--sub); margin:8px 0 0; white-space:pre-wrap; }}
</style>
</head>
<body>
  <h1>Qwen3-TTS Voice Design · 音色库</h1>
  <p class="lead">按分组试听，点开描述可查看喂给模型的音色指令；角色同时已保存到 ComfyUI 的 <code>models/voices</code>，可直接用于后续配音。</p>
  <p class="sum">共 {len(rows)} 个音色 · {len(groups)} 个分组 · 同组内使用同一段参考文本，便于横向对比</p>
  {''.join(sections)}
</body>
</html>"""

with open(os.path.join(BASE, "index.html"), "w", encoding="utf-8") as f:
    f.write(html)
print(f"index.html 已生成，{len(rows)} 个音色，{len(groups)} 个分组")
