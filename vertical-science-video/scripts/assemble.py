#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把分镜图 + 配音 + 字幕合成为 720x1280 竖屏科普短片"""
import json, os, subprocess, sys, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
IMGS = os.path.join(ROOT, "images")
AUDIO = os.path.join(ROOT, "audio")
VIDEOS = os.path.join(ROOT, "videos")
CLIPS = os.path.join(ROOT, "clips")
WORK = os.path.join(ROOT, "work")

W, H, FPS = 720, 1280, 30
SRC_W, SRC_H = 1080, 1920
FONT = "C:/Windows/Fonts/msyhbd.ttc"
FONTS_DIR = "C:/Windows/Fonts"
FONT_NAME = "Microsoft YaHei"
TAIL = 0.9          # 结尾留白
FADE_IN = 0.5
FADE_OUT = 0.9
MAX_CUE = 16        # 单条字幕最大字数（保证一行放得下）
PAUSE_CHARS = "，。；、：？！,.;:?!"


def run(cmd, **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        sys.stderr.write("CMD FAILED: %s\n%s\n" % (" ".join(cmd)[:400], p.stderr[-2000:]))
        raise SystemExit(1)
    return p


def motion_vf(motion, frames):
    n = max(frames, 1)
    if motion == "in":
        z = "1+0.14*on/%d" % n
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion == "out":
        z = "1.14-0.14*on/%d" % n
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion == "pandown":
        z = "1.12"
        x, y = "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*(on/%d)" % n
    else:  # panup
        z = "1.12"
        x, y = "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*(1-on/%d)" % n
    return ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
            "zoompan=z='%s':x='%s':y='%s':d=1:s=%dx%d:fps=%d,setsar=1,format=yuv420p"
            % (SRC_W, SRC_H, SRC_W, SRC_H, z, x, y, W, H, FPS))


def split_cues(text, max_len=MAX_CUE):
    """按标点切分并合并成适合阅读的字幕条目"""
    parts, buf = [], ""
    for ch in text:
        buf += ch
        if ch in PAUSE_CHARS:
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    cues, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) > max_len:
            cues.append(cur)
            cur = p
        else:
            cur += p
    if cur:
        cues.append(cur)
    if len(cues) > 1 and len(cues[-1]) <= 2:
        cues[-2] += cues[-1]
        cues.pop()
    return cues


def ass_time(t):
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return "%d:%02d:%05.2f" % (h, m, s)


def build_ass(tl, labels, gap, out_path):
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{f},38,&H00FFFFFF,&H000000FF,&H00403020,&H78000000,-1,0,0,0,100,100,0.5,0,1,3,1,2,48,48,150,1
Style: Label,{f},32,&H00A8D8FF,&H000000FF,&H00403020,&H78000000,-1,0,0,0,100,100,2,0,1,3,1,8,44,44,58,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""".format(w=W, h=H, f=FONT_NAME)

    lines = []
    for idx, sc in enumerate(tl):
        sid = sc["id"]
        start = sc["start"]
        dur = sc["dur"]
        nxt = tl[idx + 1]["start"] if idx + 1 < len(tl) else start + dur + TAIL
        label = labels.get(sid, "")
        if label:
            lines.append("Dialogue: 0,%s,%s,Label,,0,0,0,,%s"
                         % (ass_time(start + 0.15), ass_time(min(nxt, start + dur + 1.2)), label))
        cues = split_cues(sc["narration"])
        total_chars = sum(len(c) for c in cues) or 1
        t = start + 0.12
        for i, c in enumerate(cues):
            d = dur * len(c) / total_chars
            end = (nxt - 0.06) if i == len(cues) - 1 else t + d
            txt = c.replace("\n", " ").strip()
            lines.append("Dialogue: 0,%s,%s,Sub,,0,0,0,,%s"
                         % (ass_time(t), ass_time(max(end - 0.04, t + 0.2)), txt))
            t = t + d
    with open(out_path, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(head + "\n".join(lines) + "\n")


def main():
    cfg = json.load(open(os.path.join(ROOT, "scenes.json"), encoding="utf-8"))
    tim = json.load(open(os.path.join(ROOT, "timings.json"), encoding="utf-8"))
    labels = json.load(open(os.path.join(ROOT, "labels.json"), encoding="utf-8"))
    tl = tim["timeline"]
    gap = tim["gap"]
    for d in (CLIPS, WORK):
        os.makedirs(d, exist_ok=True)

    # 音画统一时长
    total = sum(s["dur"] for s in tl) + gap * (len(tl) - 1) + TAIL

    # 1) 每个分镜生成运动镜头片段（有真视频就用真视频，否则静帧+运镜）
    clip_list = []
    for i, sc in enumerate(tl):
        d = sc["dur"] + (gap if i < len(tl) - 1 else TAIL)
        frames = int(round(d * FPS))
        img = os.path.join(IMGS, "s%s.png" % sc["id"])
        vid = os.path.join(VIDEOS, "s%s.mp4" % sc["id"])
        out = os.path.join(CLIPS, "c%s_%.3f.mp4" % (sc["id"], d))
        if not os.path.exists(out):
            if os.path.exists(vid) and os.path.getsize(vid) > 100000:
                # 真视频：24fps 源 -> 循环铺满 d 秒，统一 30fps/720x1280
                run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", vid,
                     "-t", "%.3f" % d,
                     "-vf", "scale=%d:%d:force_original_aspect_ratio=increase,"
                            "crop=%d:%d,fps=%d,setsar=1,format=yuv420p" % (W, H, W, H, FPS),
                     "-r", str(FPS), "-c:v", "libx264", "-threads", "2",
                     "-preset", "medium", "-crf", "18",
                     "-pix_fmt", "yuv420p", "-an", out])
                kind = "VIDEO"
            else:
                run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", img,
                     "-t", "%.3f" % d,
                     "-vf", motion_vf(sc["motion"], frames),
                     "-r", str(FPS), "-c:v", "libx264", "-threads", "2",
                     "-preset", "medium", "-crf", "18",
                     "-pix_fmt", "yuv420p", "-an", out])
                kind = sc["motion"]
        else:
            kind = "cached"
        clip_list.append(out)
        print("  clip %s  %.2fs  %s" % (sc["id"], d, kind), flush=True)

    # 2) 拼接视频
    lst = os.path.join(WORK, "vid.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for c in clip_list:
            f.write("file '%s'\n" % c.replace("\\", "/"))
    base = os.path.join(WORK, "base.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", base])

    # 3) 拼接配音（分镜之间插入静音间隔）
    sil = os.path.join(WORK, "sil.mp3")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", "%.3f" % gap, "-c:a", "libmp3lame", "-b:a", "96k", sil])
    alst = os.path.join(WORK, "aud.txt")
    with open(alst, "w", encoding="utf-8") as f:
        for i, sc in enumerate(tl):
            f.write("file '%s'\n" % os.path.join(AUDIO, "s%s.mp3" % sc["id"]).replace("\\", "/"))
            if i < len(tl) - 1:
                f.write("file '%s'\n" % sil.replace("\\", "/"))
    narr = os.path.join(WORK, "narr.mp3")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", alst, "-c", "copy", narr])

    # 4) 字幕
    ass = os.path.join(WORK, "sub.ass")
    build_ass(tl, labels, gap, ass)

    # 5) 合成：字幕烧录 + 首尾淡入淡出 + 音频补齐到总长
    def esc(p):
        return p.replace("\\", "/").replace(":", "\\:")

    out = os.path.join(ROOT, "肿瘤早期警示症状_科普竖屏.mp4")
    run(["ffmpeg", "-y", "-i", base, "-i", narr,
         "-filter_complex",
         "[0:v]subtitles='%s':fontsdir='%s',fade=t=in:st=0:d=%.2f,"
         "fade=t=out:st=%.2f:d=%.2f[v];"
         "[1:a]apad,atrim=0:%.3f,afade=t=in:st=0:d=0.3,"
         "afade=t=out:st=%.2f:d=%.2f[a]"
         % (esc(ass), esc(FONTS_DIR),
            FADE_IN, total - FADE_OUT, FADE_OUT,
            total, total - FADE_OUT, FADE_OUT),
         "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-threads", "2", "-preset", "medium", "-crf", "19",
         "-profile:v", "high", "-level", "4.0", "-pix_fmt", "yuv420p",
         "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
         "-movflags", "+faststart", "-t", "%.3f" % total, out])
    print("\nDONE -> %s  (%.1fs)" % (out, total))


main()
