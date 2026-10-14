---
name: bor-groq-audio-to-text  
description: 用 Groq API（whisper-large-v3-turbo）把长音频快速转写成文字：课堂录音、讲座、播客等 m4a/mp3/wav 文件转文字稿、字幕。输出 .md 阅读稿（带时间戳）、.srt 字幕、.json 分段数据，并自动过滤静音幻觉、标记课间、可选术语规整。当用户要"用groq转写录音/转写录音/音频转文字/生成字幕/出字幕文件/转写课堂录音"时使用本技能。  
agent_created: true
---

# bor-groq-audio-to-text

把长音频（100 分钟级别的课堂录音、讲座等）通过 Groq 云端 whisper 模型转写成文字。100 分钟录音约 1 分钟转完（本地 CPU 转写要 1~3 倍实时时长，故优先云端）。产出三件套：`.md`（阅读稿）、`.srt`（字幕）、`.json`（分段数据）。

## 前置条件

1. **API key**（缺则停止并告知用户按 README 申请配置）：
   - 环境变量 `GROQ_API_KEY`（本机已配置则直接可用）
   - 永远不要把 key 打印到输出或写进任何文件。
2. `ffmpeg` 和 `curl` 在 PATH 中。

## 工作流程（6 步）

### 1. 压缩音频（顺带量时长）

**先量时长——它决定要不要切分**：

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 "录音/xxx.m4a"
```

Groq 上传上限 25MB。100 分钟录音压成 24k 码率单声道 opus（约 18MB）：

```bash
ffmpeg -y -i "录音/xxx.m4a" -ar 16000 -ac 1 -c:a libopus -b:a 24k work/xxx.ogg
```

约 1~2 分钟，建议后台运行。短音频（< 25MB）可跳过直接上传原文件。

> **两个上限别混**：25MB 是**文件大小**，压缩能解决；**7200 秒（2 小时）是单请求音频时长**，压缩解决不了，只能先切。3 小时录音压完只有 23MB，**轻松过 25MB 检查却一头撞上 7200s**——所以先看时长，再看体积。

### 2. 切分（时长 > 7200s 时必须）

每片必须 < 7200s，按 90 分钟切最省事。以 10828s（约 3 小时）的录音为例，切成 0–5410s 和 5410s–末尾：

```bash
ffmpeg -y -i "录音/xxx.m4a" -t 5410 -ar 16000 -ac 1 -c:a libopus -b:a 24k work/xxx-part1.ogg
ffmpeg -y -i "录音/xxx.m4a" -ss 5410 -ar 16000 -ac 1 -c:a libopus -b:a 24k work/xxx-part2.ogg
```

**记下切点秒数（这里是 5410）**，第 4 步合并要用。

### 3. Groq 转写

```bash
PYTHONIOENCODING=utf-8 python <skill目录>/scripts/groq_transcribe.py work/xxx.ogg "转写/xxx-转写" [model] --prompt "主题描述"
```

- `model`：默认 `whisper-large-v3-turbo`（快、便宜）；要求更高准确率时用 `whisper-large-v3`（更慢）。
- `--prompt` **强烈建议传**：写清音频内容的主题和关键术语（逗号分隔罗列，如"本节课讲解扩频通信、码分多址、信道均衡等概念"）。whisper 会参考 prompt 选词，能显著降低专业术语的误听率。
- `--lang`：默认 `zh`，其他语言显式传。
- 上传失败自动重试 3 次。转写本身是长任务（数分钟），后台运行并等待完成通知。
- 脚本内部用 curl 上传（`--ssl-no-revoke`），因为 Windows 下 Python requests 会 SSL 挂起——不要改回 requests。
- **切过片就一片跑一次**，每片落到自己的 prefix（`work/xxx-part1.ogg` → `"转写/xxx-part1-转写"`）。
- **免费层有每小时音频秒数配额（ASPH）**：约 7200 音频秒/小时。一节 3 小时的课切成两片后，第二片常常要等下一个小时窗才有额度——**这不是卡死，是配额在排队**，等着就行。撞限流也可以换另一个模型试（`whisper-large-v3` 与 `whisper-large-v3-turbo` 配额相互独立）。

### 4. 合并分片（切过才做）

```bash
PYTHONIOENCODING=utf-8 python <skill目录>/scripts/merge_transcripts.py "转写/xxx-转写" --split 5410 "转写/xxx-part1-转写" "转写/xxx-part2-转写"
```

- `--split`：各分片在**原始录音**里的起始秒数，逗号分隔——2 片传 1 个值，3 片传 2 个。就是第 2 步记下的切点。
- 脚本把后片的全部时间戳加上偏移再拼接，写出 `转写/xxx-转写.json`。
- 内置自检：某片末段时长与 `--split` 推出的区间长相差超过 60s 就报错退出。**切点传错会当场暴露，不会静默产出错时间轴。**
- 合并完对**合并后的** prefix 跑第 6 步的 clean，不要对分片跑。

### 5. 检查课间与幻觉

读取生成的 `.md` 或 `.json`，定位两类需要清理的段：

- **课间休息段**：长时间静音后出现"感谢观看/本节目/点赞订阅"类幻觉文字（典型课堂录音约 100 分钟，课间常在中段 44~55 分钟处）。记下起止的分钟区间。
- **连续重复短句**：同一句 ≤10 字重复刷屏（如"小丁。"×12）。

### 6. 清理规整

```bash
PYTHONIOENCODING=utf-8 python <skill目录>/scripts/clean_transcript.py "转写/xxx-转写" --breaks "45.5-54.8" --rules <skill目录>/references/term-rules-example.json
```

- `--breaks`：课间分钟区间，逗号分隔多个（如 `"43.3-52.9,88.1-90.2"`），这些段替换为"课间休息"标记。
- `--rules`：可选，术语规整表 JSON（`[["正则", "替换"], ...]`）。`references/term-rules-example.json` 是现代通信技术课程的规则；其他领域自建同格式文件。**不传则只做通用清理**——注意规则表里的替换较激进（如"不长"→"步长"），跨领域复用前先核对，避免误伤。
- 通用清理始终执行：幻觉短句过滤（<30 字且命中通用幻觉模式）、连续重复短句丢弃、纯标点段丢弃。
- 原始转写自动备份为 `prefix-raw.json`，重复运行 clean 从 raw 重新生成，幂等。

## 产物格式

- `.md`：按 >2.5 秒停顿分段、每段带 `[mm:ss]` 时间戳的阅读稿。
- `.srt`：标准字幕文件。
- `.json`：`[{start, end, text}]` 分段数据（秒）。

## 注意事项（Windows / Git Bash）

- **开工第一件事是量时长**：超过 7200s 就必须先切分（第 2 步），否则上传再多也是白跑。
- 所有 Python 命令前加 `PYTHONIOENCODING=utf-8`，否则中文输出重定向到文件会 GBK 乱码。
- 中间文件放 Windows 路径，不要用 Git Bash 的 `/tmp`（Windows Python 不认）。
- 传给原生 Windows 程序的路径用 Windows 风格或相对路径，避免 MSYS 路径转换 bug。
- 长任务（压音频、上传转写）一律后台运行。
