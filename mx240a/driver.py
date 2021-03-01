from time import monotonic
from typing import Type, Dict, Callable, TypeVar, Final, Optional

from mx240a.connection import Service, HandheldManager
from mx240a.base import Base
from mx240a.packets import Packet, HandheldConnectingPacket, HandheldDisconnectedPacket, \
    HandheldInfoPacket, ServiceInfoPacket, PollingPacket, RingtonePacket, HandheldUsernamePacket, \
    HandheldPasswordPacket, ErrorPacket, LoginSuccessPacket
from mx240a.logging import logger
from mx240a.handheld import Handheld
from mx240a.rtttl import Ringtone

PacketInstanceType = TypeVar("PacketInstanceType", bound="Packet")


class Driver:
    base: Base
    PACKET_DISPATCH_TABLE: Final[Dict[Type[Packet], Callable[[PacketInstanceType], None]]]
    num_connections: int
    connections: Dict[int, Optional[Handheld]]
    last_time: int
    ping_timer: int
    service: Service

    def __init__(self, handheld_manager: HandheldManager, service: Service) -> None:
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
        self.handheld_manager = handheld_manager

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

        connect_info = self.handheld_manager.connect_handheld(handheld_id)
        assert connect_info  # todo: error out on null
        self.base.write(HandheldInfoPacket(connection_id, connect_info.handheld_name))
        self.base.write(ServiceInfoPacket(connection_id, self.service.service_id))

        mute = Ringtone(None)
        for tone_name, tone in connect_info.tones.as_dict().items():
            self.base.write(RingtonePacket(connection_id, tone_name, tone if tone else mute))

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
