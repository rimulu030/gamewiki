# GameWiki - AI-Powered In-Game Assistant 

> **Smart game companion that never leaves your side** - Real-time wiki overlay + AI knowledge base for instant answers while gaming

![Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-blue?logo=windows)
![Python](https://img.shields.io/badge/Python-3.8%2B-green?logo=python)
![Games](https://img.shields.io/badge/AI%20Games-4%20Supported-orange?logo=gamepad)
![License](https://img.shields.io/badge/License-GPL3.0-yellow)

👉 **[中文说明](README.zh-CN.md)** | **[Quick Start](#-quick-install)**  |  **[Join Our Discord](https://discord.gg/5HHjNdmYtm)**

## ✨ Why GameWiki?

Never alt-tab out of your game again! Get instant answers, build guides, and wiki information directly in your game with our AI-powered overlay.

### 🎯 Key Features

- **🔥 One Hotkey, All Answers** - Press `Ctrl+Q` to instantly overlay wiki/AI chat without leaving your game
- **🤖 AI Game Expert** - Powered by Google Gemini with local knowledge bases for smart Q&A. 

To use the AI chatbot feature, you will need to have a google account and get gemini API from Google AI Studio.

_"The **Gemini API** "free tier" is offered through the API service with lower [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits#free-tier) for testing purposes. Google AI Studio usage is **completely free** in all available countries" - according to [Gemini API docs](https://ai.google.dev/gemini-api/docs/pricing)_
## 📸 Screenshots
- Use as AI assitant

![Demo](data/demo1.gif)

**[View use video](https://www.youtube.com/watch?v=9QPJ6KVg7gE)**

- Quick access to Wikis
![Demo](data/demo3.gif)
![Demo](data/demo4.png)
- Use as an web browser
![Demo](data/demo2.gif)



## 🚀 Quick Install

### Run from Source
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
2. **API Key** (Optional): Add Gemini API key for AI features
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
- 🎮 Adding new game support/Knowledge data base. [How to build a new knowledge base](src/game_wiki_tooltip/ai/README.md)
- 🐛 Bug fixes
- 📚 Documentation improvements
- Project Optimization

## 📄 License

With the usage of Pyqt6, we use GPL3.0 License - See [LICENSE](LICENSE) file

## 🙏 Acknowledgments

- **Google Gemini AI** - Powering intelligent responses
- **Gaming Communities** - For wiki content and knowledge

## Contact me 

- Weizhen Chu
- chu.weizhen04@gmail.com
- X profile: https://x.com/ChengXiang75007
---

<div align="center">

**⭐ Star us if this helps your gaming experience!**

[Report Issue](https://github.com/rimulu030/gamewiki/issues) · [Join Our Discord](https://discord.gg/5HHjNdmYtm)

</div>
