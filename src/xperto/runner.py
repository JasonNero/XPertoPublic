#
# Copyright (c) 2025, Jason Schuehlein
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio

import aiohttp
import click
from pipecat.audio.vad.silero import SileroVADAnalyzer

from .bots.bot import SimpleBot
from .config import APIKeysConfig, AppConfig
from .utils.context_manager import ConversationContextManager


def load_config_with_overrides(config_file: str, **cli_overrides) -> AppConfig:
    """Load config from YAML and apply CLI overrides."""
    config = AppConfig.load_from_yaml(config_file)

    # Apply CLI overrides to bot config
    bot_config = config.bot.model_dump()
    for key, value in cli_overrides.items():
        if value is not None and hasattr(config.bot, key):
            bot_config[key] = value

    # Reconstruct config with overrides
    config.bot = config.bot.__class__(**bot_config)
    return config


@click.command()
@click.option(
    "--config",
    default="default",
    help='Config name ("default", "experto-en", ...) or file path',
)
@click.option(
    "--transport",
    "-t",
    type=click.Choice(["local", "daily"]),
    default="local",
    help="Transport type",
)
@click.option("--language", help="Override language (EN/DE)")
@click.option("--assistant-name", help="Override assistant name")
@click.option("--voice-id", help="Override voice ID")
@click.option("--resume", help="Resume conversation from session ID")
@click.option("--list-contexts", is_flag=True, help="List saved conversation contexts")
@click.option("--verbose", "-v", count=True, help="Increase verbosity")
def main(
    config,
    transport,
    language,
    assistant_name,
    voice_id,
    resume,
    list_contexts,
    verbose,
):
    """Pipecat Bot Runner with configuration support."""

    # Handle list-contexts command
    if list_contexts:
        app_config = AppConfig.load_from_yaml(config)
        context_manager = ConversationContextManager(app_config.paths.contexts)
        contexts = context_manager.list_saved_contexts()

        if not contexts:
            click.echo("No saved conversation contexts found.")
            return

        click.echo("Available conversation contexts:")
        click.echo("-" * 60)
        for ctx in contexts:
            click.echo(f"Session ID: {ctx.session_id}")
            click.echo(f"  Timestamp: {ctx.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            click.echo(f"  Messages: {ctx.message_count}")
            click.echo(f"  Config: {ctx.config_used}")
            click.echo(f"  Participants: {ctx.participant_count}")
            click.echo()
        return

    # Load configuration with CLI overrides
    cli_overrides = {
        "language": language,
        "assistant_name": assistant_name,
        "voice_id": voice_id,
    }
    app_config = load_config_with_overrides(config, **cli_overrides)

    # Load API keys from environment
    api_keys = APIKeysConfig()

    # Create bot instance with optional resume
    bot = SimpleBot(app_config, api_keys, resume_session_id=resume)

    # Using match-case for transport selection and lazy imports
    match transport:
        case "local":
            from pipecat.transports.local.audio import (
                LocalAudioTransport,
                LocalAudioTransportParams,
            )

            params = LocalAudioTransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
            )

            async def run():
                transport = LocalAudioTransport(params=params)
                await bot.run(transport)

            asyncio.run(run())

        case "daily":
            from pipecat.transports.daily.transport import DailyParams, DailyTransport
            from pipecat.transports.daily.utils import DailyRESTHelper

            params = DailyParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
            )

            async def run():
                async with aiohttp.ClientSession() as session:
                    daily_rest_helper = DailyRESTHelper(
                        daily_api_key=api_keys.daily_api_key,
                        daily_api_url="https://api.daily.co/v1",
                        aiohttp_session=session,
                    )
                    token = await daily_rest_helper.get_token(
                        api_keys.daily_sample_room_url, 60 * 60
                    )
                    transport = DailyTransport(
                        api_keys.daily_sample_room_url, token, "Pipecat", params=params
                    )

                    await bot.run(transport)

            asyncio.run(run())


if __name__ == "__main__":
    main()
