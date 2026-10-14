"""合并分片转写：把 part1/part2... 的 json 按偏移拼成一个 prefix.json。

用法：
  python merge_transcripts.py <输出prefix> --split "5410[,10800...]" <分片prefix1> <分片prefix2> [...]

--split：各分片在原始录音里的起始秒数（= 切分时用的 -t/-ss 值），逗号分隔。
  2 片传 1 个值，3 片传 2 个，依此类推。
  例：整段切成 0-5410s 和 5410s-末尾 -> --split 5410

合并后写 <输出prefix>.json，随后对该 prefix 跑 clean_transcript.py 出三件套。
"""
import io, json, os, subprocess, sys

argv = sys.argv[1:]
if "--split" not in argv or len(argv) < 3:
    sys.exit(__doc__)
i = argv.index("--split")
splits = [float(x) for x in argv[i + 1].split(",")]
del argv[i:i + 2]
out, parts = argv[0], argv[1:]

if len(splits) != len(parts) - 1:
    sys.exit(f"--split 需要 {len(parts)-1} 个值（{len(parts)} 片），实际给了 {len(splits)} 个")

merged = []
for n, (p, off) in enumerate(zip(parts, [0.0] + splits)):
    src = p + ".json"
    if not os.path.exists(src):
        sys.exit(f"缺文件：{src}")
    segs = json.load(io.open(src, encoding="utf-8"))
    if not segs:
        sys.exit(f"{src} 是空的")
    # 自检：分片的时长应约等于它在原录音里的区间长，差太多说明 --split 传错了
    span, got = (splits + [None])[n] - off if n < len(splits) else None, segs[-1]["end"]
    if span is not None and abs(got - span) > 60:
        sys.exit(f"{src} 末段 {got:.0f}s，与 --split 推出的区间长 {span:.0f}s 差超过 60s，"
                 f"检查 --split 是否传错")
    merged += [{"start": s["start"] + off, "end": s["end"] + off, "text": s["text"]} for s in segs]

json.dump(merged, io.open(out + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{len(parts)} 片 -> {len(merged)} 段，总长 {merged[-1]['end']:.1f}s -> {out}.json")
