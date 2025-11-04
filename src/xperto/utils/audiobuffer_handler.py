import datetime
import io
import wave
from pathlib import Path

import aiofiles
from loguru import logger


class AudioBufferHandler:
    """Handles audio data processing and saving.

    This class provides methods to save audio data to WAV files, either as a single
    combined audio file or as separate tracks for user and bot audio.
    """

    def __init__(
        self, output_folder: Path = Path("./recordings"), output_name: str = "recording"
    ):
        """Initialize the handler with an output folder.

        Args:
            output_folder: Path to the folder where audio files will be saved.
        """
        self.output_folder = output_folder
        self.output_folder.mkdir(parents=True, exist_ok=True)
        self.output_name = output_name
        logger.debug(
            f"AudioBufferHandler initialized with output folder: {self.output_folder}"
        )

    async def save_audio_file(
        self, audio: bytes, filename: Path, sample_rate: int, num_channels: int
    ):
        """Save audio data to a WAV file."""
        if len(audio) > 0:
            with io.BytesIO() as buffer:
                with wave.open(buffer, "wb") as wf:
                    wf.setsampwidth(2)
                    wf.setnchannels(num_channels)
                    wf.setframerate(sample_rate)
                    wf.writeframes(audio)
                async with aiofiles.open(filename, "wb") as file:
                    await file.write(buffer.getvalue())
            logger.info(f"Audio saved to {filename}")

    # Handler for combined audio data
    async def on_audio_data(self, buffer, audio, sample_rate, num_channels):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.output_folder / f"{timestamp}_{self.output_name}.wav"
        await self.save_audio_file(audio, filename, sample_rate, num_channels)

    # Handler for separate tracks
    async def on_track_audio_data(
        self, buffer, user_audio, bot_audio, sample_rate, num_channels
    ):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save user audio
        user_filename = self.output_folder / f"{timestamp}_{self.output_name}_user.wav"
        await self.save_audio_file(user_audio, user_filename, sample_rate, 1)

        # Save bot audio
        bot_filename = self.output_folder / f"{timestamp}_{self.output_name}_bot.wav"
        await self.save_audio_file(bot_audio, bot_filename, sample_rate, 1)
