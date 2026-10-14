"""Groq API 音频转写（curl 上传版：Windows 下 Python requests 会 SSL 挂起，curl 稳定）。

用法：
  python groq_transcribe.py <audio> <output_prefix> [model] [--prompt "内容主题与关键术语"] [--lang zh]

示例：
  python groq_transcribe.py work/xxx.ogg "转写/xxx-转写" whisper-large-v3-turbo --prompt "本节课讲解扩频通信、码分多址等概念"

输出：prefix.md（阅读稿，带时间戳）、prefix.srt（字幕）、prefix.json（分段数据），并打印统计。

API key：只从环境变量 GROQ_API_KEY 读取（申请方式见 README）。
"""
import io, json, os, re, subprocess, sys, tempfile, time

argv = sys.argv[1:]
prompt, lang = None, "zh"
if "--prompt" in argv:
    i = argv.index("--prompt")
    prompt = argv[i + 1]
    del argv[i:i + 2]
if "--lang" in argv:
    i = argv.index("--lang")
    lang = argv[i + 1]
    del argv[i:i + 2]
audio, prefix = argv[0], argv[1]
model = argv[2] if len(argv) > 2 else "whisper-large-v3-turbo"

KEY = os.environ.get("GROQ_API_KEY", "").strip()
if not KEY:
    sys.exit("no API key: set the GROQ_API_KEY environment variable (how to get one: see README)")

# whisper 静音/幻觉输出的通用过滤模式（中文 ASR 常见幻觉）
HALLU = re.compile(r"点赞|订阅|转发|打赏|明镜|字幕|Amara|下期再见|感谢观看|本节目|MING PAO|点击")

tmp = tempfile.mkdtemp()
fwd = lambda p: p.replace("\\", "/")  # curl 配置文件里反斜杠是转义符，路径统一用正斜杠
prompt_file = os.path.join(tmp, "prompt.txt")
cfg_file = os.path.join(tmp, "curl.cfg")
resp_file = os.path.join(tmp, "resp.json")

cfg_lines = [
    'url = "https://api.groq.com/openai/v1/audio/transcriptions"',
    f'header = "Authorization: Bearer {KEY}"',
    f'form = "file=@{fwd(audio)}"',
    f'form = "model={model}"',
    f'form = "language={lang}"',
    'form = "response_format=verbose_json"',
    'form = "temperature=0"',
    f'output = "{fwd(resp_file)}"',
]
if prompt:
    io.open(prompt_file, "w", encoding="utf-8").write(prompt)
    cfg_lines.insert(-1, f'form = "prompt=<{fwd(prompt_file)}"')
io.open(cfg_file, "w", encoding="utf-8").write("\n".join(cfg_lines) + "\n")

t0 = time.time()
ok = False
for attempt in range(1, 4):
    # --ssl-no-revoke: Windows schannel 吊销列表检查常因网络不可达报 rc=35
    p = subprocess.run(["curl", "-s", "--ssl-no-revoke", "--max-time", "1800", "-K", cfg_file],
                       capture_output=True)
    if p.returncode == 0 and os.path.exists(resp_file) and os.path.getsize(resp_file) > 0:
        ok = True
        break
    print(f"attempt {attempt} failed: rc={p.returncode} {p.stderr[:200]}", flush=True)
    time.sleep(10 * attempt)
if not ok:
    sys.exit("curl upload failed")
print(f"[{time.time()-t0:.0f}s] response received", flush=True)

d = json.load(open(resp_file, encoding="utf-8"))
if "segments" not in d:
    print(json.dumps(d)[:500])
    sys.exit("no segments in response (API error?)")

segs, dropped = [], 0
for s in d["segments"]:
    text = s["text"].strip()
    if not text:
        continue
    if len(text) < 30 and HALLU.search(text):
        dropped += 1
        continue
    segs.append({"start": s["start"], "end": s["end"], "text": text})

with io.open(prefix + ".json", "w", encoding="utf-8") as f:
    json.dump(segs, f, ensure_ascii=False, indent=1)

def ts(sec):
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"

paras, cur, last_end = [], [], None
for s in segs:
    if last_end is not None and s["start"] - last_end > 2.5 and cur:
        paras.append((cur[0]["start"], "".join(x["text"] for x in cur)))
        cur = []
    cur.append(s)
    last_end = s["end"]
if cur:
    paras.append((cur[0]["start"], "".join(x["text"] for x in cur)))

with io.open(prefix + ".md", "w", encoding="utf-8") as f:
    for start, text in paras:
        f.write(f"**[{ts(start)}]** {text}\n\n")

def srt_t(x):
    h = int(x // 3600); m = int(x % 3600 // 60); sec = x % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")

with io.open(prefix + ".srt", "w", encoding="utf-8") as f:
    for i, s in enumerate(segs, 1):
        f.write(f"{i}\n{srt_t(s['start'])} --> {srt_t(s['end'])}\n{s['text']}\n\n")

print(f"done: {len(segs)} segs, {dropped} hallucinations dropped, "
      f"{len(paras)} paras -> {prefix}.md/.srt/.json in {time.time()-t0:.0f}s")
