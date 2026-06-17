# 📱 SociaBot — Social Media Downloader

A Telegram bot that downloads videos, photos, and stories from YouTube, Instagram, and TikTok. Just paste a link or type a `@username` — no setup needed.

**Bot:** [@sociodabot](https://t.me/sociodabot)

## ✨ Features

- 🔴 **YouTube** — Videos, Shorts, audio extraction, quality selection
- 📸 **Instagram** — Posts, Reels, Stories (including bulk `@username` story download)
- 🎵 **TikTok** — Videos (no-watermark), audio extraction
- 📦 **Bulk Stories** — Type `@username` to download all stories at once
- 🎯 **Quality Selection** — Choose video/audio quality via inline buttons
- ⭐ **Telegram Stars** — Buy extra downloads when daily limit is reached
- 🔒 **Server-side cookies** — Instagram login handled automatically
- 👮 **Admin Panel** — Stats, ban/unban users, broadcast messages
- 📊 **Usage Limits** — 20 downloads/day per user (configurable)

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- **ffmpeg / ffprobe** — required for merging video+audio and splitting large files
- **A JavaScript runtime (Deno recommended)** — required by yt-dlp to solve TikTok / YouTube JS challenges. Without it, TikTok downloads fail with `Unable to extract universal data for rehydration`.

#### Installing Deno

```bash
# Windows (PowerShell)
irm https://deno.land/install.ps1 | iex

# macOS / Linux
curl -fsSL https://deno.land/install.sh | sh
```

After install, restart your terminal and verify:

```bash
deno --version
```

Make sure `deno` is on your `PATH` in the same environment from which you run the bot — yt-dlp invokes it automatically.

> Note: `yt-dlp[default,curl-cffi]` and `yt-dlp-ejs` are installed via `requirements.txt` (see below). `curl-cffi` provides browser impersonation and `yt-dlp-ejs` provides the JS components that run on Deno — both are needed for current TikTok extraction.

### Installation

```bash
# Clone the repo
git clone https://github.com/aldimhr/smdownbot.git
cd smdownot

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your BOT_TOKEN
```

### Configuration

Create a `.env` file:

```env
BOT_TOKEN=your_bot_token_here
ADMIN_ID=your_telegram_user_id
DAILY_LIMIT=20
```

### Run

```bash
python bot.py
```

### Run as systemd service

```bash
sudo cp smdownbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now smdownbot
```

## 📁 Project Structure

```
smdownbot/
├── bot.py                 # Entry point — dispatcher & router setup
├── config.py              # Settings (env vars, limits, paths)
├── handlers/
│   ├── start.py           # /start, /help, /stats, /buy commands
│   ├── download.py        # Link handling, quality selection, bulk stories
│   └── admin.py           # /admin, /ban, /unban commands
├── services/
│   ├── downloader.py      # yt-dlp wrapper (get_info, download)
│   ├── platform.py        # URL detection (YouTube, Instagram, TikTok)
│   ├── limiter.py         # Per-user daily download limits
│   ├── bulk_stories.py    # Bulk story download logic
│   └── url_store.py       # Callback data hash mapping (Telegram 64-byte limit)
├── keyboards/
│   └── inline.py          # Inline keyboard builders (quality, format)
├── database/
│   ├── db.py              # aiosqlite connection & init
│   └── models.py          # User & usage tables
├── cookies/
│   └── instagram.txt      # Server-side Instagram cookies (Playwright)
├── tests/
│   └── test_downloader.py # Unit tests
├── requirements.txt
└── .env.example
```

## 🔧 Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Usage guide |
| `/stats` | Your download statistics |
| `/buy` | Buy extra downloads with Telegram Stars |
| `/admin` | Admin panel (admin only) |
| `/ban @user` | Ban a user (admin only) |
| `/unban @user` | Unban a user (admin only) |

## 💡 Usage

1. Open [@sociodabot](https://t.me/sociodabot)
2. Paste a link from YouTube, Instagram, or TikTok
3. Choose quality/format if prompted
4. Wait for download — file sent directly in chat

### Bulk Story Download

Just type an Instagram `@username` to download all their active stories:

```
@dr_tompi
```

## 🛠 Tech Stack

- **[aiogram 3](https://docs.aiogram.dev/)** — Async Telegram Bot framework
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — Media extraction engine
- **[aiosqlite](https://github.com/omnilib/aiosqlite)** — Async SQLite database
- **[Playwright](https://playwright.dev/)** — Instagram cookie login

## 📝 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BOT_TOKEN` | — | Telegram bot token (required) |
| `ADMIN_ID` | `519613720` | Admin Telegram user ID |
| `DB_PATH` | `data/smdown.db` | SQLite database path |
| `DOWNLOAD_DIR` | `downloads` | Temporary download folder |
| `DAILY_LIMIT` | `20` | Max downloads per user per day |

## 📄 License

MIT License — feel free to use and modify.

## 👨‍💻 Author

Built by [aldimhr](https://github.com/aldimhr)
