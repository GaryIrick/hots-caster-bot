from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    monitor_index: int = 0
    frame_width: int = 1000
    openai_api_key: str
    screenshot_model: str
    image_detail: str = "auto"
    announcer_model: str
    tts_model: str
    audio_device: str
    history_retention: int = 10
    announcer_voice: str
    color_voice: str
    blue_team: str
    red_team: str
    map: str
