from time import monotonic
from typing import Type, Dict, Callable, TypeVar, Final, Optional

from mx240a.service import Service
from mx240a.base import Base
from mx240a.packets import Packet, HandheldConnectingPacket, HandheldDisconnectedPacket, \
    HandheldInfoPacket, ServiceInfoPacket, PollingPacket, RingtonePacket, HandheldUsernamePacket, \
    HandheldPasswordPacket, ErrorPacket, LoginSuccessPacket
from mx240a.logging import logger
from mx240a.handheld import Handheld
from mx240a.rtttl import Ringtone
from mx240a.util import as_bytes

PacketType = TypeVar("PacketType", bound="Packet")


class Driver:
    base: Base
    PACKET_DISPATCH_TABLE: Final[Dict[Type[Packet], Callable[[PacketType], None]]]
    num_connections: int
    connections: Dict[int, Optional[Handheld]]
    last_time: int
    ping_timer: int
    service: Service

    def __init__(self, service: Service) -> None:
        self.base = Base()
        self.PACKET_DISPATCH_TABLE = {
            HandheldConnectingPacket: self.handle_connection_packet,
            HandheldDisconnectedPacket: self.handle_disconnect_packet,
            HandheldUsernamePacket: self.handle_username_packet,
            HandheldPasswordPacket: self.handle_password_packet,
        }
        self.num_connections = 0
        self.connections = {
            1: None,
            2: None,
            3: None,
            4: None,
            5: None,
            6: None,
            7: None,
        }
        self.last_time = int(monotonic() * 1000)
        self.ping_timer = 0
        self.service = service

    def loop(self) -> None:
        try:
            while True:
                self.do_one_loop()
        except KeyboardInterrupt:
            logger.info("Caught KeyboardInterrupt, exiting...")
        finally:
            self.base.close()

    def do_one_loop(self) -> None:
        cur_time = int(monotonic() * 1000)
        delta = cur_time - self.last_time
        self.last_time = cur_time

        if packet := self.base.read():
            self.process_packet(packet)

        self.ping_timer += delta
        time_limit = 500 if self.num_connections else 3000
        if self.ping_timer > time_limit:
            assert self.num_connections >= 0
            self.ping_timer = 0
            self.base.write(PollingPacket())

    def process_packet(self, packet: Packet) -> None:
        logger.trace(f"[RECV] Packet {packet}")
        try:
            self.PACKET_DISPATCH_TABLE[type(packet)](packet)
        except KeyError:
            logger.error(f"No handler for packet type {type(packet).__name__}")

    def handle_connection_packet(self, packet: HandheldConnectingPacket) -> None:
        handheld_id = packet.handheld_id
        connection_id = packet.connection_id
        logger.debug(f"Handheld {connection_id} connecting, ID: {handheld_id}")

        self.num_connections += 1
        self.connections[connection_id] = Handheld(self, connection_id, handheld_id)

        # todo: check for registration info
        name = "IMFree"
        self.base.write(HandheldInfoPacket(connection_id, name))
        self.base._write(bytes([
            0xc0 | connection_id,
            0xd1,
            *as_bytes(" MSN  "),
            0xff
        ]))
        self.base.write(ServiceInfoPacket(connection_id, self.service.service_id))

        return

        # noinspection SpellCheckingInspection
        tones = {
            # All these ringtones are copied from the original MX240a driver
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

        mute_tone = Ringtone(None)
        for tone_name, tone in tones.items():
            if not tone:
                tone = mute_tone
            self.base.write(RingtonePacket(connection_id, tone_name, tone))

    def handle_disconnect_packet(self, packet: HandheldDisconnectedPacket) -> None:
        connection_id = packet.connection_id
        logger.debug(f"Handheld {connection_id} disconnected")

        self.num_connections -= 1
        self.connections[connection_id] = None

    def handle_username_packet(self, packet: HandheldUsernamePacket) -> None:
        connection_id = packet.connection_id
        logger.debug(f"Handheld {connection_id} username: \"{packet.username}\"")
        handheld = self.connections[connection_id]
        if handheld:
            handheld.username = packet.username

    def handle_password_packet(self, packet: HandheldPasswordPacket) -> None:
        connection_id = packet.connection_id
        logger.debug(f"Handheld {connection_id} password: \"{packet.password}\"")
        handheld = self.connections[connection_id]
        if handheld:
            handheld.password = packet.password

        if self.service.handheld_login(handheld):
            self.base.write(LoginSuccessPacket(connection_id))
        else:
            self.base.write(ErrorPacket(connection_id, ErrorPacket.ErrorType.ServiceTemporarilyUnavailable))
