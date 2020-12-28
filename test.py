import time
import os
import json
from typing import List, Tuple, Optional, Callable, Any, Dict
from threading import Thread
from queue import Queue

import tkinter as tk
from tkinter import messagebox, simpledialog
import discord
import asyncio

from newdriver import BaseStation, Handset, Buddy, debug as _debug, rtttl_to_bytes


def debug(data: Any) -> None:
    _debug(data, "TEST   ")


class DiscordInterface:
    client_thread: Optional[Thread]
    client_ready: bool

    selected_server: Optional[discord.Guild]
    selected_channel: Optional[discord.TextChannel]
    message_handler: Callable[[discord.Message], None]

    send_queue: Queue

    def __init__(self, ready_callback: Callable, message_handler: Callable[[discord.Message], None]) -> None:
        self.client = discord.Client()
        self.client_thread = None
        self.client_ready = False

        self.selected_server = None
        self.selected_channel = None

        self.ready_callback = ready_callback
        self.message_handler = message_handler

        self.send_queue = Queue()
        self.event_loop = asyncio.new_event_loop()

        self.client.event(self.on_message)
        self.client.event(self.on_ready)

    def init(self) -> None:
        asyncio.set_event_loop(self.event_loop)
        with open("self.token") as f:
            self.event_loop.create_task(self.client.start(f.read().strip(), bot=False))
        self.event_loop.create_task(self.send_loop_func())

        self.client_thread = Thread(target=self.event_loop.run_forever)
        self.client_thread.start()

        print("Logging in...")

    async def on_message(self, message: discord.Message):
        if message.author == self.client.user:
            return

        if self.selected_server and self.selected_channel:
            if message.channel == self.selected_channel:
                self.message_handler(message)
                debug("{} #{} <{}>: {}".format(message.guild, message.channel, message.author, message.clean_content))

    async def on_ready(self) -> None:
        self.client_ready = True
        self.ready_callback()
        debug("Discord bot logged in as: {} ({})".format(self.client.user.name, self.client.user.id))

    async def send_loop_func(self) -> None:
        while True:
            while not self.send_queue.empty():
                if self.selected_server and self.selected_channel:
                    await self.selected_channel.send(self.send_queue.get())
                    await asyncio.sleep(1)
            await asyncio.sleep(1)

    def close(self) -> None:
        asyncio.get_event_loop().create_task(self.client.close())
        self.client_thread.join()
        debug("Exiting...")

    def get_servers(self) -> List[Tuple[int, str]]:
        servers = [(0, "DM")]
        for i, server in enumerate(self.client.guilds):
            servers.append((i+1, server.name))

        debug("Available servers: " + servers.__repr__())
        return servers

    def get_channels(self) -> Optional[List[Tuple[int, str]]]:
        if not self.selected_server:
            return None

        channels = []
        for i, channel in enumerate([c for c in self.selected_server.channels if c.type is discord.ChannelType.text]):
            channels.append((i, "#"+channel.name))

        debug("Channels in server: " + channels.__repr__())
        return channels

    def select_server(self, index: int) -> bool:
        try:
            self.selected_server = self.client.guilds[index-1]
            debug("Selected server " + self.selected_server.name)
        except KeyError:
            return False
        return True

    def select_channel(self, index: int) -> bool:
        if not self.selected_server:
            return False
        try:
            self.selected_channel = [c for c in self.selected_server.channels
                                     if c.type is discord.ChannelType.text][index]
            debug("Selected channel " + self.selected_channel.name)
        except KeyError:
            return False
        return True

    def send_message(self, msg: str) -> None:
        if self.selected_server and self.selected_channel:
            self.send_queue.put(msg)


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


def write_data(new: dict) -> None:
    jsonfile = "data/data.json"
    with open(jsonfile, "w") as f:
        f.write(json.dumps(new))


def register_callback(handset_id: str) -> bool:
    root = tk.Tk()
    reg_ok = messagebox.askyesno("Registration", f"OK to register handset ID {handset_id}?")
    if reg_ok:
        name = simpledialog.askstring("Registration", "Enter a name for this handset.")
        root.destroy()

        data = read_data()
        data["handsets"][handset_id] = {"name": name}
        write_data(data)

        return True
    else:
        root.destroy()
        return False


def connect_callback(handset: Handset) -> Dict[str, Any]:
    data = read_data()
    connect_data = {
        "name": "IMFree",
        "tones": {
            # "newMessage": "FelizNav:d=8,o=5,b=140:a,4d6,c#6,d6,2b.,b,4e6,d6,b,2a."
            # "newMessage": "test:d=8,o=5,b=120:g,f,e,d,c",
        }
    }

    if handset.id in data["handsets"]:
        connect_data["name"] = data["handsets"][handset.id]["name"]

    return connect_data


def login_callback(handset: Handset) -> bool:
    data = read_data()

    if handset.id not in data["handsets"]:
        return True

    if "login" not in data["handsets"][handset.id]:
        data["handsets"][handset.id]["login"] = {
            "username": handset.username,
            "password": handset.password,
        }
        write_data(data)
        return True

    if data["handsets"][handset.id]["login"]["password"] == handset.password:
        return True

    return False


g_handset: Optional[Handset] = None


def discord_ready_callback() -> None:
    g_handset.send_message(1, f"Logged in as {client.client.user.name}")


def discord_message_callback(message) -> None:
    debug(message)


client = DiscordInterface(discord_ready_callback, discord_message_callback)


def post_login_callback(handset: Handset) -> None:
    handset.add_buddy(Buddy("Test"), "Group")
    global g_handset
    g_handset = handset
    handset.message_callback = echo
    # client.init()
    # g_handset.send_message(1, "Logging in...")


def echo(message: str) -> None:
    time.sleep(0.5)
    g_handset.send_message(1, message)


if __name__ == "__main__":
    # rttl_to_bytes(":d=32,o=5,b=900:p")
    # exit()
    b = BaseStation()

    b.register_callback = register_callback
    b.connect_callback = connect_callback
    b.login_callback = login_callback
    b.post_login_callback = post_login_callback

    try:
        b.open()
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        b.close()
