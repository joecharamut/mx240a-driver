from time import monotonic, sleep
from typing import Type, Dict, Callable, TypeVar, Final, Optional, List, Tuple

from mx240a.connection import Service, HandheldManager
from mx240a.base import Base
from mx240a.packets import Packet, HandheldConnectingPacket, HandheldDisconnectedPacket, \
    HandheldInfoPacket, ServiceInfoPacket, PollingPacket, RingtonePacket, HandheldUsernamePacket, \
    HandheldPasswordPacket, ErrorPacket, LoginSuccessPacket, HandheldRegistrationPacket, \
    HandheldRegistrationReplyPacket, BuddyStatusPacket, BuddyInfoPacket, OpenWindowPacket,\
    CloseWindowPacket, ACKPacket
from mx240a.logging import logger
from mx240a.handheld import Handheld, Buddy
from mx240a.rtttl import Ringtone

PacketInstanceType = TypeVar("PacketInstanceType", bound="Packet")


class Driver:
    base: Base
    PACKET_DISPATCH_TABLE: Final[Dict[Type[Packet], Callable[[PacketInstanceType], None]]]
    num_connections: int
    connections: Dict[int, Optional[Handheld]]
    last_time: int
    service: Service

    def __init__(self, handheld_manager: HandheldManager, service: Service) -> None:
        self.base = Base()
        self.PACKET_DISPATCH_TABLE = {
            HandheldRegistrationPacket: self.handle_registration_packet,
            HandheldConnectingPacket: self.handle_connection_packet,
            HandheldDisconnectedPacket: self.handle_disconnect_packet,
            HandheldUsernamePacket: self.handle_username_packet,
            HandheldPasswordPacket: self.handle_password_packet,
            ACKPacket: self.handle_ack_packet,
            OpenWindowPacket: self.handle_open_window_packet,
            CloseWindowPacket: self.handle_close_window_packet,
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

        self.future_tasks: List[Tuple[int, Callable[[], None]]] = []

    def loop(self) -> None:
        try:
            while True:
                self.event_loop()
        except KeyboardInterrupt:
            logger.info("Caught KeyboardInterrupt, exiting...")
        finally:
            self.base.close()

    def event_loop(self) -> None:
        cur_time = int(monotonic() * 1000)
        delta = cur_time - self.last_time
        self.last_time = cur_time

        if delta > 20:
            logger.warning(f"Tick took {delta} ms!")

        if packet := self.base.read():
            self.process_packet(packet)

        next_tasks = []
        for task_time, task_target in self.future_tasks:
            new_task_time = task_time - delta
            if new_task_time <= 0:
                task_target()
            else:
                next_tasks.append((new_task_time, task_target))
        self.future_tasks = next_tasks

        self.ping_timer += delta
        if (self.num_connections > 0 and self.ping_timer >= 500) or self.ping_timer >= 3000:
            self.ping_timer = 0
            assert self.num_connections >= 0
            self.base.write(PollingPacket())

    def run_later(self, ms: int, target: Callable[[], None]):
        self.future_tasks.append((ms, target))

    def send_buddy_info(self, connection_id: int, buddy: Buddy):
        self.base.write(BuddyStatusPacket(connection_id, buddy))
        self.base.write(BuddyInfoPacket(connection_id, buddy))
        # todo: figure out what the "status modifier" packet does
        self.base._write(bytes([
            0xa0 | connection_id,
            0xc9,
            0x01,
            0xff,
        ]))
        # todo: figure out how long to delay
        sleep(0.1)

    def process_packet(self, packet: Packet) -> None:
        logger.trace(f"[RECV] Packet {packet}")
        try:
            self.PACKET_DISPATCH_TABLE[type(packet)](packet)
        except KeyError:
            logger.error(f"No handler for packet type {type(packet).__name__}")

    def handle_registration_packet(self, packet: HandheldRegistrationPacket) -> None:
        handheld_id = packet.handset_id
        logger.debug(f"Handheld {handheld_id} attempting to register")

        # self.num_connections += 1

        register_result = self.handheld_manager.register(handheld_id)
        self.base.write(HandheldRegistrationReplyPacket(register_result))

    def handle_connection_packet(self, packet: HandheldConnectingPacket) -> None:
        handheld_id = packet.handheld_id
        connection_id = packet.connection_id
        logger.debug(f"Handheld {connection_id} connecting, ID: {handheld_id}")

        self.num_connections += 1
        self.connections[connection_id] = Handheld(self, connection_id, handheld_id)

        connect_info = self.handheld_manager.connect(handheld_id)
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

        if self.service.login(handheld):
            self.base.write(LoginSuccessPacket(connection_id))
            self.run_later(500, lambda: self.service.ready(handheld))
        else:
            self.base.write(ErrorPacket(connection_id, ErrorPacket.ErrorType.ServiceTemporarilyUnavailable))

    def handle_open_window_packet(self, packet: OpenWindowPacket) -> None:
        ...

    def handle_close_window_packet(self, packet: CloseWindowPacket) -> None:
        ...

    def handle_ack_packet(self, packet: ACKPacket) -> None:
        self.base.ack(packet)
