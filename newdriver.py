import queue
import re
import sys
from enum import Enum
from queue import Queue
from threading import Thread
import time
from typing import Union, List, Optional, Any, Callable, Dict
from multiprocessing import Lock

# noinspection PyPep8Naming
from hid import device as HIDDevice


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


LOG_LOCK = Lock()
DEBUG_LOG_ENABLED = True
VERBOSE_LOG_ENABLED = False


def log(msg: str, name: str) -> None:
    with LOG_LOCK:
        print(f"[{name.ljust(7)}]: {msg}")


def warn(msg: str) -> None:
    log(msg, "WARN")


def debug(msg: Any) -> None:
    if DEBUG_LOG_ENABLED:
        log(f"{msg if isinstance(msg, str) else msg.__repr__()}", "DEBUG")


def verbose(msg: Any) -> None:
    if VERBOSE_LOG_ENABLED:
        log(f"{msg if isinstance(msg, str) else msg.__repr__()}", "VERBOSE")


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

        verbose(f"RTTTL Input \"{tone_data}\"")
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

        verbose(f"RTTTL: \"{name}\" (Note Duration: {duration}, Octave: {octave}, BPM: {bpm}) Notes: {notes}")
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
                warn("RTTTL WARNING: Pauses do not work correctly on the handset")
            output_bytes.append(0x7f if note == "p" else Ringtone.NOTE_TO_HEX[full_note])

        verbose(f"RTTTL Output {hexdump(output_bytes)}")

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


class Handset:
    base: "BaseStation"
    num: int
    id: str
    name: Optional[str]
    username: Optional[str]
    password: Optional[str]
    buddy_list: Dict[str, List[Optional[Buddy]]]

    message_callback = Optional[Callable[[str], None]]

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

        self.message_callback = None

    def send_message(self, window: int, message: str) -> None:
        self.base.write(bytes([int(f"8{self.num}", 16), window, *as_bytes(message), 0xff]))
        self.base.write(bytes([int(f"e{self.num}", 16), 0xce, window]))

    def add_buddy(self, buddy: Buddy, group: str) -> None:
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


class BaseStation:
    device: Optional[HIDDevice]

    read_thread: Thread
    read_semaphore: bool
    read_buffer: Queue

    process_thread: Thread
    process_semaphore: bool

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
        self.read_semaphore = False
        self.read_buffer = Queue()

        self.process_thread = Thread(target=self.process_loop)
        self.process_semaphore = False

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
        try:
            debug("Opening device...")
            self.device = device = HIDDevice()
            device.open(0x22b8, 0x7f01)
            debug(f"mfr: {device.get_manufacturer_string()}")
            debug(f"prd: {device.get_product_string()}")
            debug(f"ser: {to_hex(device.get_serial_number_string().encode())}")

            self.read_thread.start()

            debug("Initializing...")
            self.write(b"\xad\xef\x8d\xff")

            buf = self.read(timeout=0.5)
            if buf == b"":
                debug("Init reply skipped for some reason?")
            elif buf[0:2] == b"\xef\x01":
                debug(f"Init reply: {hexdump(buf[2:])}")
            else:
                debug("Reading real data uh oh")

            debug("Init complete?")
            self.process_thread.start()
        except IOError:
            print("Failed to open base")
            sys.exit(1)

    def read(self, blocking: bool = True, timeout: Optional[float] = None) -> bytes:
        if self.read_buffer.empty() and not blocking:
            return b""

        try:
            return self.read_buffer.get(timeout=timeout)
        except queue.Empty:
            return b""

    def write(self, data: bytes, ack: bool = False) -> int:
        if not ack:
            self.last_write = data

        # split into octets
        parts = [
            # pad to 8 bytes
            data[i:i + 8].ljust(8, b"\0")
            for i in range(0, len(data), 8)
        ]

        # write and count amount written
        sent = 0
        for octet in parts:
            verbose(f"[SEND] {hexdump(octet)}")
            sent += self.device.write(octet)
            time.sleep(0.15)

        return sent

    def read_loop(self) -> None:
        debug("Starting read thread")
        while not self.read_semaphore:
            try:
                # read 16 bytes
                data = bytes(self.device.read(16))
                if len(data):
                    verbose(f"[RECV] {hexdump(data)}")
                    self.read_buffer.put(data)
            except OSError:
                # catch error on close()
                pass
        debug("Exiting read thread")

    def close(self) -> None:
        # put some nulls to clear out any blocking reads
        for _ in range(16):
            self.read_buffer.put(b"")

        if self.process_thread.is_alive():
            self.process_semaphore = True
            self.process_thread.join()

        if self.read_thread.is_alive():
            self.read_semaphore = True
            self.read_thread.join()

        debug("Closing Device")
        self.device.close()
        debug("Bye!")

    def process_loop(self) -> None:
        debug("Starting process thread")
        while not self.process_semaphore:
            data = self.read()

            if data == b"":
                continue

            command, handset_num = to_hex(data[0])
            function = to_hex(data[1])
            extra = data[2:]
            verbose(f"Command: {command}, Handset Num: {handset_num}, Function: {function}, Extra: {hexdump(extra)}")

            if command == "a" or command == "d" or command == "8":
                self.read_message(self.handsets[int(handset_num)], data)
            elif command == "c":
                debug(f"Command c (NAK?)")
            elif command == "e" or command == "f":
                if not self.handle_function(command, handset_num, function, extra):
                    self.read_message(self.handsets[int(handset_num)], data)
            else:
                debug(f"Unknown command: {command}")

        debug("Exiting process thread")

    def handle_function(self, command: str, handset_num: str, function: str, extra: bytes) -> bool:
        nak = False
        if command == "e":
            if handset_num == "0" or handset_num == "c":
                # reg new handset
                handset_id = "".join([to_hex(n) for n in extra[0:4]])
                debug(f"Registration req handset ID: {handset_id}")

                result = True
                if self.register_callback:
                    result = self.register_callback(handset_id)

                if result:
                    # accepted
                    self.write(b"\xee\xd3")
                else:
                    # rejected
                    self.write(b"\xee\xc5")
                self.ack()
                return True
            elif handset_num == "1" or handset_num == "2":
                # mystery function
                self.ack()
                return True
            elif handset_num == "8":
                # "init base ack?"
                self.ack(True)
                return True
            elif handset_num == "f":
                debug("Base init reply")
                return True
            else:
                debug(f"e gives up")
                command = "f"
                nak = True

        if command == "f":
            if function == "fd":
                # ACK?
                if nak:
                    self.write(self.last_write)
                if extra[0] == 1 or extra[0] == 2:
                    self.ack()
                return True
            elif function == "69":
                self.ack(True)
                return True
            elif function == "8c":
                if extra[0] == 0xff or extra[0] == 0xc1:
                    if self.disconnect_callback:
                        self.disconnect_callback(self.handsets[int(handset_num)])
                    self.handsets[int(handset_num)] = None
                    debug(f"Handset {handset_num} disconnected")
                else:
                    self.ack(True)
                return True
            elif function == "8e":
                handset_id = "".join([to_hex(n) for n in extra[0:4]])
                debug(f"Handset connecting, ID: {handset_id}")
                self.handsets[int(handset_num)] = handset = Handset(self, int(handset_num), handset_id)

                name = "IMFree"
                connect_data = None
                if self.connect_callback:
                    connect_data = self.connect_callback(handset)

                if connect_data and "name" in connect_data:
                    name = connect_data["name"]

                handset.name = name
                self.write(bytes([int(handset_num), 0xd9, *as_bytes(name), 0xff]))
                self.write(bytes([int(f"e{handset_num}", 16), 0xd7, *as_bytes(" AIM  "), 0xff]))

                # noinspection SpellCheckingInspection
                tones: Dict[str, Optional[Ringtone]] = {
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
                            tone_bytes = b"\x01\x7f"
                        tone_parts = [tone_bytes[i:i + 20] for i in range(0, len(tone_bytes), 20)]

                        self.write(bytes([int(f"c{handset_num}", 16), 0xcd, tone_id, *tone_parts[0], 0xff]))
                        self.ack()
                        if len(tone_parts) > 1:
                            for part in tone_parts:
                                self.write(bytes([int(f"8{handset_num}", 16), 0xcd, tone_id, *part, 0xff]))
                                self.ack()
                return True
            elif function == "91":
                username = self.read_string(extra)
                debug(f"Handset username: {username}")
                self.handsets[int(handset_num)].username = username
                return True
            elif function == "92":
                password = self.read_string(extra)
                debug(f"Handset password: {password}")
                handset = self.handsets[int(handset_num)]
                handset.password = password

                result = True
                if self.login_callback:
                    result = self.login_callback(handset)

                if result:
                    self.write(bytes([int(f"e{handset_num}", 16), 0xd3, 0xff]))
                    self.ack()
                    debug("Login success")

                    if self.post_login_callback:
                        self.post_login_callback(handset)
                else:
                    self.write(bytes([int(f"e{handset_num}", 16), 0xe5, 0x02, 0xff]))
                    debug("Login failed")
                return True
            elif function == "93":
                debug("todo: fN 93")
                return True
            elif function == "94":
                debug("todo: fN 94")
                return True
            elif function == "95":
                debug("todo: fN 95")
                return True
            elif function == "96":
                away = self.read_string(extra)
                self.ack()
                debug(f"Away message: {away}")
                if self.away_callback:
                    self.away_callback(away)
                return True
            elif function == "9a":
                debug("todo: fN 9a (warn)")
                return True
            elif function == "9b":
                debug("todo: fN 9b (invite)")
                return True
            return False

    def read_message(self, handset: Optional[Handset], extra: bytes):
        skip = 1
        message = self.read_string(extra, skip)
        if handset and handset.message_callback:
            handset.message_callback(message)
        debug(f"Message: {message}")

    def read_string(self, initial_buffer: bytes, skip: int = 2) -> str:
        string = bytearray()
        buffer = initial_buffer.rjust(8, b"\0")
        i = skip
        while (byte := buffer[i]) != 0xff:
            if byte == 0xfe:
                self.ack()
            if byte == 0xff:
                break
            elif 32 <= byte <= 127:
                string.append(byte)

            i += 1
            if i >= 8:
                i = 0
                buffer = self.read(timeout=0.25)
                if not buffer:
                    self.ack()
                    buffer = self.read()
        self.ack()
        return string.decode()

    def ack(self, expect_reply: bool = False) -> bool:
        if not self.write(b"\xad\xff", True):
            return False
        if expect_reply:
            debug("NAK: " + hexdump(self.read()))
        return True
