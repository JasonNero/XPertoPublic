import yaml
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings


class BotConfig(BaseSettings):
    language: str = "EN"
    assistant_names: List[str] = ["Experto", "Experte", "Expertin", "Expert"]
    idle_timeout_secs: int = 1800
    keepalive_timeout_secs: float = 30
    audio_recording: bool = False
    tui: bool = False


class PromptsConfig(BaseSettings):
    persona: Path = Path("src/xperto/prompts/Experto_EN.md")
    intro: Path = Path("src/xperto/prompts/intro_EN.md")


class PathsConfig(BaseSettings):
    recordings: Path = Path("./recordings")
    transcripts: Path = Path("./transcripts")
    contexts: Path = Path("~/.xperto/contexts")


class STTConfig(BaseSettings):
    provider: str = "deepgram"
    model: str = "nova-2-general"


class LLMConfig(BaseSettings):
    provider: str = "openai"
    model: str = "gpt-4.1"
    tools: List[str] = []


class TTSConfig(BaseSettings):
    provider: str = "deepgram"
    model: str = "aura-helios-en"
    voice: str = "aura-helios-en"


class ServicesConfig(BaseSettings):
    stt: STTConfig = STTConfig()
    llm: LLMConfig = LLMConfig()
    tts: TTSConfig = TTSConfig()


class APIKeysConfig(BaseSettings):
    openai_api_key: str
    deepgram_api_key: Optional[str] = None
    speechmatics_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None
    daily_api_key: Optional[str] = None
    daily_sample_room_url: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


class AppConfig(BaseSettings):
    config_name: str = "default"
    bot: BotConfig = BotConfig()
    prompts: PromptsConfig = PromptsConfig()
    paths: PathsConfig = PathsConfig()
    services: ServicesConfig = ServicesConfig()

    @classmethod
    def load_from_yaml(cls, config_path: str = "default") -> "AppConfig":
        """Load configuration from YAML file or bundled config name."""
        resolved_path = cls._resolve_config_path(config_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"Config file not found: {resolved_path}")

        with open(resolved_path, "r") as f:
            data = yaml.safe_load(f)

        # Handle Path expansion for ~ and relative paths
        paths_data = data.get("paths", {})
        if "recordings" in paths_data:
            paths_data["recordings"] = Path(paths_data["recordings"]).expanduser()
        if "transcripts" in paths_data:
            paths_data["transcripts"] = Path(paths_data["transcripts"]).expanduser()
        if "contexts" in paths_data:
            paths_data["contexts"] = Path(paths_data["contexts"]).expanduser()

        prompts_data = data.get("prompts", {})
        if "prompts_dir" in prompts_data:
            prompts_data["prompts_dir"] = Path(prompts_data["prompts_dir"]).expanduser()

        return cls(
            config_name=resolved_path.stem,
            bot=BotConfig(**data.get("bot", {})),
            prompts=PromptsConfig(**prompts_data),
            paths=PathsConfig(**paths_data),
            services=ServicesConfig(
                stt=STTConfig(**data.get("services", {}).get("stt", {})),
                llm=LLMConfig(**data.get("services", {}).get("llm", {})),
                tts=TTSConfig(**data.get("services", {}).get("tts", {})),
            ),
        )

    @staticmethod
    def _resolve_config_path(config_path: str) -> Path:
        """Resolve config path - handle bundled configs and custom paths."""
        path = Path(config_path)

        # If it's an absolute path or contains path separators, use as-is
        if path.is_absolute() or "/" in config_path or "\\" in config_path:
            return path

        # If it ends with .yaml, treat as relative path
        if config_path.endswith(".yaml"):
            return path

        # Otherwise, treat as bundled config name
        bundle_path = Path(__file__).parent / "configs" / f"{config_path}.yaml"
        return bundle_path

    def load_persona_prompt(self) -> str:
        """Load and render persona prompt with template variables."""
        with open(self.prompts.persona, "r") as f:
            persona = f.read()

        return persona

    def load_intro_prompt(self) -> str:
        """Load and render intro prompt with template variables."""
        with open(self.prompts.intro, "r") as f:
            intro = f.read()

        return intro
