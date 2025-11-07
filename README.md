# XPerto

Your AI meeting assistant!

Based on [Pipecat](https://www.github.com/pipecat-ai/pipecat), powered by Daily.co, Speechmatics, GPT-4.1 and ElevenLabs.

## Quick Start

> [!NOTE]
> This project was developed on WSL2/Linux and we recommend to also install it that way. 
> It also works on Windows but you won't be able to use Daily.co (for now), instead you'll have to run it locally. Also you might experience some hiccups (e.g. slow UI, audio bugs, longer startup and shutdown times).

**Pre-requisites**: 
- having [`git`](https://git-scm.com/downloads) and [`uv`](https://docs.astral.sh/uv/getting-started/installation/) installed
- having [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) installed (recommended) or running on Windows/Linux/MacOS directly

### WSL2 Setup

1. **Windows**: install Pulse Audio using the "Full Installer" from this URL: https://pgaskin.net/pulseaudio-win32/
    - Make sure to allow the app through the firewall when prompted during installation!
2. **WSL**: run `sudo apt install build-essential libasound2-plugins portaudio19-dev libportaudio2 pulseaudio-utils` to install the required libraries
3. **WSL**: configure the pulse audio server by appending the following lines to your `~/.bashrc` file e.g. by running `code ~/.bashrc`:
    ```bash
    export HOST_IP="$(ip route |awk '/^default/{print $3}')"
    export PULSE_SERVER="tcp:$HOST_IP"
    ```
4. **WSL**: Restart your WSL terminal or run `source ~/.bashrc`
5. **WSL**: Test the audio setup by running `pactl list sources short`, you should see at least two audio devices listed. 
    - If no audio devices are found, restart the Pulse Audio service on Windows (or reboot your PC) and try again.
    - If only "RDP" devices are shown, make sure that your changes to the `~/.bashrc` file have been saved and restart your terminal.
    - If the connection has been refused, make sure that the firewall rule for "Pulse Audio (TCP-In)" is enabled in Windows Defender Firewall settings and you are connected to a private network (or have enabled the rule for public networks as well).

It might be necessary to allow microphone access to the terminal app in Windows Settings:
- Open **Settings** > **Privacy & security** > **Microphone**
- Make sure **Microphone access** is turned **On** and the terminal app you are using (e.g. Windows Terminal, Ubuntu) has access as well.

Further troubleshooting tips (and the source for the steps above) can be found here: 
[Microsoft/WSL Discussion Question: Is it possible to run pyaudio on Ubuntu 22.04 under WSL2 with Windows 11? #9624](https://github.com/microsoft/WSL/discussions/9624#discussioncomment-12587731)

### XPerto Installation

1. Clone this repository via `git clone https://github.com/JasonNero/XPertoPublic`
2. Setup your environment variables by copying `.env.example` to `.env` and filling in your API keys (see below)
3. Install dependencies with `uv sync`

> [!NOTE]
> To run the bot locally (without Daily.co): `uv run bot`
>
> To run the bot in a Daily.co meeting room: `uv run bot --transport daily`

To specify a custom bot configuration you can append `--config <path>`. 
Currently there are example configurations in the `src/xperto/configs` folder:
- `default.yaml` - Main German bot with Speechmatics and ElevenLabs
- `experto-en.yaml` - English version with Speechmatics and Deepgram TTS
- `connectival.yaml` - HdM Connectival demo configuration

## XPerto Configuration

### Environment Variables

XPerto requires API keys for various services. 
To get them, please register on their respective websites and follow their docs.
Then copy `.env.example` to `.env` and fill in your keys:

```bash
# Transport (only needed for Daily.co deployments)
DAILY_SAMPLE_ROOM_URL=https://your-room.daily.co/room-name
DAILY_API_KEY=your-daily-api-key

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
    provider: "speechmatics"  # Options: "speechmatics"
    model: ""  # leave empty for Speechmatics

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
# by name
uv run bot --config my-bot
# or with full path:
uv run bot --config src/xperto/configs/my-bot.yaml
```
