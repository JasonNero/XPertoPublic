# XPerto

Your AI meeting assistant!

Based on [Pipecat](https://www.github.com/pipecat-ai/pipecat), powered by Daily.co, Speechmatics, GPT-4.1 and ElevenLabs.

## Quick Start

> [!NOTE]
> This project was developed on WSL/Linux and we recommend to also install it that way. 
> However, it also works on Windows but you might experience some hiccups (e.g. slow UI, audio bugs, freezing instead of exiting the bot).

Pre-requisites: having [`git`](https://git-scm.com/downloads) and [`uv`](https://docs.astral.sh/uv/getting-started/installation/) installed.

1. Clone this repository via `git clone https://github.com/JasonNero/xperto`
2. Setup your environment variables in a `.env` file (see below)
3. Install dependencies with `uv sync`
4. Run the app with `uv run bot` (on Windows: `uv run -m src.xperto.runner`)

To specify a custom bot configuration use `--config <path>`. 
Currently there are example configurations in the `src/xperto/configs` folder:
- `default.yaml` - Main German bot with Speechmatics and ElevenLabs
- `experto-en.yaml` - English version with Speechmatics and Deepgram TTS
- `connectival.yaml` - Connectival demo configuration

For use with Daily.co online meeting rooms, sync via `uv sync --extra daily` and run with the `--transport daily` flag.

> [!NOTE]
> If you want to switch from Speechmatics SST to Deepgram STT, you'll need to use [my fork of pipecat](https://github.com/JasonNero/pipecat/tree/feat/userid-in-llm-context-rebased2) instead of the main repo, as it contains some fixups to propagate user/diarization IDs to the LLM context.

## Configuration

### Environment Variables

XPerto requires API keys for various services. 
To get them please register on their respective websites and follow their docs.
Then copy `.env.example` to `.env` and fill in your keys:


```bash
# Transport (only needed for Daily.co deployments)
# DAILY_SAMPLE_ROOM_URL=https://your-room.daily.co/room-name
# DAILY_API_KEY=your-daily-api-key

# Speech-to-Text (choose one or both)
SPEECHMATICS_API_KEY=your-speechmatics-key

# Large Language Model
OPENAI_API_KEY=sk-your-openai-key

# Text-to-Speech (choose one or both)
ELEVENLABS_API_KEY=sk_your-elevenlabs-key
```

### Creating a New Bot Configuration

Bot configurations are stored in `src/xperto/configs/` as YAML files. To create a new bot:

1. **Create a new YAML file** (or copy an existing one) in `src/xperto/configs/`, e.g., `my-bot.yaml`

2. **Define the configuration** using the following structure:

```yaml
bot:
  language: "EN"  # Language code (e.g., "EN", "DE")

  # Names the bot should respond to (including common mis-transcriptions)
  assistant_names:
    - "MyBot"
    - "My Bot"

  # Timeout in seconds after which the bot stops (default: 1800)
  idle_timeout_secs: 1800

  # Timeout for transitioning from wake to sleep state (default: 30)
  keepalive_timeout_secs: 30

prompts:
  # Path to the persona/system prompt file
  persona: "src/xperto/prompts/my_bot_persona.md"

  # Path to the initial/intro prompt file
  intro: "src/xperto/prompts/my_bot_intro.md"

paths:
  # Directories for storing bot outputs (supports ~ for home directory)
  recordings: "~/.xperto/recordings"
  transcripts: "~/.xperto/transcripts"
  contexts: "~/.xperto/contexts"

services:
  # Speech-to-Text configuration
  stt:
    provider: "speechmatics"  # Options: "deepgram" or "speechmatics"
    model: ""  # For Deepgram; leave empty for Speechmatics

  # Large Language Model configuration
  llm:
    provider: "openai"  # Currently only "openai" is supported
    model: "gpt-4.1"  # Model name (e.g., "gpt-4.1", "gpt-4o")

  # Text-to-Speech configuration
  tts:
    provider: "deepgram"  # Options: "deepgram" or "elevenlabs"
    model: "aura-helios-en"  # Model/voice ID
    voice: "aura-helios-en"  # Voice ID (for Deepgram, same as model)
```

3. **Create prompt files** in `src/xperto/prompts/`:
   - Create a persona file (e.g., `my_bot_persona.md`) defining the bot's personality and behavior
   - Create an intro file (e.g., `my_bot_intro.md`) with the initial greeting/instructions

4. **Run your bot**:
```bash
uv run bot --config my-bot
# or with full path:
uv run bot --config src/xperto/configs/my-bot.yaml
```

## Troubleshooting

### Using local transport on WSL2

Local transport on WSL2 can be a bit finicky. Here are some notes on what "works on my machine" (TM):

- Install Pulse Audio from https://pgaskin.net/pulseaudio-win32/
- Occasionally requires restarting the Pulse service and/or the WSL2 instance
