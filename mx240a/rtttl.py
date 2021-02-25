from typing import Dict, Final, Optional
import re

from mx240a.logging import logger
from mx240a.util import hexdump


class Ringtone:
    tone_bytes: bytes
    name: str
    tone_data: str

    NOTE_TO_HEX: Final[Dict[str, int]] = {
        "c4": 0x01,
        "c4#": 0x02,
        "d4": 0x03,
        "d4#": 0x04,
        "e4": 0x05,
        "f4": 0x06,
        "f4#": 0x07,
        "g4": 0x08,
        "g4#": 0x09,
        "a4": 0x0a,
        "a4#": 0x0b,
        "b4": 0x0c,
        "c5": 0x0d,
        "c5#": 0x0e,
        "d5": 0x0f,
        "d5#": 0x10,
        "e5": 0x11,
        "f5": 0x12,
        "f5#": 0x13,
        "g5": 0x14,
        "g5#": 0x15,
        "a5": 0x16,
        "a5#": 0x17,
        # 0x18 - 0x1f missing
        "b5": 0x20,
        "c6": 0x21,
        "c6#": 0x22,
        "d6": 0x23,
        "d6#": 0x24,
        "e6": 0x25,
        "f6": 0x26,
        "f6#": 0x27,
        "g6": 0x28,
        "g6#": 0x29,
        "a6": 0x2a,
        "a6#": 0x2b,
        "b6": 0x2c,
        "c7": 0x2d,
        "c7#": 0x2e,
        "d7": 0x2f,
        "d7#": 0x30,
        "e7": 0x31,
        "f7": 0x32,
        "f7#": 0x33,
        "g7": 0x34,
        "g7#": 0x35,
        "a7": 0x36,
        "a7#": 0x37,
        "b7": 0x38,
    }

    def __init__(self, tone_data: Optional[str]) -> None:
        self.tone_data = tone_data

        if not tone_data:
            # null tone data = mute
            self.tone_bytes = bytes([0x01, 0x7f])
            return

        logger.trace(f"RTTTL Input \"{tone_data}\"")
        duration = 4
        octave = 4
        bpm = 120

        tone_data = tone_data.replace(" ", "")
        if not (match := re.match(R"(.*):(([dob]=\d+,?)*):(.*)", tone_data)):
            raise ValueError("Invalid RTTTL Data")

        name = match.group(1)
        args = match.group(2)
        notes = match.group(4)

        for arg in args.split(","):
            parts = arg.split("=")
            if parts[0] == "d":
                new_duration = int(parts[1])
                if new_duration not in [1, 2, 4, 8, 16, 32]:
                    raise ValueError("Invalid RTTTL Data (Invalid duration)")
                duration = new_duration
            elif parts[0] == "o":
                new_octave = int(parts[1])
                if new_octave not in [4, 5, 6, 7]:
                    raise ValueError("Invalid RTTTL Data (Invalid octave)")
                octave = new_octave
            elif parts[0] == "b":
                bpm = int(parts[1])

        logger.trace(f"RTTTL: \"{name}\" (Note Duration: {duration}, Octave: {octave}, BPM: {bpm}) Notes: {notes}")
        self.name = name

        output_bytes = bytearray()
        for match in re.findall(R"(\d?)([a-gA-GpP])(#?)(\d?)(\.?),?", notes):
            note_duration = int(match[0]) if match[0] else duration
            note_ms = int(60000 / bpm * 4 / note_duration / 16)
            if note_ms < 1:
                note_ms = 1
            if note_ms > 255:
                note_ms = 255
            output_bytes.append(note_ms)

            note = match[1].lower()
            sharp = match[2] if match[2] else ""
            note_octave = match[3] if match[3] else octave
            full_note = f"{note}{note_octave}{sharp}"
            if full_note not in Ringtone.NOTE_TO_HEX and note != "p":
                raise ValueError("Invalid RTTTL Data (Invalid note)")
            elif note == "p":
                logger.warning("RTTTL WARNING: Pauses do not work correctly on the handset")
            output_bytes.append(0x7f if note == "p" else Ringtone.NOTE_TO_HEX[full_note])

        self.tone_bytes = bytes(output_bytes)
        logger.trace(f"RTTTL Output {hexdump(self.tone_bytes)}")

    def __repr__(self) -> str:
        return f"<Ringtone \"{self.tone_data}\">"
