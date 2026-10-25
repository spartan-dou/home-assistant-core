"""Voice messages: the watch records Opus, the Assist pipeline answers in text."""

from collections.abc import AsyncIterator
import struct
from typing import Any

import av

from homeassistant.components import assist_pipeline, stt
from homeassistant.core import Context, HomeAssistant

from .const import CONF_PIPELINE, ZeppConfigEntry

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
# Each packet follows its length and its final range, big-endian, as opus_demo writes
# them: Zepp OS records no container a decoder could open on its own.
PACKET_HEADER = struct.Struct(">II")


class InvalidAudioError(Exception):
    """The recording is not the Opus the watch writes."""


def decode_opus(data: bytes) -> bytes:
    """Decode a watch recording to the 16 kHz mono 16-bit PCM that Assist expects."""
    packets = _split_packets(data)
    decoder = av.CodecContext.create("opus", "r")
    decoder.sample_rate = SAMPLE_RATE
    decoder.layout = "mono"
    # The decoder outputs 48 kHz float, whatever rate it is given.
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    pcm = bytearray()
    try:
        for packet in packets:
            for frame in decoder.decode(av.Packet(packet)):
                pcm += _pcm(resampler.resample(frame))
    except av.FFmpegError as err:
        raise InvalidAudioError(str(err)) from err
    pcm += _pcm(resampler.resample(None))
    if not pcm:
        raise InvalidAudioError("No audio")
    return bytes(pcm)


def _split_packets(data: bytes) -> list[bytes]:
    packets = []
    position = 0
    while position < len(data):
        if position + PACKET_HEADER.size > len(data):
            raise InvalidAudioError("Truncated packet header")
        length, _ = PACKET_HEADER.unpack_from(data, position)
        position += PACKET_HEADER.size
        if position + length > len(data):
            raise InvalidAudioError("Truncated packet")
        if length:
            packets.append(data[position : position + length])
        position += length
    return packets


def _pcm(frames: list[av.AudioFrame]) -> bytes:
    # A plane can be padded past the samples it holds.
    return b"".join(
        bytes(frame.planes[0])[: frame.samples * SAMPLE_WIDTH] for frame in frames
    )


async def async_ask(
    hass: HomeAssistant, entry: ZeppConfigEntry, pcm: bytes, conversation_id: str | None
) -> dict[str, Any]:
    """Run a recording through the pipeline, up to the answer of the agent."""
    result: dict[str, Any] = {
        "heard": None,
        "answer": None,
        "conversation_id": conversation_id,
        "continue": False,
        "error": None,
    }

    def on_event(event: assist_pipeline.PipelineEvent) -> None:
        data = event.data or {}
        if event.type is assist_pipeline.PipelineEventType.STT_END:
            result["heard"] = data["stt_output"]["text"]
        elif event.type is assist_pipeline.PipelineEventType.INTENT_END:
            output = data["intent_output"]
            speech = output["response"]["speech"]
            result["answer"] = speech.get("plain", {}).get("speech")
            result["conversation_id"] = output["conversation_id"]
            result["continue"] = output["continue_conversation"]
        elif event.type is assist_pipeline.PipelineEventType.ERROR:
            result["error"] = data["code"]

    async def audio() -> AsyncIterator[bytes]:
        yield pcm

    try:
        await assist_pipeline.async_pipeline_from_audio_stream(
            hass,
            context=Context(),
            event_callback=on_event,
            stt_metadata=stt.SpeechMetadata(
                language="",
                format=stt.AudioFormats.WAV,
                codec=stt.AudioCodecs.PCM,
                bit_rate=stt.AudioBitRates.BITRATE_16,
                sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
                channel=stt.AudioChannels.CHANNEL_MONO,
            ),
            stt_stream=audio(),
            pipeline_id=entry.options.get(CONF_PIPELINE),
            conversation_id=conversation_id,
            device_id=entry.runtime_data,
            end_stage=assist_pipeline.PipelineStage.INTENT,
            # The message arrives whole: voice detection could only cut it on a pause.
            audio_settings=assist_pipeline.AudioSettings(is_vad_enabled=False),
        )
    except assist_pipeline.PipelineNotFound:
        result["error"] = "pipeline_not_found"
    return result
