"""Tests for the voice messages of the watch."""

import base64
from collections.abc import AsyncIterable
from http import HTTPStatus
import math
import struct
from typing import Any
from unittest.mock import patch

import av
import pytest

from homeassistant.components import assist_pipeline
from homeassistant.components.zepp.voice import (
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    InvalidAudioError,
    decode_opus,
)
from homeassistant.core import HomeAssistant

from .conftest import Post

from tests.common import MockConfigEntry

PIPELINE = "homeassistant.components.zepp.voice.assist_pipeline.async_pipeline_from_audio_stream"


@pytest.fixture(scope="module")
def recording() -> bytes:
    """One second of a 440 Hz tone, packet by packet as the watch writes it."""
    encoder = av.CodecContext.create("libopus", "w")
    encoder.sample_rate = SAMPLE_RATE
    encoder.layout = "mono"
    encoder.format = "s16"
    encoder.open()
    samples = b"".join(
        struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / SAMPLE_RATE)))
        for i in range(SAMPLE_RATE)
    )
    size = encoder.frame_size * SAMPLE_WIDTH
    packets = []
    for start in range(0, len(samples), size):
        frame = av.AudioFrame(format="s16", layout="mono", samples=encoder.frame_size)
        frame.planes[0].update(samples[start : start + size].ljust(size, b"\0"))
        frame.sample_rate = SAMPLE_RATE
        frame.pts = start // SAMPLE_WIDTH
        packets.extend(bytes(packet) for packet in encoder.encode(frame))
    packets.extend(bytes(packet) for packet in encoder.encode(None))
    return b"".join(struct.pack(">II", len(packet), 0) + packet for packet in packets)


def test_decode_opus(recording: bytes) -> None:
    """The recording comes back as about one second of 16 kHz mono 16-bit PCM."""
    pcm = decode_opus(recording)

    assert SAMPLE_RATE * 0.95 <= len(pcm) / SAMPLE_WIDTH <= SAMPLE_RATE * 1.1
    peak = max(abs(sample) for (sample,) in struct.iter_unpack("<h", pcm))
    assert peak > 4000


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"\0\0\0\x10\0\0", id="truncated_header"),
        pytest.param(b"\0\0\0\x10\0\0\0\0abc", id="truncated_packet"),
    ],
)
def test_decode_invalid(data: bytes) -> None:
    """Anything but whole packets is refused."""
    with pytest.raises(InvalidAudioError):
        decode_opus(data)


async def test_voice(
    post: Post, mock_config_entry: MockConfigEntry, recording: bytes
) -> None:
    """What was heard and answered goes back to the watch, with the conversation."""
    received: dict[str, Any] = {}

    async def pipeline(
        hass: HomeAssistant,
        *,
        event_callback: assist_pipeline.PipelineEventCallback,
        stt_stream: AsyncIterable[bytes],
        **kwargs: Any,
    ) -> None:
        received.update(kwargs, pcm=b"".join([chunk async for chunk in stt_stream]))
        event_callback(
            assist_pipeline.PipelineEvent(
                assist_pipeline.PipelineEventType.STT_END,
                {"stt_output": {"text": "allume le salon"}},
            )
        )
        event_callback(
            assist_pipeline.PipelineEvent(
                assist_pipeline.PipelineEventType.INTENT_END,
                {
                    "intent_output": {
                        "response": {"speech": {"plain": {"speech": "C'est fait"}}},
                        "conversation_id": "01JZEPP",
                        "continue_conversation": False,
                    }
                },
            )
        )

    with patch(PIPELINE, pipeline):
        response = await post(
            {"type": "voice", "audio": base64.b64encode(recording).decode()}
        )

    assert response.status == HTTPStatus.OK
    assert await response.json() == {
        "heard": "allume le salon",
        "answer": "C'est fait",
        "conversation_id": "01JZEPP",
        "continue": False,
        "error": None,
    }
    assert received["pcm"] == decode_opus(recording)
    assert received["device_id"] == mock_config_entry.runtime_data
    assert received["pipeline_id"] is None
    assert received["end_stage"] is assist_pipeline.PipelineStage.INTENT
    assert received["audio_settings"].is_vad_enabled is False


async def test_voice_not_understood(post: Post, recording: bytes) -> None:
    """A pipeline error reaches the watch as its code."""

    async def pipeline(
        hass: HomeAssistant,
        *,
        event_callback: assist_pipeline.PipelineEventCallback,
        **kwargs: Any,
    ) -> None:
        event_callback(
            assist_pipeline.PipelineEvent(
                assist_pipeline.PipelineEventType.ERROR,
                {"code": "stt-no-text-recognized", "message": "No text recognized"},
            )
        )

    with patch(PIPELINE, pipeline):
        response = await post(
            {
                "type": "voice",
                "audio": base64.b64encode(recording).decode(),
                "conversation_id": "01JZEPP",
            }
        )

    assert await response.json() == {
        "heard": None,
        "answer": None,
        "conversation_id": "01JZEPP",
        "continue": False,
        "error": "stt-no-text-recognized",
    }


async def test_voice_pipeline_not_found(post: Post, recording: bytes) -> None:
    """A pipeline removed since it was chosen is reported, not raised."""
    with patch(
        PIPELINE,
        side_effect=assist_pipeline.PipelineNotFound("pipeline_not_found", "Gone"),
    ):
        response = await post(
            {"type": "voice", "audio": base64.b64encode(recording).decode()}
        )

    assert (await response.json())["error"] == "pipeline_not_found"


@pytest.mark.parametrize(
    ("audio", "status"),
    [
        pytest.param("pas du base64 !", HTTPStatus.BAD_REQUEST, id="not_base64"),
        pytest.param(
            base64.b64encode(b"\0\0\0\x10").decode(),
            HTTPStatus.UNPROCESSABLE_ENTITY,
            id="not_opus",
        ),
    ],
)
async def test_voice_invalid_audio(post: Post, audio: str, status: HTTPStatus) -> None:
    """Audio that cannot be decoded never reaches the pipeline."""
    with patch(PIPELINE) as pipeline:
        response = await post({"type": "voice", "audio": audio})

    assert response.status == status
    assert (await response.json())["error"] == "invalid_audio"
    pipeline.assert_not_called()
