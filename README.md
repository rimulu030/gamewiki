# GameWikiTooltip - AI-Powered In-Game Assistant 

> **Smart game companion that never leaves your side** - Real-time wiki overlay + AI knowledge base for instant answers while gaming

![Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-blue?logo=windows)
![Python](https://img.shields.io/badge/Python-3.8%2B-green?logo=python)
![Games](https://img.shields.io/badge/AI%20Games-4%20Supported-orange?logo=gamepad)
![License](https://img.shields.io/badge/License-MIT-yellow)
[![GitHub Release](https://img.shields.io/github/v/release/rimulu030/gamewiki?include_prereleases)](https://github.com/rimulu030/gamewiki/releases)

👉 **[中文说明](README.zh-CN.md)** | **[Quick Start](#-quick-install)** | **[Download Latest Release](https://github.com/rimulu030/gamewiki/releases/latest)** |  **[Join Our Discord](https://discord.gg/WdZVcnQ2)**

## ✨ Why GameWikiTooltip?

Never alt-tab out of your game again! Get instant answers, build guides, and wiki information directly in your game with our AI-powered overlay.

### 🎯 Key Features

- **🔥 One Hotkey, All Answers** - Press `Ctrl+Q` to instantly overlay wiki/AI chat without leaving your game
- **🤖 AI Game Expert** - Powered by Google Gemini with local knowledge bases for smart Q&A
- **🎮 Auto Game Detection** - Automatically recognizes your active game and loads relevant content
- **💬 Voice Input Support** - Ask questions using voice commands (built-in Vosk recognition)

## 📸 Screenshots

![Demo](data/demo.gif)
**[View use video](https://your-video-or-doc-link)**

## 🚀 Quick Install

### Option 1: Download Ready-to-Use Package (Recommended)
1. **[⬇️ Download Latest Release](https://github.com/rimulu030/gamewiki/releases/download/v1.0.0/GameWikiAssistant_Portable_onedir.zip)**
2. Extract the ZIP file
3. Run `GameWikiAssistant/GameWikiAssistant.exe`
4. Set your hotkey and start gaming!

### Option 2: Run from Source
```bash
# Clone and setup
git clone https://github.com/rimulu030/gamewiki.git
cd gamewiki
pip install -r requirements.txt

# Configure API key for AI features (optional)
set GEMINI_API_KEY=your_key_here  # Windows

# Run
python -m src.game_wiki_tooltip
```

## 🎮 Supported Games

### 🤖 AI-Enhanced Games (Full Knowledge Base)
| Game | Features |
|------|----------|
| **HELLDIVERS 2** | Weapons, Stratagems, Enemy Weaknesses |
| **Elden Ring** | Items, Bosses, Build Guides |
| **Don't Starve Together** | Crafting, Characters, Survival Tips |
| **Civilization VI** | Civs, Units, Victory Strategies |

### 📖 Wiki-Supported Games
Quick wiki access for 100+ games including: VALORANT, CS2, Monster Hunter, Stardew Valley, and more!

## 🔧 Configuration

### First Launch Setup
1. **Hotkey Setup**: Choose your preferred activation key (default: `Ctrl+Q`)
2. **API Key** (Optional): Add Gemini API key for enhanced AI features
3. **Game Detection**: Automatic - just launch your game!

### Advanced Settings
- Custom hotkey combinations
- Language preferences (EN/ZH)
- Wiki sources configuration
- Voice recognition settings

## 📚 Documentation

- **[Quick Start Guide](docs/QUICKSTART.md)** - Get started in 5 minutes
- **[FAQ](docs/FAQ.md)** - Common questions and solutions
- **[Build Guide](docs/BUILD.md)** - Build your own executable
- **[Architecture](docs/ARCHITECTURE.md)** - Technical deep dive
- **[AI Module Docs](src/game_wiki_tooltip/ai/README.md)** - AI system details

## 🐛 Troubleshooting

| Issue                   | Quick Fix |
|-------------------------|-----------|
| **Hotkey not working**  | Run as Administrator / Change hotkey combination |
| **Game not detected**   | Check supported games list|
| **AI not responding**   | Verify API key in settings |
| **Website not showing** | Install WebView2 Runtime (included in package) |

For more solutions, see [FAQ](docs/FAQ.md) or [report an issue](https://github.com/rimulu030/gamewiki/issues).

## 🤝 Contributing

We love contributions! Whether it's:
- 🎮 Adding new game support
- 🐛 Bug fixes
- 📚 Documentation improvements
- Project Optimization

## 📄 License

MIT License - See [LICENSE](LICENSE) file

## 🙏 Acknowledgments

- **Google Gemini AI** - Powering intelligent responses
- **FAISS** - Lightning-fast vector search
- **Gaming Communities** - For wiki content and knowledge
- **Contributors** - Making this tool better every day

---

<div align="center">

**⭐ Star us if this helps your gaming experience!**

[Report Issue](https://github.com/rimulu030/gamewiki/issues) · [Join Our Discord](https://discord.gg/WdZVcnQ2)

</div>