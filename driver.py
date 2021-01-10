import queue
import re
import sys
from enum import Enum
from queue import Queue
from threading import Thread, Lock
import time
from typing import Union, List, Optional, Any, Callable, Dict

# noinspection PyPep8Naming
from hid import device as HIDDevice
from loguru import logger


def set_log_level(level: str) -> None:
    logger.remove()
    if level == "TRACE" or level == "DEBUG":
        logger.add(sys.stdout, level=level, format="[{elapsed}] [{level}] {message}",
                   backtrace=True, diagnose=True, enqueue=True)
    else:
        logger.add(sys.stdout, level=level, format="[{time:HH:mm:ss}] [{level}] {message}",
                   backtrace=True, diagnose=True, enqueue=True)


# default info level
set_log_level("INFO")


def as_bytes(data: Union[str, bytes]) -> bytes:
    if isinstance(data, bytes):
        return data
    return data.encode("ascii", "replace")


def to_hex(num: Union[int, bytes]) -> str:
    if isinstance(num, int):
        return "%.2x" % num
    else:
        out = ""
        for b in num:
            out += "%.2x" % b
        return out


def hexdump(data: Union[List[str], List[int], bytes], show_binary: bool = False) -> str:
    if isinstance(data, List) and len(data):
        if isinstance(data[0], str):
            data = bytes([ord(c) for c in data])
        if isinstance(data[0], int):
            data = bytes(data)

    ascii_data = []
    for byte in data:
        # if printable ascii
        if 32 <= byte <= 127:
            ascii_data.append(chr(byte))
        else:
            ascii_data.append(".")

    hex_data = [to_hex(b) for b in data]
    output = "(%s)" % " ".join(hex_data + [".."] * (8 - len(hex_data)))
    output += " (%s)" % "".join(ascii_data)

    if show_binary:
        binary_data = []
        for byte in data:
            bits = ""
            for i in range(7, -1, -1):
                bits += str((byte >> i) & 1)
            binary_data.append(bits)
        output += " {%s}" % " ".join(binary_data)

    return output


class Ringtone:
    tone_bytes: bytes
    name: str
    tone_data: str

    NOTE_TO_HEX: Dict[str, int] = {
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

    def __init__(self, tone_data: str) -> None:
        self.tone_data = tone_data

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

        logger.trace(f"RTTTL Output {hexdump(output_bytes)}")

        self.tone_bytes = bytes(output_bytes)

    def __repr__(self) -> str:
        return f"<Ringtone \"{self.tone_data}\">"


class Status(Enum):
    ACTIVE = 0
    IDLE = 1
    AWAY = 2


class Buddy:
    screen_name: str
    id: Optional[int]
    status: Status
    mobile: bool

    def __init__(self, screen_name: str) -> None:
        self.screen_name = screen_name
        self.id = None
        self.status = Status.ACTIVE
        self.mobile = False


class Window:
    handset: "Handset"
    window_id: int
    is_group: bool

    def __init__(self, handset: "Handset", window_id: int, is_group: bool) -> None:
        self.handset = handset
        self.window_id = window_id
        self.is_group = is_group

    def send_message(self, message: str, username: Optional[str] = None) -> None:
        # group messages have a username of ascii followed by a ':', messages to a buddy have null username
        if self.is_group:
            if not username:
                username = as_bytes(":")
                logger.warning("Group messages should have a username")
            else:
                username = as_bytes(username.replace(":", "") + ":")
        else:
            username = [0x00]

        msg_bytes = [*username, *as_bytes(message)]
        payload_len = 21 if not self.is_group else 22
        msg_parts = [msg_bytes[i:i + payload_len] for i in range(0, len(msg_bytes), payload_len)]
        if len(msg_parts[-1]) == payload_len:
            # and some more padding for the last 0xff, just in case
            msg_parts.append([])

        for i, part in enumerate(msg_parts):
            to_send = bytearray()
            to_send.append(int(f"8{self.handset.num}", 16))
            to_send.append(self.window_id)
            for byte in part:
                to_send.append(byte)
            if i == len(msg_parts) - 1:
                to_send.append(0xff)

            # max 24 bytes
            assert len(to_send) <= 24
            self.handset.base.write(bytes(to_send))
            self.handset.base.ack()
        self.handset.base.write(bytes([int(f"e{self.handset.num}", 16), 0xce, self.window_id]))
        self.handset.base.ack()


class Handset:
    base: "BaseStation"
    num: int
    id: str
    name: Optional[str]
    username: Optional[str]
    password: Optional[str]
    buddy_list: Dict[str, List[Optional[Buddy]]]
    windows: Dict[int, Window]
    next_group_id: int

    message_callback = Optional[Callable[[str], None]]
    window_open_callback = Optional[Callable[[Window], None]]
    window_close_callback = Optional[Callable[[Window], None]]

    def __init__(self, base: "BaseStation", handset_num: int, handset_id: str) -> None:
        self.base = base
        if 1 > handset_num > 7:
            raise ValueError(f"Invalid Handset Number: {handset_num}")
        self.num = handset_num
        self.id = handset_id

        self.name = None
        self.username = None
        self.password = None

        self.buddy_list = {}
        self.windows = {}
        self.next_group_id = 0x81

        self.message_callback = None
        self.window_open_callback = None
        self.window_close_callback = None

    def open_window(self, window_id: int) -> None:
        self.windows[window_id] = window = Window(self, window_id, False)
        if self.window_open_callback:
            self.window_open_callback(window)

    def close_window(self, window_id: int) -> None:
        if window_id in self.windows:
            window = self.windows[window_id]
            del self.windows[window_id]
            if self.window_close_callback:
                self.window_close_callback(window)

    def new_group(self) -> Window:
        self.windows[self.next_group_id] = window = Window(self, self.next_group_id, True)
        self.next_group_id += 1

        self.base.write(bytes([int(f"e{self.num}", 16), 0xc9, window.window_id, 0xff]))
        self.base.ack()

        return window

    def add_buddy(self, buddy: Buddy, group: str) -> int:
        group = group[0:6].ljust(6, " ")
        if group not in self.buddy_list.keys():
            self.buddy_list[group] = [None]
        buddy.id = len(self.buddy_list[group])
        self.buddy_list[group].append(buddy)
        status_str = (f"{'A' if buddy.status == Status.ACTIVE else 'I' if buddy.status == Status.IDLE else 'U'}" +
                      f"{'Y' if buddy.mobile else 'N'}" + "N")
        self.base.ack()
        self.base.write(bytes([
            int(f"e{self.num}", 16), 0xca, *as_bytes(status_str), buddy.id, 0xff
        ]))
        self.base.write(bytes([
            int(f"c{self.num}", 16), 0xc9, *as_bytes(group), *as_bytes(buddy.screen_name), 0xff
        ]))
        self.base.write(bytes([
            int(f"a{self.num}", 16), 0xc9, 0x01, 0xff
        ]))
        self.base.ack()
        return buddy.id


class PacketType(Enum):
    Unknown = 0x00
    Message = 0x01
    MessageContinuation = 0x02
    HandsetRegistration = 0x03
    MysteryACK = 0x04
    BaseInitACK = 0x05
    BaseInitReply = 0x06
    HandsetDisconnected = 0x07
    HandsetConnecting = 0x08
    HandsetUsername = 0x09
    HandsetPassword = 0x0a
    ACK = 0x0b
    OpenWindow = 0x0c
    CloseWindow = 0x0d
    HandsetAway = 0x0e
    HandsetWarning = 0x0f
    HandsetInvite = 0x10


class Packet:
    packet_type: PacketType
    _packet_data: bytearray

    def __init__(self, packet_type: PacketType) -> None:
        self.packet_type = packet_type
        self._packet_data = bytearray()

    @staticmethod
    def detect_type(byte_1: int, byte_2: int) -> PacketType:
        byte_1_hi = (byte_1 & 0xf0) >> 4

        if byte_1 == 0xe0:
            return PacketType.HandsetRegistration
        elif (byte_1 == 0xe1 or byte_1 == 0xe2) and byte_2 == 0xfd:
            return PacketType.MysteryACK
        elif byte_1 == 0xe8:
            return PacketType.BaseInitACK
        elif byte_1 == 0xef:
            return PacketType.BaseInitReply
        elif byte_1_hi == 0xf or byte_1_hi == 0xe:
            if byte_2 == 0xfd:
                return PacketType.ACK
            elif byte_2 == 0x8c:
                return PacketType.HandsetDisconnected
            elif byte_2 == 0x8e:
                return PacketType.HandsetConnecting
            elif byte_2 == 0x91:
                return PacketType.HandsetUsername
            elif byte_2 == 0x92:
                return PacketType.HandsetPassword
            elif byte_2 == 0x93:
                return PacketType.HandsetDisconnected  # Logoff menu selection
            elif byte_2 == 0x94:
                return PacketType.OpenWindow
            elif byte_2 == 0x95:
                return PacketType.CloseWindow
            elif byte_2 == 0x96:
                return PacketType.HandsetAway
            elif byte_2 == 0x9a:
                return PacketType.HandsetWarning
            elif byte_2 == 0x9b:
                return PacketType.HandsetInvite
            else:
                return PacketType.Message
        elif byte_1_hi == 0xa or byte_1_hi == 0xd or byte_1_hi == 0x8:
            return PacketType.Message

        return PacketType.Unknown

    def append_data(self, data: bytes) -> None:
        for b in data:
            self._packet_data.append(b)

    def bytes(self) -> bytes:
        return bytes(self._packet_data)

    def handset_num(self) -> int:
        return int(to_hex(self._packet_data[0])[1], 16)

    def __repr__(self) -> str:
        return f"<Packet type: {self.packet_type} data: {hexdump(self.bytes())}>"


class BaseStation:
    device: Optional[HIDDevice]

    read_thread: Thread
    read_loop_flag: bool
    read_buffer: Queue

    decode_thread: Thread
    decode_loop_flag: bool
    decoded_packet_buffer: Queue

    process_thread: Thread
    process_loop_flag: bool

    write_thread: Thread
    write_loop_flag: bool
    write_lock: Lock
    write_buffer: Queue

    poll_thread: Thread
    poll_loop_flag: bool
    handset_connected: bool

    last_write: bytes

    handsets: List[Optional[Handset]]

    string_buffer: Optional[bytearray]

    register_callback: Optional[Callable[[str], bool]]
    connect_callback: Optional[Callable[[Handset], Dict[str, Any]]]
    disconnect_callback: Optional[Callable[[Handset], None]]
    login_callback: Optional[Callable[[Handset], bool]]
    post_login_callback: Optional[Callable[[Handset], None]]
    away_callback: Optional[Callable[[str], None]]

    def __init__(self) -> None:
        self.device = None

        self.read_thread = Thread(target=self.read_loop)
        self.read_loop_flag = False
        self.read_buffer = Queue()

        self.decode_thread = Thread(target=self.decode_loop)
        self.decode_loop_flag = False
        self.decoded_packet_buffer = Queue()

        self.process_thread = Thread(target=self.process_loop)
        self.process_loop_flag = False

        self.write_thread = Thread(target=self.write_loop)
        self.write_loop_flag = False
        self.write_lock = Lock()
        self.write_buffer = Queue()

        self.poll_thread = Thread(target=self.poll_loop)
        self.poll_loop_flag = False
        self.handset_connected = False

        self.last_write = b""

        self.handsets = [None, None, None, None, None, None, None, None]

        self.string_buffer = None

        self.register_callback = None
        self.connect_callback = None
        self.disconnect_callback = None
        self.login_callback = None
        self.post_login_callback = None
        self.away_callback = None

    def open(self) -> None:
        logger.debug("Opening device...")
        self.device = device = HIDDevice()
        try:
            device.open(0x22b8, 0x7f01)
            mfr = device.get_manufacturer_string()
            prd = device.get_product_string()
            ser = device.get_serial_number_string().encode()
            if mfr != "Giant Wireless Technology" or prd != "MX240a MOTOROLA MESSENGER" or ser != b"\xd0\x89":
                raise IOError()
        except IOError:
            logger.error("Error opening device")
            exit(1)

        logger.trace(f"mfr: {device.get_manufacturer_string()}")
        logger.trace(f"prd: {device.get_product_string()}")
        logger.trace(f"ser: {to_hex(device.get_serial_number_string().encode())}")

        self.read_thread.start()
        self.write_thread.start()

        logger.debug("Initializing...")
        self._write(b"\xad\xef\x8d\xff")

        buf = self.read(timeout=0.5)
        if buf == b"":
            logger.trace("Init reply skipped for some reason?")
        elif buf[0:2] == b"\xef\x01":
            logger.trace(f"Init reply: {hexdump(buf[2:])}")
        else:
            logger.warning("Reading real data, you might want to restart the driver")

        logger.debug("Init complete")

        self.decode_thread.start()
        self.process_thread.start()
        self.poll_thread.start()

    def read(self, blocking: bool = True, timeout: Optional[float] = None) -> bytes:
        if self.read_buffer.empty() and not blocking:
            return b""

        try:
            return self.read_buffer.get(timeout=timeout)
        except queue.Empty:
            return b""

    def write(self, data: bytes, ack: bool = False) -> None:
        if not ack:
            self.last_write = data

        self.write_buffer.put(data)

    def _write(self, data: bytes) -> None:
        parts = [
            # pad to 8 bytes
            data[i:i + 8].ljust(8, b"\0")
            for i in range(0, len(data), 8)
        ]

        # write and count amount written
        for part in parts:
            logger.trace(f"[SEND] {hexdump(part)}")
            self.device.write(part)
            time.sleep(0.15)

    def read_loop(self) -> None:
        logger.debug("Starting read thread")
        while not self.read_loop_flag:
            try:
                # read 16 bytes
                data = bytes(self.device.read(16))
                if len(data):
                    logger.trace(f"[RECV] {hexdump(data)}")
                    self.read_buffer.put(data)
            except OSError:
                # catch error on close()
                pass
        logger.debug("Exiting read thread")

    def write_loop(self) -> None:
        logger.debug("Starting write thread")
        while not self.write_loop_flag:
            data = self.write_buffer.get()

            if data == b"":
                continue

            self._write(data)

        logger.debug("Exiting write thread")

    def poll_loop(self) -> None:
        logger.debug("Starting poll thread")
        while not self.poll_loop_flag:
            self.ack()
            time.sleep(1 if self.handset_connected else 3)
        logger.debug("Exiting poll thread")

    def close(self) -> None:
        if self.poll_thread.is_alive():
            self.poll_loop_flag = True
            self.poll_thread.join()

        if self.process_thread.is_alive():
            for _ in range(16):
                self.decoded_packet_buffer.put(Packet(PacketType.Unknown))

            self.process_loop_flag = True
            self.process_thread.join()

        if self.decode_thread.is_alive():
            for _ in range(16):
                self.read_buffer.put(b"")

            self.decode_loop_flag = True
            self.decode_thread.join()

        if self.read_thread.is_alive():
            self.read_loop_flag = True
            self.read_thread.join()

        if self.write_thread.is_alive():
            for _ in range(16):
                self.write_buffer.put(b"")

            self.write_loop_flag = True
            self.write_thread.join()

        logger.debug("Closing Device")
        self.device.close()
        logger.debug("Bye!")

    def decode_loop(self) -> None:
        logger.debug("Starting decode thread")

        packet_in_progress = None

        while not self.decode_loop_flag:
            data = self.read()

            if data == b"":
                continue

            # start of new packet
            if data[0] & 0x80 and data[0] != 0xff and data[0] != 0xfe:
                logger.trace(hexdump(data))
                packet_type = Packet.detect_type(data[0], data[1])
                logger.trace("Packet type: {}", packet_type)
                if packet_type == PacketType.Unknown:
                    raise ValueError(f"Unknown Packet {hexdump(data)}")
                packet_in_progress = Packet(packet_type)
                packet_in_progress.append_data(data)

                if 0xff in data:
                    self.decoded_packet_buffer.put(packet_in_progress)
                    logger.trace("Packet: {}", packet_in_progress)
                    packet_in_progress = None
            else:
                if not packet_in_progress:
                    logger.warning("Cannot append data to nonexistent packet")
                else:
                    packet_in_progress.append_data(data)
                    if 0xff in data or 0xfe in data:
                        self.decoded_packet_buffer.put(packet_in_progress)
                        logger.trace("Packet: {}", packet_in_progress)
                        packet_in_progress = None

        logger.debug("Exiting decode thread")

    def process_loop(self) -> None:
        logger.debug("Starting process thread")
        while not self.process_loop_flag:
            packet = self.decoded_packet_buffer.get()

            if packet.packet_type == PacketType.Unknown:
                continue

            if packet.packet_type == PacketType.Message or packet.packet_type == PacketType.MessageContinuation:
                num = packet.handset_num()
                handset = self.handsets[num]
                message = self.read_string(packet)

                if message:
                    logger.debug(f"Message: {message}")
                    if handset and handset.message_callback:
                        handset.message_callback(message)
            elif packet.packet_type == PacketType.ACK or packet.packet_type == PacketType.MysteryACK:
                self.ack()
            elif packet.packet_type == PacketType.HandsetRegistration:
                handset_id = "".join([to_hex(n) for n in packet.bytes()[2:][0:4]])
                logger.debug(f"Handset registering, ID: {handset_id}")

                result = True
                if self.register_callback:
                    result = self.register_callback(handset_id)

                if result:
                    # accept registration
                    self.write(b"\xee\xd3")
                else:
                    # reject registration
                    self.write(b"\xee\xc5")
            elif packet.packet_type == PacketType.HandsetConnecting:
                self.handset_connected = True
                handset_id = "".join([to_hex(n) for n in packet.bytes()[2:][0:4]])
                handset_num = packet.handset_num()
                logger.debug(f"Handset connecting, ID: {handset_id}")
                self.handsets[handset_num] = Handset(self, handset_num, handset_id)
                handset = self.handsets[handset_num]

                name = "IMFree"
                connect_data = None
                if self.connect_callback:
                    connect_data = self.connect_callback(handset)

                if connect_data and "name" in connect_data:
                    name = connect_data["name"]

                handset.name = name
                self.write(bytes([handset_num, 0xd9, *as_bytes(name), 0xff]))
                self.write(bytes([int(f"e{handset_num}", 16), 0xd7, *as_bytes(" AIM  "), 0xff]))

                # noinspection SpellCheckingInspection
                tones: Dict[str, Optional[Ringtone]] = {
                    # Copied all these ringtones from the original MX240a driver
                    # (including the names (no i dont know why its called bulletme (also these are really annoying)))
                    "newMessage": Ringtone("Dang:d=4,o=5,b=140:16g#5,16e5,16c#5"),  # aol-imrcv.txt
                    "contactOnline": Ringtone("Rikasmiesjos:d=4,o=5,b=100:32b,32d6,32g6,32g6"),  # aol_ring.txt
                    "contactOffline": Ringtone("Bolero:d=4,o=5,b=80:c6"),  # bolero.txt
                    "messageSent": Ringtone("Dang:d=4,o=5,b=140:16b5,16e5,16g#5"),  # aol-imsend.txt
                    "serviceDisconnected": Ringtone("Dang:d=16,o=6,b=200:c,e,d7,c,e,a#,c,e"),  # aol_urgent.txt
                    "serviceConnected": Ringtone("Bulletme:d=4,o=5,b=112:b.5,g.5"),  # bulletme.txt
                    "outOfRange": Ringtone("Dang:d=4,o=5,b=140:4c,8g,8g,8a,4g,2b,c"),  # aol-outofrange.txt
                    "backInRange": Ringtone("Dang:d=32,o=7,b=180:d#,e,g,d#,g,d#,f#,e"),  # aol_in_range.txt
                    "enterSleepMode": Ringtone("Dang:d=4,o=5,b=80:8e,8c,4f,4e,4d,4c"),  # aol_sleep.txt
                }

                if connect_data and "tones" in connect_data:
                    user_tones = connect_data["tones"]
                    for name, tone in user_tones.items():
                        if name in tones:
                            if isinstance(tone, Ringtone):
                                tones[name] = tone
                            elif isinstance(tone, str):
                                tones[name] = Ringtone(tone)
                            else:
                                tones[name] = None

                tone_names_to_id: Dict[str, int] = {
                    "newMessage": 0x02,
                    "contactOnline": 0x03,
                    "contactOffline": 0x04,
                    "messageSent": 0x05,
                    "serviceDisconnected": 0x06,
                    "serviceConnected": 0x07,
                    "outOfRange": 0x08,
                    "backInRange": 0x09,
                    "enterSleepMode": 0x0a,
                }

                for tone_name, tone in tones.items():
                    if tone_name in tone_names_to_id:
                        tone_id = tone_names_to_id[tone_name]
                        if tone:
                            tone_bytes = tone.tone_bytes
                        else:
                            # yeah the "mute tone" function just plays a very short rest, i guess that works
                            tone_bytes = b"\x01\x7f"
                        tone_parts = [tone_bytes[i:i + 20] for i in range(0, len(tone_bytes), 20)]

                        self.write(bytes([int(f"c{handset_num}", 16), 0xcd, tone_id, *tone_parts[0], 0xff]))
                        self.ack()
                        if len(tone_parts) > 1:
                            for part in tone_parts:
                                self.write(bytes([int(f"8{handset_num}", 16), 0xcd, tone_id, *part, 0xff]))
                                self.ack()
            elif packet.packet_type == PacketType.HandsetDisconnected:
                num = packet.handset_num()
                handset = self.handsets[num]
                self.handsets[num] = None

                for item in self.handsets:
                    if item:
                        self.handset_connected = True
                        break
                else:
                    self.handset_connected = False

                logger.debug("Handset disconnect: num {}", num)
                if self.disconnect_callback and handset:
                    self.disconnect_callback(handset)
            elif packet.packet_type == PacketType.HandsetUsername:
                username = self.read_string(packet)
                logger.debug(f"Handset username: {username}")
                self.handsets[packet.handset_num()].username = username
            elif packet.packet_type == PacketType.HandsetPassword:
                password = self.read_string(packet)
                handset_num = packet.handset_num()
                logger.debug(f"Handset password: {password}")
                handset = self.handsets[handset_num]
                handset.password = password

                result = True
                if self.login_callback:
                    result = self.login_callback(handset)

                time.sleep(0.5)

                if result:
                    self.write(bytes([int(f"e{handset_num}", 16), 0xd3, 0xff]))
                    self.ack()
                    logger.debug("Login success")

                    if self.post_login_callback:
                        self.post_login_callback(handset)
                else:
                    self.write(bytes([int(f"e{handset_num}", 16), 0xe5, 0x02, 0xff]))
                    logger.debug("Login failed")
            elif packet.packet_type == PacketType.OpenWindow:
                handset = self.handsets[packet.handset_num()]
                window_id = packet.bytes()[2]
                logger.debug("Window Open: id {}", window_id)
                handset.open_window(window_id)
            elif packet.packet_type == PacketType.CloseWindow:
                handset = self.handsets[packet.handset_num()]
                window_id = packet.bytes()[2]
                logger.debug("Window Close: id {}", window_id)
                handset.close_window(window_id)
            elif packet.packet_type == PacketType.HandsetAway:
                away = self.read_string(packet)
                self.ack()
                logger.debug(f"Away message: {away}")
                if self.away_callback:
                    self.away_callback(away)
            elif packet.packet_type == PacketType.HandsetWarning:
                ...
            elif packet.packet_type == PacketType.HandsetInvite:
                ...
            else:
                logger.warning("Unknown Packet: {}", packet)

        logger.debug("Exiting process thread")

    def read_string(self, packet: Packet) -> Optional[str]:
        if not self.string_buffer:
            self.string_buffer = bytearray()
        buffer = packet.bytes()
        finished = False

        for byte in buffer:
            if byte == 0xff:
                finished = True
                break
            elif 32 <= byte <= 127:
                self.string_buffer.append(byte)

        self.ack()
        logger.trace("Partial Message: " + self.string_buffer.decode())

        if finished:
            string = self.string_buffer.decode()
            self.string_buffer = None
            return string
        return None

    def ack(self, expect_reply: bool = False) -> None:
        self.write(b"\xad", True)
        if expect_reply:
            logger.debug("NAK: " + hexdump(self.read()))
