# -*- coding: utf-8 -*-
"""
Qwen3-TTS Voice Design 批量音色生成
通过 ComfyUI API 批量提交 voice_design_qwen3_api.json 工作流，
为「年龄 × 性别 × 音色」矩阵中的每一个角色生成一段参考语音，并保存为可复用角色。
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import uuid

import requests

HOST = "http://192.168.31.197:10003"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKFLOW_PATH = os.path.join(BASE_DIR, "voice_design_qwen3_api.json")
OUT_DIR = os.path.join(BASE_DIR, "out")

# ---------------------------------------------------------------- 参考样本文本
# 同一段文本用于所有角色，便于横向比较音色。
# 覆盖：陈述句 / 疑问句 / 感叹句 / 列举停顿 / 高低起伏，长度约 10-15 秒。
REFERENCE_TEXT = (
    "今天天气真不错，你要不要一起去公园走走？"
    "远处的山峦连绵起伏，湖水在微风里泛起层层涟漪。"
    "什么？你说明天就要出发了？"
    "嗯，我明白了——那就这样决定吧，一路顺风！"
)

# ---------------------------------------------------------------- 角色矩阵
# (key, 中文名, 年龄组, 性别, 音色标签, voice_instruction)
CHARACTERS = [
    # ---------- 儿童 ----------
    ("child_m_lively", "男童·清脆活泼", "儿童", "男", "清脆活泼",
     "五六岁小男孩的声音，音调高而清脆，奶声奶气但吐字清楚，语速偏快，"
     "句尾常常不自觉地扬起来，带着天真好奇的劲儿。音色明亮干净，没有杂质，"
     "说话时有孩子气的停顿和换气，偶尔有一点漏风的感觉。情绪饱满，像在跟小伙伴分享新发现。"),
    ("child_f_sweet", "女童·甜美稚嫩", "儿童", "女", "甜美稚嫩",
     "六七岁小女孩的声音，音调很高很甜，音色轻盈透亮，像风铃一样。语速适中偏快，"
     "吐字带一点孩子气的含糊但整体可辨，句尾习惯性上扬。语气软糯撒娇，"
     "充满童真和想象力，偶尔有一两声清脆的笑意藏在字里行间。"),

    # ---------- 少年 ----------
    ("teen_m_sunny", "少年·阳光朝气", "少年", "男", "阳光朝气",
     "十五六岁少年的声音，刚过变声期，嗓音清爽里带着一点未定型的青涩，"
     "音高比成年男性略高，音色明亮有朝气。语速较快，语调起伏明显，"
     "充满少年人的热忱和冲劲，说话干脆利落，偶尔有点毛躁。无沙哑，无低沉。"),
    ("teen_f_fresh", "少女·清甜灵动", "少年", "女", "清甜灵动",
     "十六七岁高中女生的声音，音色清甜干净，音调偏高但已经脱去童声，"
     "带着少女特有的轻盈感。语速明快，语调活泼有弹性，情绪外放，"
     "说话像在跟朋友聊天，偶尔带一点俏皮的尾音上扬。吐字清晰，气息饱满。"),

    # ---------- 青年 ----------
    ("youth_m_clear", "青年男·清朗温和", "青年", "男", "清朗温和",
     "二十多岁青年男性的声音，音色清朗干净，音高适中，共鸣位置靠前，"
     "说话温和有礼、语速平稳从容，吐字清晰标准。语调自然舒缓，没有夸张起伏，"
     "气质阳光干净，像电台里那种让人舒服的年轻男声。"),
    ("youth_m_magnetic", "青年男·磁性低沉", "青年", "男", "磁性低沉",
     "二十七八岁男性声音，音域偏低，音色温暖厚实带有明显磁性的低频共振，"
     "中气十足但不浑厚。语速偏慢，咬字沉稳有力，气息绵长，"
     "语调平直克制、几乎没有上扬，像深夜电台的男主播，松弛且有倾诉感。"),
    ("youth_m_energetic", "青年男·活力明快", "青年", "男", "活力明快",
     "二十多岁男性声音，音色明亮有穿透力，语速快、节奏感强，"
     "字与字之间衔接紧凑，重音明确，语调起伏大、富有煽动性和热情，"
     "像带货主播或体育解说，中气足、精神饱满，略带一点喊话式的用力感。"),
    ("youth_f_sweet", "青年女·甜美温柔", "青年", "女", "甜美温柔",
     "二十多岁女性的声音，音色柔和甜美，音调中偏高，带着轻微的鼻音和气息感，"
     "语速舒缓，语调温婉上扬，吐字轻柔圆润。气质亲切体贴，说话像在哄人，"
     "尾音常常轻轻飘起来，整体松弛不紧绷。"),
    ("youth_f_cool", "青年女·清冷知性", "青年", "女", "清冷知性",
     "二十七八岁女性声音，音调中等偏高，音色清冽纯净、几乎没有杂音，"
     "咬字极为标准清晰，语速平稳，语调克制平直、起伏很小，情绪冷淡理性。"
     "气质疏离而专业，像纪录片解说或有声书里的冷静叙述者。"),
    ("youth_f_vivid", "青年女·活力四射", "青年", "女", "活力四射",
     "二十出头女性的声音，音调偏高，音色明亮跳跃，语速快、节奏轻快，"
     "语调起伏夸张、表情丰富，常有上扬的惊叹尾音。中气足、感染力强，"
     "像综艺节目里的活泼女主持，说话带笑意，朝气蓬勃。"),

    # ---------- 中年 ----------
    ("mid_m_mellow", "中年男·醇厚沉稳", "中年", "男", "醇厚沉稳",
     "四十多岁成熟男性的声音，低沉醇厚，嗓音带有自然的胸腔共鸣，"
     "语速平缓从容，吐字清晰标准，语调稳定克制，没有夸张起伏。"
     "气质沉稳可靠、温和内敛，略带阅历感，无沙哑破音，不生硬冰冷也不油腻，"
     "像阅历丰富的儒雅男士，说话松弛自然，停顿合理。"),
    ("mid_m_strong", "中年男·浑厚有力", "中年", "男", "浑厚有力",
     "四十多岁男性声音，音域低，音色浑厚粗粝、胸腔和鼻腔共鸣都很重，"
     "中气极足，音量感强。语速慢而稳，每个字都咬得实、落得重，"
     "语调下沉，带有权威感和压迫感，像新闻联播播音员或企业宣传片旁白，"
     "庄重、可信、不容置疑。"),
    ("mid_m_gentle", "中年男·温和儒雅", "中年", "男", "温和儒雅",
     "四十多岁男性声音，音调中等，音色温润柔和略带一点书卷气，"
     "语速中等偏慢，咬字轻巧文雅，语调平缓上行、带着讲解的耐心。"
     "气质儒雅亲切，像大学教授或博物馆讲解员，说话不疾不徐，"
     "声音里带着笑意和包容感。"),
    ("mid_f_warm", "中年女·温婉柔和", "中年", "女", "温婉柔和",
     "四十岁左右女性的声音，音调中等，音色温润饱满，带着成熟女性特有的柔和质感，"
     "语速舒缓，吐字圆润，语调温和起伏自然。气质亲切包容，"
     "像邻家阿姨或深夜情感节目女主播，说话有安抚感，声音里带着笑意。"),
    ("mid_f_crisp", "中年女·干练职业", "中年", "女", "干练职业",
     "三十八九岁职业女性声音，音调中等，音色干脆利落、几乎没有气声，"
     "咬字精准、语速偏快，节奏感和逻辑重音都很明确，语调平稳少起伏。"
     "气质专业干练，像新闻女主播或企业发布会主持人，理性、清晰、有分寸感。"),
    ("mid_f_elegant", "中年女·知性优雅", "中年", "女", "知性优雅",
     "四十多岁女性的声音，音调中低，音色细腻优雅带轻微的醇厚感，"
     "语速从容不迫，吐字讲究，语调舒缓下行，句尾常常轻轻收住。"
     "气质知性安静，像文学作品的朗读者，声音里有厚度和分寸，优雅而不冷淡。"),

    # ---------- 老年 ----------
    ("senior_m_hoarse", "老年男·沧桑沙哑", "老年", "男", "沧桑沙哑",
     "七十岁左右老爷爷的声音，音调低沉，音色明显沙哑粗糙、带颗粒感和气息声，"
     "声带松弛使尾音有轻微颤抖和拖沓。语速慢，吐字略含混但基本可辨，"
     "语调起伏小、平淡悠长。像经历过风霜的老者在慢慢讲述往事，"
     "沧桑、质朴、有故事感。"),
    ("senior_m_kind", "老年男·慈祥温和", "老年", "男", "慈祥温和",
     "七十多岁老爷爷的声音，音调偏低但柔和不哑，音色温暖带一点老年人的虚化，"
     "语速很慢，语调舒缓上扬、充满善意，句尾常常拖长并轻轻上翘。"
     "像在给孙辈讲故事，慈祥、耐心、让人安心，说话时似乎带着微笑。"),
    ("senior_f_kind", "老年女·慈爱温和", "老年", "女", "慈爱温和",
     "七十岁左右老奶奶的声音，音调中偏高但音色发虚发飘，带明显的年龄感，"
     "语速缓慢，吐字有些松散，语调温和起伏，尾音常常软软地拖长。"
     "像邻家奶奶在唠家常，慈爱、絮叨、亲切，说话中气不足但充满疼爱。"),
    ("senior_f_hoarse", "老年女·沙哑缓慢", "老年", "女", "沙哑缓慢",
     "七十五岁左右老太太的声音，音调低沉，音色沙哑干涩、有明显的气息摩擦声，"
     "声带松弛导致字与字之间有停顿和拖音。语速很慢，音量偏小，"
     "语调平直少起伏，吐字略含混。像久病或操劳一生的老妪在低声说话，"
     "苍老、迟缓、质朴。"),
]


# ---------------------------------------------------------------- API 封装
def load_workflow():
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_prompt(wf, char, seed, reference_text, engine_lang="Chinese"):
    """克隆工作流并注入当前角色参数"""
    g = json.loads(json.dumps(wf))
    # 引擎：使用 VoiceDesign 1.7B，语言切到目标语言
    g["2"]["inputs"]["language"] = engine_lang
    # 音色设计器
    g["6"]["inputs"]["voice_instruction"] = char[5]
    g["6"]["inputs"]["reference_text"] = reference_text
    g["6"]["inputs"]["seed"] = seed
    # 保存角色（用英文 key 做文件名，避免 NAS 路径下的编码问题）
    g["3"]["inputs"]["character_name"] = char[0]
    g["3"]["inputs"]["overwrite_character"] = True
    return g


def submit(g, client_id):
    r = requests.post(f"{HOST}/prompt",
                      json={"prompt": g, "client_id": client_id},
                      timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"提交失败 {r.status_code}: {r.text[:800]}")
    data = r.json()
    if data.get("node_errors"):
        raise RuntimeError(f"节点错误: {json.dumps(data['node_errors'], ensure_ascii=False)[:800]}")
    return data["prompt_id"]


def wait_done(prompt_id, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = requests.get(f"{HOST}/history/{prompt_id}", timeout=30)
        if r.status_code == 200:
            h = r.json()
            if prompt_id in h:
                return h[prompt_id]
        time.sleep(2)
    raise TimeoutError(f"等待 {prompt_id} 超时")


def download_audio(file_info, dest_dir):
    """通过 /view 下载 ComfyUI 输出文件"""
    fn = file_info["filename"]
    sub = file_info.get("subfolder", "")
    typ = file_info.get("type", "output")
    qs = urllib.parse.urlencode({"filename": fn, "subfolder": sub, "type": typ})
    r = requests.get(f"{HOST}/view?{qs}", timeout=180, stream=True)
    if r.status_code != 200:
        return None, f"下载失败 {r.status_code}"
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, fn)
    with open(path, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    return path, None


def find_audio(hist):
    """从 history outputs 里找到音频文件信息"""
    for node_id, out in (hist.get("outputs") or {}).items():
        for key in ("audio", "images", "files"):
            v = out.get(key)
            if not v:
                continue
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and item.get("filename"):
                        return item
            elif isinstance(v, dict) and v.get("filename"):
                return v
    return None


def find_texts(hist):
    """收集 PreviewAny 输出的文本"""
    texts = []
    for node_id, out in (hist.get("outputs") or {}).items():
        for val in out.values():
            if isinstance(val, list) and val and isinstance(val[0], str):
                texts.append((node_id, "\n".join(val)))
    return texts


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑指定 key，逗号分隔")
    ap.add_argument("--limit", type=int, default=0, help="限制数量")
    ap.add_argument("--seed0", type=int, default=1000, help="起始 seed")
    ap.add_argument("--lang", default="Chinese")
    ap.add_argument("--reference", default=REFERENCE_TEXT)
    args = ap.parse_args()

    chars = CHARACTERS
    if args.only:
        keys = {k.strip() for k in args.only.split(",")}
        chars = [c for c in chars if c[0] in keys]
    if args.limit:
        chars = chars[:args.limit]

    os.makedirs(OUT_DIR, exist_ok=True)
    wf = load_workflow()
    client_id = str(uuid.uuid4())

    manifest_path = os.path.join(BASE_DIR, "manifest.csv")
    rows = []
    print(f"待生成 {len(chars)} 个角色 -> {HOST}\n")

    for i, char in enumerate(chars):
        key, name, age, gender, timbre, instr = char
        seed = args.seed0 + i
        print(f"[{i+1}/{len(chars)}] {key} | {age}/{gender}/{timbre}", end=" ... ", flush=True)
        t0 = time.time()
        try:
            g = build_prompt(wf, char, seed, args.reference, args.lang)
            pid = submit(g, client_id)
            hist = wait_done(pid)
            fi = find_audio(hist)
            path, err = download_audio(fi, OUT_DIR) if fi else (None, "未找到音频输出")
            elapsed = time.time() - t0
            if path:
                final = os.path.join(OUT_DIR, f"{key}{os.path.splitext(path)[1]}")
                if os.path.abspath(path) != os.path.abspath(final):
                    if os.path.exists(final):
                        os.remove(final)
                    os.rename(path, final)
                print(f"OK {elapsed:.1f}s -> {os.path.basename(final)}")
            else:
                final = ""
                print(f"失败 {elapsed:.1f}s: {err}")
            save_info = ""
            for nid, txt in find_texts(hist):
                if "save" in txt.lower() or "character" in txt.lower():
                    save_info = txt[:400]
                    break
            rows.append({
                "key": key, "name": name, "age": age, "gender": gender,
                "timbre": timbre, "seed": seed, "audio": os.path.basename(final),
                "seconds": round(elapsed, 1), "instruction": instr,
                "save_info": save_info.replace("\n", " | "),
            })
        except Exception as e:
            print(f"异常: {type(e).__name__}: {e}")
            rows.append({"key": key, "name": name, "age": age, "gender": gender,
                         "timbre": timbre, "seed": seed, "audio": "",
                         "seconds": round(time.time() - t0, 1),
                         "instruction": instr, "save_info": f"ERROR: {e}"})

    with open(manifest_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["key"])
        w.writeheader()
        w.writerows(rows)
    ok = sum(1 for r in rows if r["audio"])
    print(f"\n完成 {ok}/{len(rows)}，音频目录: {OUT_DIR}\n清单: {manifest_path}")


if __name__ == "__main__":
    main()
