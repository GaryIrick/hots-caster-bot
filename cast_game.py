import os
import time
from io import BytesIO
import base64
import json
from datetime import datetime

from openai import OpenAI
from PIL import ImageGrab
from pydantic import BaseModel
import screeninfo
import pygame

from settings import AppSettings

settings = AppSettings()

SCREENSHOT_PROMPT = f"""
I will give you a screenshot of a Heroes of the Storm game in progress.  Please describe the action that is taking place.

The map is: {settings.map}.

The heroes on the blue team are: {settings.blue_team}.
The heroes on the red team are: {settings.red_team}.
"""

ANNOUNCER_PROMPT = """
Please describe the action as if you were a professional play-by-play announcer, like Al Michaels or John Madden.  It should be 30 words or less.

Then, give me some commentary as if you were a color commentator that used to play the game professionally.  It should be 30 words or less.

Return it as JSON, like this:

{
"announcer": "This is a description of the action.",
"color": "This game sure is exciting!"
}
"""

monitor = screeninfo.get_monitors()[settings.monitor_index]
bounding_box = (
    monitor.x,
    monitor.y,
    monitor.x + monitor.width,
    monitor.y + monitor.height,
)
pygame.mixer.init(devicename=settings.audio_device)
client = OpenAI(api_key=settings.openai_api_key)
start = datetime.now()


class Message(BaseModel):
    role: str
    content: str

    def __repr__(self):
        return f"{self.role}: {self.content}"


def show_time(message: str):
    delta = datetime.now() - start
    print(f"{message}: {delta.total_seconds()}")


def get_completion(
    model: str,
    history: list[Message],
    new_messages: list[Message],
    frame_b64: str = None,
) -> Message:
    messages = [{"role": m.role, "content": m.content} for m in history] + [
        {"role": m.role, "content": m.content} for m in new_messages
    ]

    if frame_b64:
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{frame_b64}",
                            "detail": settings.image_detail,
                        },
                    }
                ],
            }
        )

    completion = client.chat.completions.create(
        model=model, messages=messages, max_tokens=400
    )

    llm_response = completion.choices[0].message

    return Message(role=llm_response.role, content=llm_response.content)


def get_frame_info(
    history: list[Message],
    frame_b64: bytes,
) -> Message:
    screenshot_response = get_completion(
        model=settings.screenshot_model,
        history=[],
        new_messages=[Message(role="user", content=SCREENSHOT_PROMPT)],
        frame_b64=frame_b64,
    )
    show_time("screenshot")
    print(f"Analysis: {screenshot_response.content}")

    announcer_response = get_completion(
        model=settings.announcer_model,
        history=history,
        new_messages=[
            Message(role="user", content=SCREENSHOT_PROMPT),
            Message(role="assistant", content=screenshot_response.content),
            Message(role="user", content=ANNOUNCER_PROMPT),
        ],
    )

    show_time("announcers")

    return announcer_response


def play_speech(voice: str, text: str):
    response = client.audio.speech.create(
        model=settings.tts_model, voice=voice, input=text, response_format="mp3"
    )
    pygame.mixer.music.load(BytesIO(response.content))
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        time.sleep(0.01)


message_history: list[Message] = []

start = datetime.now()

while True:
    screenshot = ImageGrab.grab(all_screens=True, bbox=bounding_box)
    screenshot = screenshot.resize(
        size=(
            settings.frame_width,
            int(settings.frame_width * screenshot.height / screenshot.width),
        )
    )
    with BytesIO() as image_data:
        screenshot.save(image_data, "png")
        frame_b64 = base64.b64encode(image_data.getvalue()).decode("utf-8")

    response_message = get_frame_info(message_history, frame_b64)

    # Clean up anything before and after the json, since the LLM likes to
    # put "helpful" text in front of it, or enclose it in markdown.
    json_text = response_message.content

    while len(json_text) > 0 and not json_text.startswith("{"):
        json_text = json_text[1:]

    while len(json_text) > 0 and not json_text.endswith("}"):
        json_text = json_text[:-1]

    try:
        response_json = json.loads(json_text)
    except Exception as e:
        print("Bad JSON returned.")
        continue

    announcer: str = response_json["announcer"]
    color: str = response_json["color"]
    message_history = message_history + [
        Message(
            role="assistant",
            content=f"Play-by-play announcer: {announcer}",
        ),
        Message(role="assistant", content=f"Color commentator: {color}"),
    ]
    message_history = message_history[-settings.history_retention :]
    print(f"Announcer: {announcer}")
    print(f"Color: {color}")
    play_speech(settings.announcer_voice, announcer)
    show_time("play by play")
    play_speech(settings.color_voice, color)
    show_time("color")
