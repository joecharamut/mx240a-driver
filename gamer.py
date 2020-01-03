from driver import Handset, MX240a, Base

from driver import hexdump

import discord
import asyncio
import threading

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

        self.handset = None
        self.on_message = None
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

    def run_forever(self):
        self.loop.run_forever()

    def start(self):
        asyncio.get_child_watcher()
        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self.handset_loop())
        self.loop.create_task(self.send_queue())
        self.thread = threading.Thread(target=self.run_forever)
        self.thread.start()

    def on_im(self, handset, message):
        print(f"IM > {message}")
        if self.on_message:
            self.on_message(message)

    def on_connect(self, handset):
        return ("Gamer", {
            "A": "aAaaaa",
            #"Y": "Gamer2",
            #"M": "Gamer3",
        })

    def on_disconnect(self, handset):
        print(f"disconnect: handset id {handset.id}")
        self.handset = None
        if self.on_close:
            self.on_close()

    def on_login(self, handset):
        print(f"Login: {handset.username}:{handset.password} @ {handset.service}")
        return 1 # okay
        return 0 # deny

    def on_login_complete(self, handset):
        self.handset = handset
        handset._buddy_in({"screenname":"i", "group":"Group"})

    def on_window_open(self, handset, buddy, with_ack, check = False):
        print(f"(H|{handset.id}) Open window (#{handset.window}) with buddy (#{buddy}), check: {check}")

        if self.on_ready:
            self.on_ready()

        return 1

    def on_window_close(self, handset):
        print(f"(H|{handset.id}) Close window (#{handset.window})")

        if self.on_close:
            self.on_close()

        return 1

    def on_data_in(self, data):
        print("[<] " + hexdump(data, end=""))


    def on_data_out(self, data):
        print("[>] " + hexdump(data, end=""))

    def send_im(self, message):
        self.message_queue.put_nowait(message)


class ProgramManager():
    def __init__(self, base):
        self.base = base
        self.shell = Shell(self)
        self.running_program = None
        self.shell_open = True
        self.programs = []

    def on_message(self, message):
        print(f"message: {message}")
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
        print(f"shell message: {message}")
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
        print("shell open")

    def list_handler(self, args):
        print("list")
        self.send_message(f"Programs: ({','.join([p.name() for p in self.manager.programs])})")

    def run_handler(self, args):
        print(f"run {args}")
        program = args[0]
        for p in self.manager.programs:
            if p.name() == program:
                self.manager.run_program(p)

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
        self.discord_interface = None

    def name(self):
        return "discord"

    def on_message(self, message):
        self.discord_interface.from_handset(message)

    def init(self):
        self.discord_interface = Discord.DiscordClient()
        self.discord_interface.init(self.send_message)

    def close(self):
        self.discord_interface.close()

    class DiscordClient(discord.Client):
        async def thread_start(self):
            await self.start(self.token)

        async def send_message_discord(self, message):
            print(f"sending \"{message}\"")
            try:
                await self.channel.send(message)
            except Exception as e:
                print(f"error: {e}")
            print("success")

        async def send_queue(self):
            while True:
                #print("queue check")
                try:
                    msg = self.message_queue.get_nowait()
                    await self.send_message_discord(msg)
                except asyncio.queues.QueueEmpty:
                    pass
                await asyncio.sleep(0.25)

        def run(self):
            self.discord_task = self.loop.create_task(self.thread_start())
            self.send_task = self.loop.create_task(self.send_queue())

        def init(self, send_message):
            self.channel_id = 660307462477578250
            self.token = "REDACTED"
            self.message_queue = asyncio.Queue()
            self.send_message_handset = send_message
            self.loop = asyncio.get_event_loop()
            self.run()

        def close(self):
            #self.loop.stop()
            #self.thread.join()
            self.send_task.cancel()
            self.discord_task.cancel()

        async def on_ready(self):
            message = f"logged in as {self.user}"
            print(message)
            self.channel = self.get_channel(self.channel_id)
            if not self.channel:
                raise Exception("Channel not found")
            self.send_message_handset(message)

        async def on_message(self, message):
            if message.author == self.user:
                return
            print(f"from discord: {message.content}")
            self.send_message_handset(f"<{message.author.display_name}>: {message.content}")

        def from_handset(self, message):
            #self.loop.create_task(self.send_message(message))
            self.message_queue.put_nowait(message)

def prog_echo(handset, message):
    print("echo invoke")
    handset._send_im(handset.window, message)

def prog_eval(handset, message):
    print("eval invoke")
    try:
        ret = eval(message).__repr__()
    except Exception as e:
        ret = str(e)
    handset._send_im(handset.window, ret)

def prog_discord(handset, message):
    print("discord invoke")
    #discord_interface.from_handset(message)

program_def = [
    ({"screenname": "Echo", "group": "Group"}, prog_echo),
    ({"screenname": "Eval", "group": "Group"}, prog_eval),
    ({"screenname": "Discord", "group": "Group"}, prog_discord)
]

def program_handler(handset, message):
    buddy = handset._locate_buddy_by_id(handset.window)
    if not buddy:
        return
    prog = buddy["screenname"]
    prog_func = None
    for b, f in program_def:
        if b["screenname"] == prog:
            prog_func = f
            break
    if prog_func:
        prog_func(handset, message)

# message len <= 36 works
# 37+ breaks

#hexdump([0x41, 0x41, 0x00, 0x11, 0x22, 0x33, 0x44])
#exit()

iface = HandsetInterface()
pmgr = ProgramManager(iface)

pmgr.register_program(Echo)
pmgr.register_program(Discord)

iface.on_message = pmgr.on_message
iface.on_ready = pmgr.on_ready
iface.on_close = pmgr.on_close

iface.start()
