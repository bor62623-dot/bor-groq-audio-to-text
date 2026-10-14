"""转写稿清理：幻觉段过滤 + 课间休息标记 + 可选术语规整。

用法：
  python clean_transcript.py <prefix> [--breaks "43.3-52.9,88.1-90.2"] [--rules rules.json]

读 prefix.json（原始转写），备份为 prefix-raw.json，然后覆盖写 .md/.srt/.json。
--breaks：课间/静音段的分钟区间，逗号分隔，这些段会被"课间休息"标记替代。
--rules：术语规整表，JSON 格式 [["正则", "替换"], ...]，见 references/term-rules-example.json。
  不传则只做通用清理（幻觉过滤、重复短句丢弃、纯标点过滤），不做术语替换。

通用清理规则：
  - 疑似幻觉短句（<30 字且命中"点赞/订阅/感谢观看"等模式）丢弃
  - 连续重复短句（同文 >=4 次且 <=10 字，幻觉刷屏）整段丢弃
  - 纯标点段丢弃
"""
import io, json, os, re, sys

prefix = sys.argv[1]
breaks = []
if "--breaks" in sys.argv:
    spec = sys.argv[sys.argv.index("--breaks") + 1]
    breaks = [tuple(float(x) for x in p.split("-")) for p in spec.split(",")]

RULES = []
if "--rules" in sys.argv:
    rules_path = sys.argv[sys.argv.index("--rules") + 1]
    RULES = [tuple(x) for x in json.load(open(rules_path, encoding="utf-8"))]

HALLU = re.compile(r"点赞|订阅|转发|打赏|明镜|字幕|Amara|下期再见|感谢观看|本节目|MING PAO|点击")

raw_path = prefix + "-raw.json"
src = raw_path if os.path.exists(raw_path) else prefix + ".json"
segs = json.load(open(src, encoding="utf-8"))
if not os.path.exists(raw_path):
    json.dump(segs, open(raw_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

stats = {"rules": {}, "hallu": 0, "duprun": 0}

# 连续重复短句（幻觉刷屏，如 "小丁。x12"）整段丢弃
drop_idx = set()
i = 0
while i < len(segs):
    j = i + 1
    while j < len(segs) and segs[j]["text"].strip() == segs[i]["text"].strip():
        j += 1
    if j - i >= 4 and len(segs[i]["text"].strip()) <= 10:
        drop_idx.update(range(i, j))
        stats["duprun"] += j - i
    i = j
out = []
for brk in sorted(breaks):
    out.append({"start": brk[0] * 60, "end": brk[1] * 60,
                "text": f"（课间休息约 {brk[1]-brk[0]:.0f} 分钟）", "marker": True})

for idx, s in enumerate(segs):
    if idx in drop_idx:
        continue
    if any(brk[0] * 60 <= s["start"] < brk[1] * 60 for brk in breaks):
        continue
    t = s["text"].strip()
    if not t or re.fullmatch(r"[。，、！？.\s]+", t):
        continue
    if len(t) < 30 and HALLU.search(t):
        stats["hallu"] += 1
        continue
    for pat, rep in RULES:
        t, n = re.subn(pat, rep, t)
        if n:
            stats["rules"][pat] = stats["rules"].get(pat, 0) + n
    out.append({"start": s["start"], "end": s["end"], "text": t})

out.sort(key=lambda x: x["start"])
print("dropped hallucinations:", stats["hallu"], "| duplicate-run segments:", stats["duprun"])
print("rule hits:", {k: v for k, v in stats["rules"].items() if v})
print("segments:", len(segs), "->", len(out))

def ts(sec):
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"

paras, cur, last_end = [], [], None
for s in out:
    if last_end is not None and s["start"] - last_end > 2.5 and cur:
        paras.append((cur[0]["start"], "".join(x["text"] for x in cur)))
        cur = []
    cur.append(s)
    last_end = s["end"]
if cur:
    paras.append((cur[0]["start"], "".join(x["text"] for x in cur)))

name = os.path.basename(prefix).replace("-转写", "")
with io.open(prefix + ".md", "w", encoding="utf-8") as f:
    f.write(f"# {name} 转写\n\n")
    f.write("> 转写：Whisper（Groq）| 自动转写 + 清理，个别字词可能有误\n\n")
    for start, text in paras:
        f.write(f"**[{ts(start)}]** {text}\n\n")

def srt_t(x):
    h = int(x // 3600); m = int(x % 3600 // 60); sec = x % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")

with io.open(prefix + ".srt", "w", encoding="utf-8") as f:
    for i, s in enumerate(out, 1):
        f.write(f"{i}\n{srt_t(s['start'])} --> {srt_t(s['end'])}\n{s['text']}\n\n")

json.dump(out, open(prefix + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("written:", prefix, ".md/.srt/.json (+ -raw.json backup)")
