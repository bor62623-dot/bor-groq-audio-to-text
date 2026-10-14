# bor-groq-audio-to-text

WorkBuddy 用户级 Skill：调用 Groq API（Whisper large-v3 / large-v3-turbo）把长音频快速转写成文字。面向课堂录音、讲座、播客等 100 分钟级长音频，云端转写约 1 分钟完成（本地 CPU 转写需 1~3 倍实时时长）。

## 功能

- 云端转写：默认 `whisper-large-v3-turbo`（快），可选 `whisper-large-v3`（更准）
- 产出三件套：`.md` 阅读稿（带 `[mm:ss]` 时间戳）、`.srt` 字幕、`.json` 分段数据
- 自动清理：静音幻觉段过滤、重复刷屏丢弃、课间休息标记
- 术语规整：外置 JSON 规则表（`--rules`），按领域自建，附一份通信课程示例
- 上传失败自动重试 3 次；内部用 curl 直传，规避 Windows 下 Python requests 的 SSL 挂起问题

## 安装

依赖：Python 3、ffmpeg、curl。

### WorkBuddy

```bash
git clone https://github.com/bor62623-dot/bor-groq-audio-to-text.git ~/.workbuddy/skills/bor-groq-audio-to-text
```

（Windows 下即 `C:\Users\<用户名>\.workbuddy\skills\`，安装后新会话自动可用。）

### Claude Code

Claude Code 原生支持同格式的 Agent Skills，直接 clone 到个人 skills 目录，新会话自动可用（可用 `/bor-groq-audio-to-text` 直接调用）：

```bash
git clone https://github.com/bor62623-dot/bor-groq-audio-to-text.git ~/.claude/skills/bor-groq-audio-to-text
```

### Codex CLI

Codex 同样支持 SKILL.md 格式的 skills：

```bash
git clone https://github.com/bor62623-dot/bor-groq-audio-to-text.git ~/.codex/skills/bor-groq-audio-to-text
```

如果你的 Codex 版本不认识 skills 目录，用通用兜底法：clone 到任意位置，在 `~/.codex/AGENTS.md` 里加一段：

```markdown
## 音频转写
用户要求转写录音 / 音频转文字时，读取并遵循
<path>/bor-groq-audio-to-text/SKILL.md 的流程执行。
```

### 其他 Agent（通用做法）

本 skill 就是「SKILL.md 说明 + 可执行脚本」的标准结构，任何能读指令文件的 agent 都能用：clone 到它认识的位置（或任意位置），在它的全局配置（AGENTS.md / CLAUDE.md / 系统提示词）里加一行指向 SKILL.md 的引用即可。

## 获取 Groq API Key（免费）

1. 打开 [console.groq.com](https://console.groq.com)，用 Google / GitHub / 邮箱注册，需验证邮箱，无需信用卡
2. 登录后进入左侧 **API Keys** 页面（或直接访问 [console.groq.com/keys](https://console.groq.com/keys)）
3. 点 **Create API Key**，起个名字，提交
4. **立即复制**生成的 `gsk_` 开头的 key——只显示这一次，关掉对话框就再也看不到了；丢了只能重新创建

免费层说明：免费用，但有按分钟/小时/天的配额限制（转写按音频秒数计，`whisper-large-v3` 与 `large-v3-turbo` 配额相互独立，撞限额时换个模型或等下一小时即可）。具体额度以控制台 [Limits](https://console.groq.com/settings/limits) 页显示为准。

## API Key 配置

**仓库里没有任何密钥，也永远不要把 key 提交进来。** key 只放环境变量：

```bash
# Linux / macOS / Git Bash（当前会话）
export GROQ_API_KEY=gsk_xxxxxxxx

# Git Bash 持久化：写入 ~/.bashrc
echo 'export GROQ_API_KEY=gsk_xxxxxxxx' >> ~/.bashrc
```

**Windows PowerShell**：

```powershell
# 当前会话
$env:GROQ_API_KEY = "gsk_xxxxxxxx"

# 持久化：写入用户级环境变量（已打开的终端不生效，新开的终端才生效）
[Environment]::SetEnvironmentVariable("GROQ_API_KEY", "gsk_xxxxxxxx", "User")

# 验证（新开一个 PowerShell 窗口后）
$env:GROQ_API_KEY
```

**Windows CMD**（当前会话）：`set GROQ_API_KEY=gsk_xxxxxxxx`；持久化用上文的 PowerShell 命令，或走图形界面：系统设置 → 环境变量 → 新建 `GROQ_API_KEY`。

脚本启动时读取 `GROQ_API_KEY`，没有则报错退出。`.gitignore` 已包含 `gsk_*`、`.env` 等模式兜底，但最稳妥的做法始终是：key 只存在于环境变量里。

## 使用

以 100 分钟课堂录音为例（完整流程见 SKILL.md，在 WorkBuddy 中对话触发 skill 即自动执行）：

```bash
# 1. 压缩（Groq 上传上限 25MB，长音频必须先压）
ffmpeg -y -i "录音/xxx.m4a" -ar 16000 -ac 1 -c:a libopus -b:a 24k work/xxx.ogg

# 2. 转写（--prompt 写清主题与关键术语，能显著降低误听）
PYTHONIOENCODING=utf-8 python scripts/groq_transcribe.py work/xxx.ogg "转写/xxx-转写" \
    --prompt "本节课讲解扩频通信、码分多址、信道均衡等概念"

# 3. 人工检查 .md，记下课间/静音段的分钟区间

# 4. 清理（--breaks 课间区间；--rules 术语表可选）
PYTHONIOENCODING=utf-8 python scripts/clean_transcript.py "转写/xxx-转写" \
    --breaks "45.5-54.8" --rules references/term-rules-example.json
```

## 自定义术语规整

`--rules` 接受 JSON 文件，格式为 `[["正则", "替换"], ...]`，见 `references/term-rules-example.json`。不传则只做通用清理。注意：规则替换较激进，跨领域复用前先核对，避免误伤正常文本。

## Windows / Git Bash 注意

- Python 命令前加 `PYTHONIOENCODING=utf-8`，否则中文输出 GBK 乱码
- 中间文件放 Windows 路径，不要用 Git Bash 的 `/tmp`
- 压缩与上传是长任务，建议后台运行

## License

[MIT](LICENSE)
