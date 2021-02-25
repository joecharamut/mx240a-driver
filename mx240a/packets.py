from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, Final, Iterator

from mx240a.rtttl import Ringtone
from mx240a.util import hexdump, to_hex, as_bytes


class Packet(ABC):
    @abstractmethod
    def encode(self) -> Iterator[bytes]:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"

    @staticmethod
    def decode(raw_data: bytes) -> "Packet":
        byte_1 = raw_data[0]
        byte_2 = raw_data[1]

        byte_1_hi = (byte_1 & 0xf0) >> 4

        byte_2_hi = (byte_2 & 0xf0) >> 4
        byte_2_lo = (byte_2 & 0x0f)

        if byte_1 == 0xe0:
            return HandsetRegistrationPacket(raw_data)
        elif (byte_1 == 0xe1 or byte_1 == 0xe2) and byte_2 == 0xfd:
            return MysteryACKPacket(raw_data)
        # elif byte_1 == 0xe8:
        #     return BaseInitACKPacket(raw_data)
        elif byte_1 == 0xef:
            return BaseInitReplyPacket(raw_data)
        elif byte_1_hi == 0xf or byte_1_hi == 0xe:
            if byte_2 == 0xfd:
                return ACKPacket(raw_data)
            elif byte_2 == 0x8c:
                return HandheldDisconnectedPacket(raw_data)
            elif byte_2 == 0x8e:
                return HandheldConnectingPacket(raw_data)
            if byte_2_hi == 0x9 or byte_2_hi == 0xa or byte_2_hi == 0xb:
                if byte_2_lo == 0x1:
                    return HandheldUsernamePacket(raw_data)
                elif byte_2_lo == 0x2:
                    return HandheldPasswordPacket(raw_data)
                elif byte_2_lo == 0x3:
                    # logoff menu
                    return HandheldLogoffPacket(raw_data)
                elif byte_2_lo == 0x4:
                    return OpenWindowPacket(raw_data)
                elif byte_2_lo == 0x5:
                    return CloseWindowPacket(raw_data)
                elif byte_2_lo == 0x6:
                    return HandsetAwayPacket(raw_data)
                elif byte_2_lo == 0xa:
                    return HandsetWarningPacket(raw_data)
                elif byte_2_lo == 0xb:
                    return HandsetInvitePacket(raw_data)
                elif byte_2_lo == 0xd:
                    return HandsetRequestResponsePacket(raw_data)
            else:
                return MessagePacket(raw_data)
        elif byte_1_hi == 0xa or byte_1_hi == 0xd or byte_1_hi == 0x8:
            return MessagePacket(raw_data)

        return UnknownPacket(raw_data)


class TxPacket(Packet):
    @abstractmethod
    def encode(self) -> Iterator[bytes]:
        raise NotImplementedError


class RxPacket(Packet):
    def encode(self) -> Iterator[bytes]:
        raise TypeError("Received packets should not be encoded")


class UnknownPacket(RxPacket):
    def __init__(self, raw_data) -> None:
        self.raw_data = raw_data

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {hexdump(self.raw_data)}>"


class HandsetRegistrationPacket(RxPacket):
    handset_id: str

    def __init__(self, raw_data) -> None:
        handset_id_bytes = raw_data[2:6]
        self.handset_id = "".join([to_hex(b) for b in handset_id_bytes])

    def __repr__(self) -> str:
        return f"<HandsetRegistrationPacket id: {self.handset_id}>"


class MysteryACKPacket(UnknownPacket):
    pass


class BaseInitReplyPacket(RxPacket):
    def __init__(self, raw_data) -> None:
        assert raw_data[0:3] == b"\xef\x01\x01"

    def __repr__(self) -> str:
        return "<BaseInitReplyPacket>"


class ACKPacket(UnknownPacket):
    pass


class HandheldDisconnectedPacket(RxPacket):
    connection_id: int

    def __init__(self, raw_data) -> None:
        self.connection_id = raw_data[0] & 0xf

    def __repr__(self) -> str:
        return f"<HandheldDisconnectedPacket connection: {self.connection_id}>"


class HandheldLogoffPacket(RxPacket):
    connection_id: int

    def __init__(self, raw_data) -> None:
        self.connection_id = raw_data[0] & 0xf

    def __repr__(self) -> str:
        return f"<HandheldLogoffPacket connection: {self.connection_id}>"


class HandheldConnectingPacket(RxPacket):
    handheld_id: str
    connection_id: int

    def __init__(self, raw_data) -> None:
        self.handheld_id = "".join([to_hex(b) for b in raw_data[2:6]])
        self.connection_id = raw_data[0] & 0xf

    def __repr__(self) -> str:
        return f"<HandheldConnectingPacket id: {self.handheld_id}, connection: {self.connection_id}>"


class HandheldUsernamePacket(RxPacket):
    connection_id: int
    username: str

    def __init__(self, raw_data) -> None:
        self.connection_id = raw_data[0] & 0xf
        if len(raw_data) > 2:
            self.username = "".join([chr(c) for c in raw_data[2:]])
        else:
            self.username = ""

    def __repr__(self) -> str:
        return f"<HandheldUsernamePacket username: \"{self.username}\", connection: {self.connection_id}>"


class HandheldPasswordPacket(RxPacket):
    connection_id: int
    password: str

    def __init__(self, raw_data) -> None:
        self.connection_id = raw_data[0] & 0xf
        if len(raw_data) > 2:
            self.password = "".join([chr(c) for c in raw_data[2:]])
        else:
            self.password = ""

    def __repr__(self) -> str:
        return f"<HandheldPasswordPacket password: \"{self.password}\", connection: {self.connection_id}>"


class OpenWindowPacket(UnknownPacket):
    pass


class CloseWindowPacket(UnknownPacket):
    pass


class HandsetAwayPacket(UnknownPacket):
    pass


class HandsetWarningPacket(UnknownPacket):
    pass


class HandsetInvitePacket(UnknownPacket):
    pass


class HandsetRequestResponsePacket(UnknownPacket):
    pass


class MessagePacket(UnknownPacket):
    pass


# Tx Packets Begin Here
class BaseInitPacket(TxPacket):
    def encode(self) -> Iterator[bytes]:
        yield bytes([0xad, 0xef, 0x8d, 0xff])

    def __repr__(self) -> str:
        return "<BaseInitPacket>"


class BaseShutdownPacket(TxPacket):
    def encode(self) -> Iterator[bytes]:
        yield bytes([0xef, 0x8d, 0xff])

    def __repr__(self) -> str:
        return "<BaseInitPacket>"


class PollingPacket(TxPacket):
    def encode(self) -> Iterator[bytes]:
        yield bytes([0xad])

    def __repr__(self) -> str:
        return "<PollingPacket>"


class ServiceInfoPacket(TxPacket):
    connection_id: int
    service_name: str

    def __init__(self, connection_id: int, service_name: str) -> None:
        if connection_id > 7 or connection_id < 1:
            raise ValueError("Invalid connection_id")
        # if len(service_name) > 6:
        #     raise ValueError("Invalid service_name: too long")
        if service_name[1] not in ["A", "a", "M"]:  # AOL, Yahoo, MSN -- handheld uses 2nd char to determine service
            raise ValueError("Invalid service_name: missing magic second character")

        self.connection_id = connection_id
        self.service_name = service_name

    def encode(self) -> Iterator[bytes]:
        yield bytes([
            0xc0 | self.connection_id,
            0xd7,
            *as_bytes(self.service_name),
            0xff,
        ])

    def __repr__(self) -> str:
        return f"<ServiceInfoPacket name: \"{self.service_name}\" connection id: {self.connection_id}>"


class HandheldInfoPacket(TxPacket):
    connection_id: int
    handheld_name: str

    def __init__(self, connection_id: int, handheld_name: str) -> None:
        if connection_id > 7 or connection_id < 1:
            raise ValueError("Invalid connection_id")

        self.connection_id = connection_id
        self.handheld_name = handheld_name

    def encode(self) -> Iterator[bytes]:
        yield bytes([
            0xc0 | self.connection_id,
            0xd9,
            *as_bytes(self.handheld_name),
            0xff,
        ])

    def __repr__(self) -> str:
        return f"<HandheldInfoPacket name: \"{self.handheld_name}\" connection id: {self.connection_id}>"


class RingtonePacket(TxPacket):
    connection_id: int
    tone_id: int
    tone: Ringtone

    TONE_NAME_TO_ID: Final[Dict[str, int]] = {
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

    def __init__(self, connection_id: int, tone_id: str, tone: Ringtone) -> None:
        self.connection_id = connection_id

        try:
            self.tone_id = RingtonePacket.TONE_NAME_TO_ID[tone_id]
        except KeyError:
            raise ValueError("Invalid tone_id")

        self.tone = tone

    def encode(self) -> Iterator[bytes]:
        yield bytes([
            0xc0 | self.connection_id,
            0xcd,
            self.tone_id,
            *self.tone.tone_bytes[:20],
            0xff,
        ])

        tone_bytes = self.tone.tone_bytes
        tone_parts = [tone_bytes[i:i + 20] for i in range(0, len(tone_bytes), 20)]

        if len(tone_parts) > 1:
            for part in tone_parts:
                yield bytes([
                    0x80 | self.connection_id,
                    0xcd,
                    self.tone_id,
                    *part,
                    0xff,
                ])


class LoginSuccessPacket(TxPacket):
    def __init__(self, connection_id: int) -> None:
        if connection_id > 7 or connection_id < 1:
            raise ValueError("Invalid connection_id")
        self.connection_id = connection_id

    def encode(self) -> Iterator[bytes]:
        yield bytes([
            0xe0 | self.connection_id,
            0xd3,
            0xff,
        ])

    def __repr__(self) -> str:
        return f"<LoginSuccessPacket connection id: {self.connection_id}>"


class ErrorPacket(TxPacket):
    class ErrorType(Enum):
        LoginError = 0x00
        InvalidNameOrPassword = 0x01
        ServiceTemporarilyUnavailable = 0x03
        TooFrequently = 0x04
        SignedInToAOLAlready = 0x05
        ErrorConnectingToService = 0x07
        SessionTerminated = 0x08
        InternetConnectionLost = 0x09

    def __init__(self, connection_id: int, errno: ErrorType) -> None:
        if connection_id > 7 or connection_id < 1:
            raise ValueError("Invalid connection_id")
        self.connection_id = connection_id
        self.errno = errno

    def encode(self) -> Iterator[bytes]:
        yield bytes([
            0xe0 | self.connection_id,
            0xe5,
            self.errno.value,
            0xff,
        ])

    def __repr__(self) -> str:
        return f"<ErrorPacket connection id: {self.connection_id} errno: {self.errno.name}>"
