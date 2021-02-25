import time
import os
import json
from typing import Optional, Any, Dict, List, Tuple, Callable, Union
import re
from threading import Thread
from queue import Queue
import functools

import tkinter as tk
from tkinter import messagebox, simpledialog
import discord
from discord import Client, ChannelType
import asyncio
import emoji

from old_driver import Window, BaseStation, Handset, Buddy, logger, set_log_level


class PrivateChannelWrapper:
    _wrapped_channel: discord.abc.PrivateChannel

    def __init__(self, obj: discord.abc.PrivateChannel) -> None:
        self._wrapped_channel = obj

    @property
    def name(self) -> str:
        if isinstance(self._wrapped_channel, discord.GroupChannel):
            return str(self._wrapped_channel.name)  # some are None for whatever reason
        elif isinstance(self._wrapped_channel, discord.DMChannel):
            return self._wrapped_channel.recipient.name
        else:
            assert False

    def __getattr__(self, attr: Any) -> Any:
        return getattr(self._wrapped_channel, attr)


class DMServer:
    client: Client
    channels: List[PrivateChannelWrapper]
    name: str

    def __init__(self, client: discord.Client) -> None:
        self.client = client
        self.name = "DM"
        self.channels = [PrivateChannelWrapper(c) for c in self.client.private_channels]


class DiscordInterface:
    client_thread: Optional[Thread]
    client_task: Optional[asyncio.Task]

    ready_callback: Optional[Callable[[], None]]

    send_queue: Queue
    send_thread_flag: bool

    def __init__(self) -> None:
        self.client = discord.Client()
        self.client_thread = None
        self.client_task = None

        self.ready_callback = None
        self.message_callback = None

        self.send_queue = Queue()
        self.send_thread_flag = False
        self.sent_messages = []
        self.event_loop = asyncio.get_event_loop()

        self.started = False
        self.logged_in = False

        self.client.event(self.on_ready)

    def start(self, token: str, bot: bool = True) -> None:
        if not self.started:
            self.started = True
            self.client_task = self.event_loop.create_task(self.client.start(token, bot=bot))
            self.event_loop.create_task(self.send_loop_func())

            self.client_thread = Thread(target=self.event_loop.run_forever)
            self.client_thread.start()

            logger.debug("Logging in to discord...")

    def event(self, func: Callable, event_name: str):
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("event registered must be a coroutine function")
        setattr(self.client, event_name, func)

    async def on_ready(self) -> None:
        self.logged_in = True
        logger.debug(f"Logged in as: {self.client.user.name} ({self.client.user.id})")
        if self.ready_callback:
            self.ready_callback()

    async def send_loop_func(self) -> None:
        while not self.send_thread_flag:
            while not self.send_queue.empty():
                channel: discord.TextChannel
                channel, message = self.send_queue.get()
                message_id = await channel.send(message)
                self.sent_messages.append(message_id)
                if len(self.sent_messages) > 8:
                    self.sent_messages.remove(0)
                await asyncio.sleep(0.5)
            await asyncio.sleep(1)

    def close(self) -> None:
        if self.client_thread and self.client_thread.is_alive():
            self.logged_in = False
            logger.debug("Exiting discord thread")
            self.send_thread_flag = True
            self.client_task.cancel()
            asyncio.ensure_future(self.client.close(), loop=self.client.loop)
            self.event_loop.stop()
            self.client_thread.join()

    def get_server_list(self) -> List[Tuple[int, str, Union[discord.Guild, DMServer]]]:
        servers = [(0, "DM", DMServer(self.client))]
        for i, guild in enumerate(self.client.guilds):
            servers.append((i+1, guild.name, guild))
        return servers

    # noinspection PyMethodMayBeStatic
    def get_channel_list(self, server: Union[discord.Guild, DMServer]) -> \
            Optional[List[Tuple[int, str, discord.TextChannel]]]:
        channels = []
        for i, channel in enumerate([c for c in server.channels
                                     if c.type in [ChannelType.text, ChannelType.private, ChannelType.group]]):
            if channel.type is ChannelType.text:
                channels.append((i, "#"+channel.name, channel))
            else:
                channels.append((i, channel.name, channel))

        logger.debug("Channels in server: " + channels.__repr__())
        return channels

    # noinspection PyMethodMayBeStatic
    def get_channel(self, server: Union[discord.Guild, DMServer], index: int) -> Optional[discord.TextChannel]:
        try:
            return [c for c in server.channels
                    if c.type in [ChannelType.text, ChannelType.private, ChannelType.group]][index]
        except KeyError:
            return None

    def send_message(self, channel: discord.TextChannel, message: str) -> None:
        logger.debug("Sending message '{}' to channel '{}' in server '{}'", message, channel.name, channel.guild.name)
        self.send_queue.put((channel, message))


def event(name: str):
    def decorator(function) -> Any:
        if not asyncio.iscoroutinefunction(function):
            raise TypeError("Wrapped function is not a coroutine")
        function.event_name = name

        @functools.wraps(function)
        async def wrapper(self, *args) -> Any:
            return await function(self, *args)
        return wrapper
    return decorator


class IMDiscord:
    selected_channel: Optional[discord.TextChannel]
    selected_server: Optional[Union[discord.Guild, DMServer]]
    running: bool
    first_open: bool
    console_id: Optional[int]
    base: BaseStation
    discord_client: DiscordInterface
    handset: Optional[Handset]
    current_window: Optional[Window]

    def __init__(self) -> None:
        # enable trace logging
        set_log_level("TRACE")

        self.base = base = BaseStation()

        # setup some hooks
        base.register_callback = IMDiscord.register_callback
        base.connect_callback = IMDiscord.connect_callback
        base.login_callback = IMDiscord.login_callback
        base.disconnect_callback = self.disconnect_callback
        base.post_login_callback = self.post_login_callback

        self.discord_client = client = DiscordInterface()
        client.ready_callback = self.discord_ready_callback
        client.message_callback = self.discord_message_callback

        self.handset = None
        self.current_window = None
        self.console_id = None
        self.first_open = True
        self.running = True
        self.selected_server = None
        self.selected_channel = None

    def run(self) -> None:
        # lets go
        try:
            self.base.open()
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.discord_client.close()
            self.base.close()

    @staticmethod
    def read_data() -> dict:
        if not os.path.exists("data"):
            os.mkdir("data")

        registered = {"handsets": {}}
        jsonfile = "data/data.json"
        if not os.path.exists(jsonfile):
            with open(jsonfile, "w") as f:
                f.write(json.dumps(registered))

        with open(jsonfile) as f:
            registered = json.loads(f.read())

        return registered

    @staticmethod
    def write_data(new: dict) -> None:
        jsonfile = "data/data.json"
        with open(jsonfile, "w") as f:
            f.write(json.dumps(new))

    @staticmethod
    def register_callback(handset_id: str) -> bool:
        root = tk.Tk()
        reg_ok = messagebox.askyesno("Registration", f"OK to register handset ID {handset_id}?")
        if reg_ok:
            name = simpledialog.askstring("Registration", "Enter a name for this handset.")
            root.destroy()

            data = IMDiscord.read_data()
            data["handsets"][handset_id] = {"name": name}
            IMDiscord.write_data(data)

            return True
        else:
            root.destroy()
            return False

    @staticmethod
    def connect_callback(handset: Handset) -> Dict[str, Any]:
        data = IMDiscord.read_data()
        connect_data = {
            "name": "IMFree",
            "tones": {},
        }

        if handset.id in data["handsets"]:
            connect_data["name"] = data["handsets"][handset.id]["name"]

        return connect_data

    def disconnect_callback(self, handset: Handset) -> None:
        logger.debug(handset)
        self.discord_client.close()
        self.running = False

    @staticmethod
    def login_callback(handset: Handset) -> bool:
        data = IMDiscord.read_data()

        if handset.id not in data["handsets"]:
            return True

        if "login" not in data["handsets"][handset.id]:
            data["handsets"][handset.id]["login"] = {
                "username": handset.username,
                "password": handset.password,
            }
            IMDiscord.write_data(data)
            return True

        if data["handsets"][handset.id]["login"]["password"] == handset.password:
            return True

        return False

    def post_login_callback(self, handset: Handset) -> None:
        self.console_id = handset.add_buddy(Buddy("Test"), "Group")
        self.handset = handset

        handset.window_open_callback = self.window_open_callback
        handset.window_close_callback = self.window_close_callback
        handset.message_callback = self.message_callback

    def window_open_callback(self, window: Window) -> None:
        self.current_window = window
        if self.first_open and window.window_id == self.console_id:
            self.first_open = False
            window.send_message("Welcome to IMDiscord\nTo login send /login")

    def window_close_callback(self, window: Window) -> None:
        ...

    def message_callback(self, message: str) -> None:
        if message[0] == "/":
            self.process_command(message[1:])
        elif self.current_window.window_id == self.console_id:
            logger.debug("Ignoring msg to console: {}", message)
        else:
            self.discord_client.send_message(self.selected_channel, emoji.emojize(message, use_aliases=True))

    def process_command(self, message: str) -> None:
        parts = message.split(" ")
        cmd = parts[0]
        args = parts[1:]

        commands: Dict[str, Callable[[List[str]], None]] = {
            "login": self.cmd_login,
            "logout": self.cmd_logout,
            "server": self.cmd_server,
            "s": self.cmd_server,
            "channel": self.cmd_channel,
            "c": self.cmd_channel,
            "test": self.cmd_test,
        }

        if cmd in commands:
            commands[cmd](args)
        else:
            self.current_window.send_message(f"Unknown Command: {cmd}")

    def cmd_test(self, args: List[str]) -> None:
        self.current_window = self.handset.new_group()
        self.current_window.send_message("Welcome to test mode", "TEST")

        def test_fn() -> None:
            for i in range(0, 128):
                self.current_window.send_message(f"chr {i}: | {chr(i)} |", f"| {chr(i)} |")
                time.sleep(1)

        Thread(target=test_fn).start()

    def cmd_login(self, args: List[str]) -> None:
        self.current_window.send_message("Logging in...")

        for func in [getattr(self, f) for f in dir(self) if callable(getattr(self, f))]:
            if hasattr(func, "event_name"):
                self.discord_client.event(func, func.event_name)

        with open("data/self.token") as f:
            self.discord_client.start(f.read().strip(), bot=False)

    def cmd_logout(self, args: List[str]) -> None:
        self.discord_client.close()

    def cmd_server(self, args: List[str]) -> None:
        if not self.discord_client.logged_in:
            self.current_window.send_message("Err: Not logged in")
            return

        if args[0].isdigit():
            i = int(args[0])
            num, name, self.selected_server = self.discord_client.get_server_list()[i]
            self.current_window.send_message(f"Selected server: {name}")
        else:
            search = " ".join(args)
            results = []
            for i, name, _ in self.discord_client.get_server_list():
                if search in name:
                    results.append((i, name))
            if len(results) == 0:
                self.current_window.send_message("No Results")
            for result in results:
                self.current_window.send_message(f"({result[0]}): {result[1]}")

    def cmd_channel(self, args: List[str]) -> None:
        if not self.discord_client.logged_in:
            self.current_window.send_message("Err: Not logged in")
            return

        if not self.selected_server:
            self.current_window.send_message("Err: No server selected")
            return

        if args[0].isdigit():
            i = int(args[0])
            self.current_window = self.handset.new_group()
            num, name, self.selected_channel = self.discord_client.get_channel_list(self.selected_server)[i]
            self.current_window.send_message(f"Joined Channel {name}")
        else:
            search = " ".join(args)
            results = []
            for i, name, _ in self.discord_client.get_channel_list(self.selected_server):
                if search in name:
                    results.append((i, name))
            if len(results) == 0:
                self.current_window.send_message("No Results")
            for result in results:
                self.current_window.send_message(f"({result[0]}): {result[1]}")

    def discord_ready_callback(self) -> None:
        self.current_window.send_message(f"Logged in as {self.discord_client.client.user.name}")

    @event("on_message")
    async def discord_message_callback(self, message: discord.Message) -> None:
        if message.author == self.discord_client.client.user:
            return
        if message.channel != self.selected_channel:
            return

        logger.debug("{} #{} <{}>: {}", message.guild, message.channel, message.author, message.clean_content)
        message_text = message.clean_content

        # encode emojis
        message_text = re.sub(R"<(a?:[a-zA-Z0-9-_]+:)\d{18}>", R" \1", message_text)
        message_text = emoji.demojize(message_text)

        message_author = message.author.display_name.replace(":", "")
        self.current_window.send_message(message_text, message_author)


if __name__ == "__main__":
    IMDiscord().run()
