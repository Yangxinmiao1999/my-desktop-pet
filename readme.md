# 桌面宠物 - 皮卡丘 ⚡

一只 AI 生成的 2D 皮卡丘桌面宠物，基于 PyQt5 构建，支持 AI 对话、表情动作、计时与提醒。

<p align="center">
  <img src="assets/pika2d/pika2d.png" alt="AI 生成的皮卡丘形象" width="360">
</p>

> 🎨 上面的皮卡丘形象由 **AI 生成**（Qwen-Image 图像模型 + MiniMax-H3 视频模型），
> 包括角色本体、12 个动作表情全部由 AI 生成后抠图制作。

## ⚡ 一键启动（推荐）

**下载仓库里的 `启动皮卡丘.exe`，双击即可运行**，无需安装 Python、无需配置环境。

启动后右键皮卡丘可以进行设置；首次使用 AI 对话功能前，请按下面「配置 API」一节填入自己的 API Key。

> exe 启动器会自动查找本机的 Python 环境运行主程序，素材更新后无需重新打包。
> 如果你的电脑没有 Python 环境，请参考下方「从源码运行」。

## 功能特性

- **2D 皮卡丘形象** - AI 生成角色，透明背景，可拖拽移动
- **12 个动作/表情** - 呼吸、眨眼、走动、摇摆、开心跳、歪头、睡眠、唤醒、跳跃挥手、爱心欢呼、大笑摇摆、害羞捂脸
- **表情自动轮换** - 每 6 秒左右自动变化表情，右键「表情 / 动作」菜单可手动指定
- **AI 对话** - 接入 OpenAI 兼容 API（默认硅基流动），头顶气泡回复
- **Agent 模式** - 基于 LangChain 的智能代理，支持工具调用
- **计时模块** - 单击皮卡丘开始计时，再点结束，自动记录今日累计时长
- **字号设置** - 右键菜单可分别调整显示字号与对话字号
- **技能系统 / MCP 协议** - 可扩展技能模块与外部工具
- **待办 & 休息提醒** - 定时提醒，保护健康

<p align="center">
  <img src="assets/preview/actions_preview.jpg" alt="AI 生成的动作表情一览" width="560">
</p>

*跳跃挥手 / 爱心欢呼 / 大笑摇摆 / 害羞捂脸 —— 由 MiniMax-H3 图生视频制作，已转为透明 GIF*

## 快速开始（从源码运行）

### 1. 环境要求

- Python 3.8+
- Windows / macOS

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 API

复制配置模板并填入自己的 API Key：

```bash
cp config_example.yaml config.yaml
```

```yaml
api:
  base_url: "https://api.siliconflow.cn/v1"
  api_key: "your-api-key-here"   # 换成你的 Key
  model: "deepseek-ai/DeepSeek-V4.1-Flash"
```

> 支持任意 OpenAI 兼容接口（硅基流动、DeepSeek 官方、OpenAI 等）。
> `config.yaml` 已加入 `.gitignore`，不会被提交，请勿把 Key 传到网上。

### 4. 运行

```bash
python main.py
```

## 使用说明

| 操作 | 效果 |
|------|------|
| **单击** 皮卡丘 | 开始计时 / 再次单击结束计时 |
| **拖拽** 皮卡丘 | 移动位置 |
| **右键** 皮卡丘 | 聊天、计时、表情 / 动作、字号设置、隐藏、退出 |
| **等待几秒** | 表情自动变化（眨眼、跳跃、害羞……） |

## 项目结构

```
├── main.py               # 入口
├── 启动皮卡丘.exe         # Windows 一键启动器（皮卡丘图标）
├── ui/                   # 界面（宠物窗口、聊天窗、字号设置）
├── core/                 # AI 对话、技能、用户画像
├── utils/                # 计时存储等工具
├── assets/pika2d/        # AI 生成的皮卡丘素材与动作包
└── config_example.yaml   # 配置模板
```

## 素材制作说明

皮卡丘形象与全部动作为 AI 生成：

1. **角色形象**：Qwen-Image 文生图生成，程序去水印、去背景
2. **表情**：Qwen-Image-Edit 图生图（眨眼大笑等）
3. **复杂动作**（跳跃挥手、爱心欢呼、大笑摇摆、害羞捂脸）：MiniMax-H3 图生视频 → 抽帧 → 抠图 → 透明 GIF
4. **简单动作**（呼吸、眨眼、走动等）：母版图 + 表情帧程序合成

## 许可证

本项目基于 MIT 许可证开源，详见 [LICENSE](LICENSE)。

素材由 AI 生成，形象灵感来源于宝可梦皮卡丘，仅供学习交流使用。
