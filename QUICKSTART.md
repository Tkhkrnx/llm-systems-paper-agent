# 快速开始

## 1. 确认 Obsidian Vault

默认 vault：

```text
C:/Users/peng/Documents/PHR/obsidian_phr
```

环境变量：

```powershell
[System.Environment]::SetEnvironmentVariable(
  "OBSIDIAN_VAULT_PATH",
  "C:/Users/peng/Documents/PHR/obsidian_phr",
  "User"
)
```

## 2. 安装依赖

基础依赖：

```powershell
pip install -r requirements.txt
```

MinerU 已在本机按源码 editable 安装。若需要重新安装：

```powershell
cd C:/Users/peng/Documents/PHR/Intellistream/projects/MinerU-mineru-3.1.5-released
python -m pip install -e ".[all]" -i https://mirrors.aliyun.com/pypi/simple
mineru --version
```

## 3. 安装配置

将 `config.yaml` 复制到 vault：

```powershell
New-Item -ItemType Directory -Force "C:/Users/peng/Documents/PHR/obsidian_phr/99_System/Config"
Copy-Item config.yaml "C:/Users/peng/Documents/PHR/obsidian_phr/99_System/Config/research_interests.yaml" -Force
```

## 4. 安装 skills 到 Obsidian

```powershell
$vaultSkills = "C:/Users/peng/Documents/PHR/obsidian_phr/.claude/skills"
Copy-Item -Recurse -Force start-my-day $vaultSkills
Copy-Item -Recurse -Force conf-papers $vaultSkills
Copy-Item -Recurse -Force paper-search $vaultSkills
Copy-Item -Recurse -Force paper-ingest $vaultSkills
Copy-Item -Recurse -Force paper-analyze $vaultSkills
Copy-Item -Recurse -Force extract-paper-images $vaultSkills
```

## 5. 在 Obsidian 中使用

打开 Obsidian vault 后，在 Claudian/Claude Code 对话中输入：

```text
使用 start-my-day，今天给我推荐3篇 LLM serving 和状态优化方向的论文，并保存 PDF、MinerU Markdown、图片和结构化笔记。
```

```text
使用 conf-papers，搜索 2025 年 MICRO、ASPLOS、SC、PPoPP、NeurIPS、ICML、ICLR 中与 KV cache 和 LLM serving 相关的论文。
```

```text
使用 paper-ingest，导入 arXiv:2402.12345，领域设为 LLM Inference Systems。
```

```text
使用 paper-search，在已有笔记和 MinerU Markdown 里搜索 continuous batching 和 state placement。
```

## 6. 输出位置

```text
10_Daily/                                  每日推荐
20_Research/Papers/<domain>/              结构化论文笔记
20_Research/Papers/_assets/<paper>/        PDF、MinerU Markdown、图片
99_System/Config/research_interests.yaml   agent 配置
```

