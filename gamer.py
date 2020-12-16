from driver import Handset, MX240a, Base
from driver import hexdump
from discord_interface import DiscordInterface
from threading import Thread
import asyncio
from queue import Queue
import time


def debug(msg: str) -> None:
    if True:
        print("[MAIN   ]: {}".format(msg))


class HandsetInterface:
    def __init__(self):
        self.base = Base()
        self.base._on_im = self.on_im
        self.base._on_connect = self.on_connect
        self.base._on_disconnect = self.on_disconnect
        self.base._on_login = self.on_login
        self.base._on_login_complete = self.on_login_complete
        self.base._on_window_open = self.on_window_open
        self.base._on_window_close = self.on_window_close
        self.base._on_data_in = self.on_data_in
        self.base._on_data_out = self.on_data_out
        self.base._on_away = self.on_away

        self.current_window = None
        self.is_away = False

        self.handset = None
        self.on_message = None
        self.on_away_message = None
        self.on_ready = None
        self.on_close = None
        self.message_queue = asyncio.Queue()

    async def handset_loop(self):
        try:
            while True:
                self.base.do_one_loop()
                await asyncio.sleep(0.001)
        except:
            self.base._close()
            raise

    async def send_queue(self):
        while True:
            try:
                msg = self.message_queue.get_nowait()
                if self.handset:
                    self.handset._send_im(self.handset.window, msg)
            except asyncio.queues.QueueEmpty:
                pass
            await asyncio.sleep(0.25)

    def start(self):
        asyncio.get_child_watcher()
        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self.handset_loop())
        self.loop.create_task(self.send_queue())
        self.thread = Thread(target=self.loop.run_forever)
        self.thread.start()

    def on_away(self, handset, message):
        debug(f"Away: {message}")
        self.is_away = True
        if self.on_away_message:
            self.on_away_message(message)

    def on_im(self, handset, message):
        debug(f"IM: {message}")
        if self.on_message:
            self.on_message(message)

    def on_connect(self, handset):
        return ("PyIMFree", {
            "A": " AIM   ",
            # "Y": "",
            # "M": "",
        })

    def on_disconnect(self, handset):
        debug(f"disconnect: handset id {handset.id}")
        self.handset = None
        if self.on_close:
            self.on_close()

    def on_login(self, handset):
        debug(f"Login: {handset.username}:{handset.password} @ {handset.service}")
        return 1 # okay
        return 0 # deny

    def on_login_complete(self, handset):
        self.handset = handset
        handset._buddy_in({"screenname":"i", "group":"Group"})

    def on_window_open(self, handset, buddy, with_ack, check = False):
        debug(f"(H|{handset.id}) Open window (#{handset.window}) with buddy (#{buddy}), check: {check}")

        if self.is_away:
            self.is_away = False
            self.on_away(handset, None)
            return 1

        if self.current_window == handset.window:
            return 1

        self.current_window = handset.window

        if self.on_ready:
            self.on_ready()

        return 1

    def on_window_close(self, handset):
        debug(f"(H|{handset.id}) Close window (#{handset.window})")

        if self.on_close:
            self.on_close()

        self.current_window = None

        return 1

    def on_data_in(self, data):
        print("[RECIEVE]: " + hexdump(data, end=""))

    def on_data_out(self, data):
        print("[SEND   ]: " + hexdump(data, end=""))

    def send_im(self, message):
        self.message_queue.put_nowait(message)

class ProgramManager():
    def __init__(self, base):
        self.base = base
        self.shell = Shell(self)
        self.running_program = None
        self.shell_open = True
        self.programs = []

    def on_away_message(self, message):
        if self.running_program:
            self.running_program.on_away(message)

    def on_message(self, message):
        debug(f"message: {message}")
        message = message.decode("ascii")
        if message == ";":
            if not self.shell_open:
                self.shell_open = True
                self.shell.init()
                return

        if not self.running_program or self.shell_open:
            self.shell.on_message(message)
        else:
            self.running_program.on_message(message)

    def on_ready(self):
        self.shell.init()

    def on_close(self):
        if self.running_program:
            self.running_program.close()
        self.running_program = None
        self.shell_open = True

    def register_program(self, program_class):
        program = program_class(self)
        if program not in self.programs:
            self.programs.append(program)

    def run_program(self, program):
        if self.running_program:
            self.running_program.close()
        self.running_program = program
        self.shell_open = False
        program.init()

class Program():
    def __init__(self, base):
        self.base = base

    def name(self):
        return "prgm"

    def on_away(self, message):
        pass

    def on_message(self, message):
        pass

    def init(self):
        pass

    def close(self):
        pass

    def send_message(self, message):
        self.base.send_im(message)

class Shell(Program):
    def __init__(self, manager):
        super().__init__(manager.base)
        self.manager = manager
        self.commands = {
            ("list", "l", self.list_handler),
            ("run", "r", self.run_handler),
            ("continue", "c", self.continue_handler),
        }

    def name(self):
        return "shell"

    def on_message(self, message):
        debug(f"shell message: {message}")
        split = message.split(" ")
        cmd = split[0]
        for long, short, func in self.commands:
            if cmd == long or cmd == short:
                func(split[1:])
                break
        else:
            self.send_message(f"Unknown command: {cmd}")

    def init(self):
        self.send_message(f"Current Program: {self.manager.running_program.name() if self.manager.running_program else None}")
        self.send_message("Shell> ")
        debug("shell open")

    def list_handler(self, args):
        debug("list")
        self.send_message(f"Programs: ({','.join([p.name() for p in self.manager.programs])})")

    def run_handler(self, args):
        debug(f"run {args}")
        self.send_message(f"Launching {args[0]}...")
        program = args[0]
        for p in self.manager.programs:
            if p.name() == program:
                self.manager.run_program(p)
                break
        else:
            self.send_message("Program does not exist")

    def continue_handler(self, args):
        if not self.manager.running_program:
            self.send_message("No running program")
        else:
            self.send_message(f"Continuing {self.manager.running_program.name()}")
            self.manager.shell_open = False

class Echo(Program):
    def __init__(self, manager):
        super().__init__(manager.base)

    def name(self):
        return "echo"

    def on_message(self, message):
        self.send_message(message)

    def init(self):
        self.send_message("Echo ready")

class Discord(Program):
    def __init__(self, manager):
        super().__init__(manager.base)
        self.manager = manager
        self.discord_interface = DiscordInterface(self.on_ready, self.on_discord_message)

    def name(self):
        return "discord"

    def on_away(self, message):
        if message:
            self.send_discord(f"{self.discord_interface.client.user.display_name} is now away: \"{message}\"")
        else:
            self.send_discord(f"{self.discord_interface.client.user.display_name} has returned")

    def on_message(self, message):
        debug(message)
        if message[0] == "/":
            self.process_command(message)
        else:
            self.send_discord(message)

    def on_discord_message(self, message):
        debug(message)
        self.send_handset("<{}>: {}".format(message.author.display_name, message.clean_content))

    def on_ready(self):
        self.send_handset("Logged in as " + self.discord_interface.client.user.name)
        self.discord_interface.select_server(21)
        self.discord_interface.select_channel(6)

    def init(self):
        self.discord_interface.init()
        self.send_message("Logging in...")

    def close(self):
        self.discord_interface.close()

    def send_discord(self, message):
        self.discord_interface.send_message(message)

    def send_handset(self, message):
        self.send_message(message)

    def process_command(self, message):
        split = message[1:].split(" ")
        debug(split)
        if split[0] == "server" or split[0] == "s":
            if len(split) == 1:
                for i, server in self.discord_interface.get_servers():
                    self.send_handset(f"({i}): {server}")
            else:
                try:
                    if self.discord_interface.select_server(int(split[1])):
                        self.send_handset(f"Switched to server {self.discord_interface.selected_server.name}")
                    else:
                        self.send_handset("Server not found")
                except:
                    self.send_handset("Invalid Server Index")
        elif split[0] == "channel" or split[0] == "c":
            if len(split) == 1:
                for i, server in self.discord_interface.get_channels():
                    self.send_handset(f"({i}): {server}")
            else:
                try:
                    if self.discord_interface.select_channel(int(split[1])):
                        self.send_handset(f"Switched to channel #{self.discord_interface.selected_channel.name}")
                    else:
                        self.send_handset("Channel not found")
                except:
                    self.send_handset("Invalid Channel Index")


# message len <= 36 works
# 37+ breaks

#hexdump([0x41, 0x41, 0x00, 0x11, 0x22, 0x33, 0x44])
#exit()

if __name__ == "__main__":
    iface = HandsetInterface()
    pmgr = ProgramManager(iface)

    pmgr.register_program(Echo)
    pmgr.register_program(Discord)

    iface.on_message = pmgr.on_message
    iface.on_away_message = pmgr.on_away_message
    iface.on_ready = pmgr.on_ready
    iface.on_close = pmgr.on_close

    iface.start()
