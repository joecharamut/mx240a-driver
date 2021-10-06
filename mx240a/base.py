from threading import Lock, Thread, Event
from time import sleep, time
from typing import Optional
from queue import Queue

# noinspection PyPep8Naming
from hid import device as HIDDevice

import mx240a.packets
from mx240a.logging import logger
from mx240a.util import hexdump
from mx240a.packets import Packet, BaseInitPacket, BaseShutdownPacket, BaseInitReplyPacket


class Base:
    write_lock: Lock
    read_lock: Lock
    device: Optional[HIDDevice]
    write_queue: Queue
    last_ack_time: float

    def __init__(self) -> None:
        self.device = None
        self.write_lock = Lock()
        self.read_lock = Lock()
        self.write_queue = Queue()
        self.last_ack_time = 0

        self._open()

    def _open_dev(self) -> bool:
        vendor_id = 0x22b8
        product_id = 0x7f01

        self.device = device = HIDDevice()
        try:
            device.open(vendor_id, product_id)
            mfr = device.get_manufacturer_string()
            prd = device.get_product_string()
            if mfr == "Giant Wireless Technology" and prd == "MX240a MOTOROLA MESSENGER":
                return True
        except IOError as e:
            logger.error(e)
            pass

        return False

    def _open_init_dev(self) -> bool:
        self.write(BaseInitPacket())

        stop_event = Event()
        error = Event()

        def _wait_init_reply() -> None:
            while not stop_event.is_set():
                packet = self.read()
                if packet and isinstance(packet, BaseInitReplyPacket):
                    logger.trace(f"Got init reply: {packet}")
                    break
                elif packet:
                    error.set()
                    logger.debug(f"Got packet but not init reply: {packet}")
                    break

        wait = Thread(target=_wait_init_reply)
        wait.start()
        wait.join(2)
        if wait.is_alive() or error.is_set():
            stop_event.set()
            wait.join()
            return False
        return True

    def _open(self) -> None:
        logger.info("Opening base")
        if not self._open_dev():
            raise RuntimeError("Unable to open base")

        logger.debug(f"mfr: {self.device.get_manufacturer_string()}")
        logger.debug(f"prd: {self.device.get_product_string()}")

        logger.debug("Initializing base")
        retries = 0
        while retries < 3:
            if not self._open_init_dev():
                self.write(BaseShutdownPacket())
                sleep(0.5)
                retries += 1
            else:
                break
        else:
            raise RuntimeError("Failed to initialize base")
        logger.debug("Init success")

    def _close(self) -> None:
        logger.info("Base shutting down")
        self.write(BaseShutdownPacket())
        self.device.close()

    def close(self) -> None:
        self._close()

    def _read(self) -> Optional[Packet]:
        with self.read_lock:
            try:
                # 255 bytes max, 1 second timeout
                data = bytes(self.device.read(255, 1000))
            except OSError as e:
                logger.warning(e)
                data = bytes()
                pass
            if len(data):
                while 0xff not in data and 0xfe not in data:
                    read_data = self.device.read(-1)
                    if read_data:
                        data += bytes(read_data)
                    else:
                        break
                # todo: check if this breaks anything
                data = data.split(b"\xff")[0]
                logger.trace(f"[RECV] {hexdump(data)}")
                packet = Packet.decode(data)
                return packet
            return None

    def read(self) -> Optional[Packet]:
        return self._read()

    def _write(self, data: bytes) -> None:
        with self.write_lock:
            # windows requires an extra 0x00 before the packet for unknowable reasons
            data = b"\x00" + data
            parts = [
                # pad to 8 bytes
                data[i:i + 8].ljust(8, b"\0")
                for i in range(0, len(data), 8)
            ]

            for part in parts:
                logger.trace(f"[SEND] {hexdump(part)}")
                self.device.write(part)
            # todo test how much to delay
            # sleep(0.05)

    def write(self, packet: Packet) -> None:
        if isinstance(packet, mx240a.packets.ImmediateTxPacket):
            for data in packet.encode():
                self._write(data)

            if isinstance(packet, mx240a.packets.PollingPacket):
                while not self.write_queue.empty():
                    delta = time() - self.last_ack_time
                    if delta > 0.5:
                        sleep(0.15)
                    for data in self.write_queue.get().encode():
                        self._write(data)
        else:
            self.write_queue.put(packet)

    def ack(self, packet) -> None:
        self.last_ack_time = time()
