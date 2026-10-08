# -*- coding: utf-8 -*-
"""
Qwen3-TTS Voice Design 批量音色生成
通过 ComfyUI API 批量提交 voice_design_qwen3_api.json 工作流，
为「年龄 × 性别 × 音色 / 方言 / 情绪」矩阵中的每个角色生成参考语音，并保存为可复用角色。

角色定义格式：
  (key, name, group, gender, timbre, instruction, ref_override)
  ref_override 为空则使用全局 REFERENCE_TEXT
"""
import argparse
import csv
import json
import os
import time
import urllib.parse
import uuid

import requests

HOST = "http://192.168.31.197:10003"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKFLOW_PATH = os.path.join(BASE_DIR, "voice_design_qwen3_api.json")
OUT_DIR = os.path.join(BASE_DIR, "out")

# ---------------------------------------------------------------- 参考样本文本
# 同一段文本用于所有非方言/非情绪角色，便于横向比较音色。
# 覆盖：陈述句 / 疑问句 / 感叹句 / 列举停顿 / 高低起伏，长度约 10-15 秒。
REFERENCE_TEXT = (
    "今天天气真不错，你要不要一起去公园走走？"
    "远处的山峦连绵起伏，湖水在微风里泛起层层涟漪。"
    "什么？你说明天就要出发了？"
    "嗯，我明白了——那就这样决定吧，一路顺风！"
)

# 情绪变体专用文本：情绪弹性大，能承载惊讶/喜悦/悲伤/愤怒
EMO_TEXT = (
    "啊？真的吗？我……我简直不敢相信。"
    "等一下，你说的是认真的？"
    "好吧，既然是这样，那就这样吧。"
)

# ---------------------------------------------------------------- 方言参考文本
# 方言必须用方言化的文本，否则模型只会用方言口音念普通话（"塑料方言"）
REF_DONGBEI = (
    "今天天气老好了，咋样，咱俩去公园溜达溜达呗？"
    "你看远处那山，一层一层的，湖面让风吹起一圈一圈的波纹。"
    "啥？你说明儿个就走啊？嗯呐，我明白了，那就这么定吧，一路顺风啊！"
)
REF_SICHUAN = (
    "今天天气巴适得很，你要不要一起去公园转一转嘛？"
    "远处那山峦一层一层的，湖头的水遭风吹起一圈圈的波纹。"
    "啥子？你说明天就要出发了嗦？嗯，我晓得咯，那就这么定嘛，一路顺风哈！"
)
REF_YUE = (
    "今日天气真系好，你要唔要一齐去公园行下？"
    "远处嘅山峦连绵起伏，湖水俾风吹起一层层嘅涟漪。"
    "咩话？你听日就要出发呀？嗯，我明白啦，咁就咁决定啦，一路顺风！"
)
REF_BEIJING = (
    "今儿个天气可真不错，你要不要一块儿去公园遛个弯儿？"
    "远处那山峦一层叠一层的，湖面儿上风吹起一圈圈的波纹。"
    "什么？你说明儿就走啊？嗐，我明白了，那就这么着吧，一路顺风儿！"
)
REF_SHANGHAI = (
    "今朝天气老好呃，侬要不要一道去公园兜一圈？"
    "老远个山一层一层个，湖里向个水被风吹起一圈圈个涟漪。"
    "啥？侬讲明朝就要出发啦？嗯，我懂了，葛末就迭能定了，一路顺风！"
)
REF_HENAN = (
    "今天天气可好嘞，你去不去公园转转？"
    "远处那山峦一层一层的，湖面上风吹起一圈圈的波纹。"
    "啥？你说明儿个就走嘞？中，我明白了，那就这么定吧，一路顺风！"
)
REF_TAIWAN = (
    "今天天气超好的欸，你要不要一起去公园走走啊？"
    "远处的山峦一层一层的，湖面上风吹起一圈圈的涟漪。"
    "蛤？你明天就要出发了喔？嗯，我懂了，那就这样决定吧，一路顺风！"
)

# ---------------------------------------------------------------- 角色矩阵
CHARACTERS = [
    # ================= 儿童（细分到 3 / 6 / 8 岁） =================
    ("kid03_m", "3岁男孩·奶声含糊", "儿童", "男", "3岁·奶声奶气",
     "三岁小男孩的声音，音调极高、又细又亮，奶声奶气。吐字含混不清，常常把音发错或漏字，"
     "句子很短、断断续续，边想边说，中间夹着'嗯''那个'之类的停顿。音色稚嫩，"
     "带很多气声和吞咽声，说话像在撒娇，可爱但发音很不标准，完全是小宝宝的说话状态。", ""),
    ("kid03_f", "3岁女孩·软糯稚嫩", "儿童", "女", "3岁·软糯稚嫩",
     "三岁小女孩的声音，音调极高、又细又软，奶声奶气。吐字含混、咬字不准，"
     "句子短且碎，语速慢，有很多停顿和重复。音色稚嫩，带明显的气声和轻微漏风，"
     "像刚学会说话不久的小宝宝在认真地表达，软糯、天真、发音很不标准。", ""),
    ("child_m_lively", "6岁男孩·清脆活泼", "儿童", "男", "6岁·清脆活泼",
     "五六岁小男孩的声音，音调高而清脆，奶声奶气但吐字清楚，语速偏快，"
     "句尾常常不自觉地扬起来，带着天真好奇的劲儿。音色明亮干净，没有杂质，"
     "说话时有孩子气的停顿和换气，偶尔有一点漏风的感觉。情绪饱满，像在跟小伙伴分享新发现。", ""),
    ("child_f_sweet", "6岁女孩·甜美稚嫩", "儿童", "女", "6岁·甜美稚嫩",
     "六七岁小女孩的声音，音调很高很甜，音色轻盈透亮，像风铃一样。语速适中偏快，"
     "吐字带一点孩子气的含糊但整体可辨，句尾习惯性上扬。语气软糯撒娇，"
     "充满童真和想象力，偶尔有一两声清脆的笑意藏在字里行间。", ""),
    ("kid08_m", "8岁男孩·清亮认真", "儿童", "男", "8岁·清亮活泼",
     "八岁小男孩的声音，音调偏高、清脆响亮，吐字已经基本清晰标准，但还保留童声的稚嫩感。"
     "语速偏快，语调起伏大、情绪外放，说话像小学生兴奋地讲学校里发生的事，"
     "活泼、有精神，偶尔说得急了有点喘。没有变声痕迹。", ""),
    ("kid08_f", "8岁女孩·清亮甜美", "儿童", "女", "8岁·清亮甜美",
     "八岁小女孩的声音，音调高、清亮甜美，吐字清晰标准，语速中等偏快，"
     "语调活泼上扬、带着孩子气的夸张。朗读感强，像小学生有感情地朗读课文，"
     "清脆、认真、可爱，声音里有童真但没有幼儿期的含混。", ""),

    # ================= 少年 =================
    ("teen_m_sunny", "少年男·阳光朝气", "少年", "男", "阳光朝气",
     "十五六岁少年的声音，刚过变声期，嗓音清爽里带着一点未定型的青涩，"
     "音高比成年男性略高，音色明亮有朝气。语速较快，语调起伏明显，"
     "充满少年人的热忱和冲劲，说话干脆利落，偶尔有点毛躁。无沙哑，无低沉。", ""),
    ("teen_f_fresh", "少女·清甜灵动", "少年", "女", "清甜灵动",
     "十六七岁高中女生的声音，音色清甜干净，音调偏高但已经脱去童声，"
     "带着少女特有的轻盈感。语速明快，语调活泼有弹性，情绪外放，"
     "说话像在跟朋友聊天，偶尔带一点俏皮的尾音上扬。吐字清晰，气息饱满。", ""),

    # ================= 青年 =================
    ("youth_m_clear", "青年男·清朗温和", "青年", "男", "清朗温和",
     "二十多岁青年男性的声音，音色清朗干净，音高适中，共鸣位置靠前，"
     "说话温和有礼、语速平稳从容，吐字清晰标准。语调自然舒缓，没有夸张起伏，"
     "气质阳光干净，像电台里那种让人舒服的年轻男声。", ""),
    ("youth_m_magnetic", "青年男·磁性低沉", "青年", "男", "磁性低沉",
     "二十七八岁男性声音，音域偏低，音色温暖厚实带有明显磁性的低频共振，"
     "中气十足但不浑厚。语速偏慢，咬字沉稳有力，气息绵长，"
     "语调平直克制、几乎没有上扬，像深夜电台的男主播，松弛且有倾诉感。", ""),
    ("youth_m_energetic", "青年男·活力明快", "青年", "男", "活力明快",
     "二十多岁男性声音，音色明亮有穿透力，语速快、节奏感强，"
     "字与字之间衔接紧凑，重音明确，语调起伏大、富有煽动性和热情，"
     "像带货主播或体育解说，中气足、精神饱满，略带一点喊话式的用力感。", ""),
    ("youth_f_sweet", "青年女·甜美温柔", "青年", "女", "甜美温柔",
     "二十多岁女性的声音，音色柔和甜美，音调中偏高，带着轻微的鼻音和气息感，"
     "语速舒缓，语调温婉上扬，吐字轻柔圆润。气质亲切体贴，说话像在哄人，"
     "尾音常常轻轻飘起来，整体松弛不紧绷。", ""),
    ("youth_f_cool", "青年女·清冷知性", "青年", "女", "清冷知性",
     "二十七八岁女性声音，音调中等偏高，音色清冽纯净、几乎没有杂音，"
     "咬字极为标准清晰，语速平稳，语调克制平直、起伏很小，情绪冷淡理性。"
     "气质疏离而专业，像纪录片解说或有声书里的冷静叙述者。", ""),
    ("youth_f_vivid", "青年女·活力四射", "青年", "女", "活力四射",
     "二十出头女性的声音，音调偏高，音色明亮跳跃，语速快、节奏轻快，"
     "语调起伏夸张、表情丰富，常有上扬的惊叹尾音。中气足、感染力强，"
     "像综艺节目里的活泼女主持，说话带笑意，朝气蓬勃。", ""),

    # ================= 中年 =================
    ("mid_m_mellow", "中年男·醇厚沉稳", "中年", "男", "醇厚沉稳",
     "四十多岁成熟男性的声音，低沉醇厚，嗓音带有自然的胸腔共鸣，"
     "语速平缓从容，吐字清晰标准，语调稳定克制，没有夸张起伏。"
     "气质沉稳可靠、温和内敛，略带阅历感，无沙哑破音，不生硬冰冷也不油腻，"
     "像阅历丰富的儒雅男士，说话松弛自然，停顿合理。", ""),
    ("mid_m_strong", "中年男·浑厚有力", "中年", "男", "浑厚有力",
     "四十多岁男性声音，音域低，音色浑厚粗粝、胸腔和鼻腔共鸣都很重，"
     "中气极足，音量感强。语速慢而稳，每个字都咬得实、落得重，"
     "语调下沉，带有权威感和压迫感，像新闻联播播音员或企业宣传片旁白，"
     "庄重、可信、不容置疑。", ""),
    ("mid_m_gentle", "中年男·温和儒雅", "中年", "男", "温和儒雅",
     "四十多岁男性声音，音调中等，音色温润柔和略带一点书卷气，"
     "语速中等偏慢，咬字轻巧文雅，语调平缓上行、带着讲解的耐心。"
     "气质儒雅亲切，像大学教授或博物馆讲解员，说话不疾不徐，"
     "声音里带着笑意和包容感。", ""),
    ("mid_f_warm", "中年女·温婉柔和", "中年", "女", "温婉柔和",
     "四十岁左右女性的声音，音调中等，音色温润饱满，带着成熟女性特有的柔和质感，"
     "语速舒缓，吐字圆润，语调温和起伏自然。气质亲切包容，"
     "像邻家阿姨或深夜情感节目女主播，说话有安抚感，声音里带着笑意。", ""),
    ("mid_f_crisp", "中年女·干练职业", "中年", "女", "干练职业",
     "三十八九岁职业女性声音，音调中等，音色干脆利落、几乎没有气声，"
     "咬字精准、语速偏快，节奏感和逻辑重音都很明确，语调平稳少起伏。"
     "气质专业干练，像新闻女主播或企业发布会主持人，理性、清晰、有分寸感。", ""),
    ("mid_f_elegant", "中年女·知性优雅", "中年", "女", "知性优雅",
     "四十多岁女性的声音，音调中低，音色细腻优雅带轻微的醇厚感，"
     "语速从容不迫，吐字讲究，语调舒缓下行，句尾常常轻轻收住。"
     "气质知性安静，像文学作品的朗读者，声音里有厚度和分寸，优雅而不冷淡。", ""),

    # ================= 老年 =================
    ("senior_m_hoarse", "老年男·沧桑沙哑", "老年", "男", "沧桑沙哑",
     "七十岁左右老爷爷的声音，音调低沉，音色明显沙哑粗糙、带颗粒感和气息声，"
     "声带松弛使尾音有轻微颤抖和拖沓。语速慢，吐字略含混但基本可辨，"
     "语调起伏小、平淡悠长。像经历过风霜的老者在慢慢讲述往事，"
     "沧桑、质朴、有故事感。", ""),
    ("senior_m_kind", "老年男·慈祥温和", "老年", "男", "慈祥温和",
     "七十多岁老爷爷的声音，音调偏低但柔和不哑，音色温暖带一点老年人的虚化，"
     "语速很慢，语调舒缓上扬、充满善意，句尾常常拖长并轻轻上翘。"
     "像在给孙辈讲故事，慈祥、耐心、让人安心，说话时似乎带着微笑。", ""),
    ("senior_f_kind", "老年女·慈爱温和", "老年", "女", "慈爱温和",
     "七十岁左右老奶奶的声音，音调中偏高但音色发虚发飘，带明显的年龄感，"
     "语速缓慢，吐字有些松散，语调温和起伏，尾音常常软软地拖长。"
     "像邻家奶奶在唠家常，慈爱、絮叨、亲切，说话中气不足但充满疼爱。", ""),
    ("senior_f_hoarse", "老年女·沙哑缓慢", "老年", "女", "沙哑缓慢",
     "七十五岁左右老太太的声音，音调低沉，音色沙哑干涩、有明显的气息摩擦声，"
     "声带松弛导致字与字之间有停顿和拖音。语速很慢，音量偏小，"
     "语调平直少起伏，吐字略含混。像久病或操劳一生的老妪在低声说话，"
     "苍老、迟缓、质朴。", ""),

    # ================= 方言 =================
    ("dia_dongbei_m", "东北话·男声", "方言", "男", "东北话",
     "三十五岁东北男性的声音，说东北话（东北官话）。音色洪亮粗粝、中气足，"
     "平翘舌不分、儿化音多，语调夸张上扬、句尾常带'呗''啊''呢'。"
     "语速中等偏快，干脆利落，气质豪爽幽默、热情直率，像东北大哥在唠嗑。", REF_DONGBEI),
    ("dia_dongbei_f", "东北话·女声", "方言", "女", "东北话",
     "三十二岁东北女性的声音，说东北话（东北官话）。音色爽朗明亮、中气足，"
     "平翘舌不分，语调起伏大、句尾上扬带'呗''呢''啊'。语速快、干脆利落，"
     "气质热情大方、幽默直爽、有点泼辣，像东北大姐在唠家常。", REF_DONGBEI),
    ("dia_sichuan_m", "四川话·男声", "方言", "男", "四川话",
     "三十五岁四川男性的声音，说四川话（西南官话成渝片）。音色洪亮爽快，"
     "n/l 不分、平翘舌不分，语速中等偏快，句尾常带'噻''哈''嘛''嗦'。"
     "语调上扬有弹性、抑扬顿挫明显，气质幽默泼辣、轻松自在，"
     "像成都茶馆里摆龙门阵的本地人。", REF_SICHUAN),
    ("dia_sichuan_f", "四川话·女声", "方言", "女", "四川话",
     "三十岁四川女性的声音，说四川话（西南官话成渝片）。音色清亮偏快、口齿伶俐，"
     "平翘舌不分，句尾常带'嘛''哈''噻'。语速快，语调起伏明显、干脆利落，"
     "气质泼辣爽快又带点俏皮，像成都妹子在聊天。", REF_SICHUAN),
    ("dia_yue_m", "粤语·男声", "方言", "男", "粤语",
     "四十岁中国香港男性的声音，用粤语（广东话）朗读。音色厚实稳重，"
     "语速中等，粤语六声调准确，入声短促，句尾常用'啦''嘅''嘢'。"
     "咬字清晰、语调自然有起伏，气质成熟专业，像香港电台的男播音员。", REF_YUE),
    ("dia_yue_f", "粤语·女声", "方言", "女", "粤语",
     "二十八岁中国香港女性的声音，用粤语（广东话）朗读。音色柔和明亮，"
     "语速中等，粤语六声调准确，句尾常用'啦''喎''嘅''呀'。咬字清晰，"
     "语调起伏自然、温柔有礼，像香港电台的女主持或客服语音。", REF_YUE),
    ("dia_beijing_m", "北京话·男声", "方言", "男", "北京话",
     "四十岁北京男性的声音，说北京话。儿化音极重、吞字明显，"
     "音色松懒带鼻音，语调悠长上扬、句尾常带'儿''呗''呀'。语速中等偏慢，"
     "气质贫嘴、局气、见多识广，像老北京胡同大爷在侃大山，松弛自在。", REF_BEIJING),
    ("dia_shanghai_f", "上海话·女声", "方言", "女", "上海话",
     "四十岁上海女性的声音，说上海话（吴语太湖片）。音色软糯细腻、音调偏高，"
     "语速中等偏快，带吴语特有的连续变调和短促的入声，句尾常带'呀''哦''呃'。"
     "气质精致温婉、讲究体面，像上海阿姨在弄堂里闲话家常。", REF_SHANGHAI),
    ("dia_henan_m", "河南话·男声", "方言", "男", "河南话",
     "四十二岁河南男性的声音，说河南话（中原官话）。音色朴实浑厚，"
     "语速中等，语调下沉、句尾常带'嘞''中''呗'，儿化较少。"
     "气质憨厚实在、直来直去，像中原老乡在地头拉家常。", REF_HENAN),
    ("dia_taiwan_f", "台湾腔·女声", "方言", "女", "台湾腔",
     "二十五岁中国台湾女性的声音，台湾国语腔。音色甜软轻柔，"
     "句尾习惯性上扬并拖长音，常带'欸''喔''啦''蛤'，语速偏慢，咬字轻、气声多。"
     "气质温柔可爱、略带撒娇感，像台湾偶像剧里的女主角在说话。", REF_TAIWAN),

    # ================= 情绪变体 =================
    ("emo_joy_m", "喜悦兴奋·男声", "情绪", "男", "喜悦/兴奋",
     "三十岁男性声音，音色明亮饱满，情绪极度喜悦兴奋：语速快、音调整体抬高，"
     "句尾上扬，重音有力，说到开心处带明显笑意甚至笑声，气息轻快。"
     "像刚得知天大的好消息，压不住的开心要从声音里溢出来。", EMO_TEXT),
    ("emo_joy_f", "喜悦兴奋·女声", "情绪", "女", "喜悦/兴奋",
     "二十六岁女性声音，情绪喜悦兴奋：音调明显抬高、音色明亮轻快，语速快，"
     "句尾上扬且常常拖出欢快的尾音，带着明显的笑声和气声。"
     "像拆到心仪已久的礼物，欢喜、雀跃、感染力强。", EMO_TEXT),
    ("emo_sad_m", "悲伤哽咽·男声", "情绪", "男", "悲伤/哽咽",
     "三十五岁男性声音，情绪悲伤：语速慢、音调低沉下行，音色发虚发哑，"
     "气息不稳带哽咽和轻微抽泣，字与字之间有停顿，句尾无力地下垂。"
     "像刚经历重大失去、强忍着泪水在说话，压抑、疲惫、心碎。", EMO_TEXT),
    ("emo_sad_f", "悲伤哽咽·女声", "情绪", "女", "悲伤/哽咽",
     "三十岁女性声音，情绪悲伤：语速慢，音调低沉下行，音色发颤发虚，"
     "句尾拖长并下垂，气息不稳，带明显的哽咽、鼻塞感和一两声抽泣。"
     "像刚哭过，努力平复情绪却还是忍不住颤抖。", EMO_TEXT),
    ("emo_anger_m", "愤怒激动·男声", "情绪", "男", "愤怒/激动",
     "三十五岁男性声音，情绪愤怒：音色紧绷粗粝、音量明显加大，语速快，"
     "咬字很重、几乎一字一顿，音调忽高忽低、句尾猛地下砸，气息急促带喘息。"
     "像在强压怒火地斥责对方，随时可能爆发。", EMO_TEXT),
    ("emo_anger_f", "愤怒激动·女声", "情绪", "女", "愤怒/激动",
     "三十二岁女性声音，情绪愤怒：音调抬高且尖锐，语速快、语气咄咄逼人，"
     "咬字重、句尾短促下砸，气息急促，声音里带压抑的颤抖和哭腔。"
     "像被激怒后正在激烈地争吵，愤怒中透着委屈。", EMO_TEXT),
    ("emo_fear_f", "恐惧紧张·女声", "情绪", "女", "恐惧/紧张",
     "二十八岁女性声音，情绪恐惧紧张：音色发抖发紧、音调偏高且不稳，"
     "语速忽快忽慢，气息短促、声音发虚，句尾常常断掉或颤抖，中间有倒吸气。"
     "像独自在黑暗中遇到可怕的事，强撑着把话说完。", EMO_TEXT),
    ("emo_surprise_m", "惊讶错愕·男声", "情绪", "男", "惊讶/错愕",
     "三十岁男性声音，情绪惊讶：开头有明显的倒吸气，音调骤然拔高，"
     "语速先快后慢，句尾上扬成问句，音色清亮、气息急促，"
     "中间夹着结巴和'什么''真的假的'之类的下意识反应。"
     "像听到完全意料之外的消息，一时没反应过来。", EMO_TEXT),
    ("emo_cute_f", "撒娇软糯·女声", "情绪", "女", "撒娇/软糯",
     "二十五岁女性声音，撒娇状态：音调明显偏高、音色软糯甜腻，语速偏慢，"
     "尾音拖长并轻轻上扬，带明显的鼻音和气声，咬字略含糊、带一点哼唧。"
     "像年轻女孩在跟恋人讨要东西，甜、软、黏人。", EMO_TEXT),
    ("emo_tired_m", "疲惫无力·男声", "情绪", "男", "疲惫/无力",
     "四十岁男性声音，极度疲惫：语速很慢、音调低沉平直几乎没有起伏，"
     "音色沙哑发虚、中气不足，字与字之间拖沓，句尾无力地下垂并带叹息。"
     "像连续加班三天没睡觉后勉强开口，懒散、倦怠、提不起劲。", EMO_TEXT),
    ("emo_cold_m", "冰冷威胁·男声", "情绪", "男", "严肃/威胁",
     "四十岁男性声音，音色低沉压抑，情绪严肃带威胁感：语速很慢、"
     "音量压得很低但字字清晰，语调平直下沉、几乎没有起伏，句与句之间有刻意停顿。"
     "像反派在平静地下最后通牒，冷静、危险、不怒自威。", EMO_TEXT),
    ("emo_tender_f", "温柔宠溺·女声", "情绪", "女", "温柔/宠溺",
     "三十二岁女性声音，温柔宠溺：音调中低、音色柔软带气声，语速慢，"
     "语调平缓略上扬，咬字轻柔像怕吵醒谁，句尾轻轻收住。"
     "声音里带着笑意和无限耐心，像母亲哄孩子入睡。", EMO_TEXT),
    ("emo_sarcasm_f", "阴阳嘲讽·女声", "情绪", "女", "嘲讽/阴阳",
     "三十岁女性声音，阴阳怪气的嘲讽语气：语调刻意拉长、尾音上翘，"
     "重音落在奇怪的地方，音色带假声和轻微的鼻音哼气，语速慢。"
     "像在明褒暗贬地挤对人，表面客套实则刻薄。", EMO_TEXT),
    ("emo_cry_m", "崩溃大哭·男声", "情绪", "男", "崩溃/哭腔",
     "三十岁男性声音，情绪崩溃大哭：声音完全失控，句与句之间被哭腔和抽泣打断，"
     "音调忽高忽低、破音明显，气息混乱，吐字因哭泣而含混断续，"
     "鼻塞感极重。像再也撑不住、终于哭出声来的状态。", EMO_TEXT),
]


# ---------------------------------------------------------------- API 封装
def load_workflow():
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_prompt(wf, char, seed, lang="Chinese"):
    """克隆工作流并注入当前角色参数"""
    key, name, group, gender, timbre, instr, ref = char
    g = json.loads(json.dumps(wf))
    g["2"]["inputs"]["language"] = lang
    g["6"]["inputs"]["voice_instruction"] = instr
    g["6"]["inputs"]["reference_text"] = ref or REFERENCE_TEXT
    g["6"]["inputs"]["seed"] = seed
    g["3"]["inputs"]["character_name"] = key
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
    texts = []
    for node_id, out in (hist.get("outputs") or {}).items():
        for val in out.values():
            if isinstance(val, list) and val and isinstance(val[0], str):
                texts.append((node_id, "\n".join(val)))
    return texts


# ---------------------------------------------------------------- 主流程
FIELDS = ["key", "name", "group", "gender", "timbre", "seed",
          "audio", "seconds", "instruction", "save_info"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑指定 key，逗号分隔")
    ap.add_argument("--group", default="", help="只跑指定分组，如 方言,情绪")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seed0", type=int, default=1000, help="起始 seed")
    ap.add_argument("--lang", default="Chinese")
    args = ap.parse_args()

    # 先按全量列表编号，保证 seed 稳定（增量跑不会变）
    indexed = list(enumerate(CHARACTERS))
    if args.only:
        keys = {k.strip() for k in args.only.split(",")}
        indexed = [(i, c) for i, c in indexed if c[0] in keys]
    if args.group:
        gs = {g.strip() for g in args.group.split(",")}
        indexed = [(i, c) for i, c in indexed if c[2] in gs]
    if args.limit:
        indexed = indexed[:args.limit]

    os.makedirs(OUT_DIR, exist_ok=True)
    wf = load_workflow()
    client_id = str(uuid.uuid4())

    manifest_path = os.path.join(BASE_DIR, "manifest.csv")
    print(f"待生成 {len(indexed)} 个角色 -> {HOST}\n")

    for n, (idx, char) in enumerate(indexed):
        key, name, group, gender, timbre, instr, ref = char
        seed = args.seed0 + idx
        print(f"[{n+1}/{len(indexed)}] {key} | {group}/{gender}/{timbre}", end=" ... ", flush=True)
        t0 = time.time()
        try:
            g = build_prompt(wf, char, seed, args.lang)
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
            rows_new = [{
                "key": key, "name": name, "group": group, "gender": gender,
                "timbre": timbre, "seed": seed, "audio": os.path.basename(final),
                "seconds": round(elapsed, 1), "instruction": instr,
                "save_info": save_info.replace("\n", " | "),
            }]
        except Exception as e:
            print(f"异常: {type(e).__name__}: {e}")
            rows_new = [{"key": key, "name": name, "group": group, "gender": gender,
                         "timbre": timbre, "seed": seed, "audio": "",
                         "seconds": round(time.time() - t0, 1),
                         "instruction": instr, "save_info": f"ERROR: {e}"}]

        # 增量合并写入 manifest，避免覆盖已有记录
        old = []
        if os.path.exists(manifest_path):
            old = list(csv.DictReader(open(manifest_path, encoding="utf-8-sig")))
        merged = {r["key"]: r for r in old}
        for r in rows_new:
            merged[r["key"]] = r
        order = {c[0]: i for i, c in enumerate(CHARACTERS)}
        # 用角色定义的权威数据补全旧记录（旧版 manifest 缺 group 字段）
        lut = {c[0]: c for c in CHARACTERS}
        for k, r in merged.items():
            c = lut.get(k)
            if c:
                _, name, group, gender, timbre, instr, _ = c
                r.update({"name": name, "group": group, "gender": gender,
                          "timbre": timbre, "instruction": instr})
        out_rows = sorted(merged.values(), key=lambda r: order.get(r["key"], 999))
        with open(manifest_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(out_rows)

    all_rows = list(csv.DictReader(open(manifest_path, encoding="utf-8-sig")))
    ok = sum(1 for r in all_rows if r["audio"])
    print(f"\n本批完成，manifest 合计 {ok}/{len(all_rows)} 个有音频\n音频目录: {OUT_DIR}\n清单: {manifest_path}")


if __name__ == "__main__":
    main()
