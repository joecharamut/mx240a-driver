import sys
from typing import List, Tuple, Optional, Callable
from threading import Thread
from queue import Queue

import discord
import asyncio
from loguru import logger


logger.remove()
logger.add(sys.stdout, level="DEBUG", format="[{time:HH:mm:ss}] [{level}] {message}",
           backtrace=True, diagnose=True, enqueue=True)


class DiscordInterface:
    client_thread: Optional[Thread]
    client_ready: bool

    selected_server: Optional[discord.Guild]
    selected_channel: Optional[discord.TextChannel]

    ready_callback: Optional[Callable[[], None]]
    message_callback: Optional[Callable[[discord.Message], None]]

    send_queue: Queue

    def __init__(self) -> None:
        self.client = discord.Client()
        self.client_thread = None
        self.client_ready = False

        self.selected_server = None
        self.selected_channel = None

        self.ready_callback = None
        self.message_callback = None

        self.send_queue = Queue()
        self.event_loop = asyncio.get_event_loop()

        self.client.event(self.on_message)
        self.client.event(self.on_ready)

    def init(self, token: str) -> None:
        # asyncio.set_event_loop(self.event_loop)
        self.event_loop.create_task(self.client.start(token, bot=False))
        self.event_loop.create_task(self.send_loop_func())

        self.client_thread = Thread(target=self.event_loop.run_forever)
        self.client_thread.start()

        logger.debug("Logging in to discord...")

    async def on_message(self, message: discord.Message):
        if message.author == self.client.user:
            return

        if self.selected_server and self.selected_channel and message.channel == self.selected_channel:
            if self.message_callback:
                self.message_callback(message)
            logger.debug("{} #{} <{}>: {}", message.guild, message.channel, message.author, message.clean_content)

    async def on_ready(self) -> None:
        self.client_ready = True
        logger.debug("Discord bot logged in as: {} ({})".format(self.client.user.name, self.client.user.id))
        if self.ready_callback:
            self.ready_callback()

    async def send_loop_func(self) -> None:
        while True:
            while not self.send_queue.empty():
                if self.selected_server and self.selected_channel:
                    await self.selected_channel.send(self.send_queue.get())
                    await asyncio.sleep(1)
            await asyncio.sleep(1)

    def close(self) -> None:
        asyncio.get_event_loop().create_task(self.client.close())
        if self.client_thread:
            self.client_thread.join()
        logger.debug("Exiting discord...")

    def get_servers(self) -> List[Tuple[int, str]]:
        servers = [(0, "DM")]
        for i, server in enumerate(self.client.guilds):
            servers.append((i+1, server.name))

        logger.debug("Available servers: " + servers.__repr__())
        return servers

    def get_channels(self) -> Optional[List[Tuple[int, str]]]:
        if not self.selected_server:
            return None

        channels = []
        for i, channel in enumerate([c for c in self.selected_server.channels if c.type is discord.ChannelType.text]):
            channels.append((i, "#"+channel.name))

        logger.debug("Channels in server: " + channels.__repr__())
        return channels

    def select_server(self, index: int) -> bool:
        try:
            self.selected_server = self.client.guilds[index-1]
            logger.debug("Selected server " + self.selected_server.name)
        except KeyError:
            return False
        return True

    def select_channel(self, index: int) -> bool:
        if not self.selected_server:
            return False
        try:
            self.selected_channel = [c for c in self.selected_server.channels
                                     if c.type is discord.ChannelType.text][index]
            logger.debug("Selected channel " + self.selected_channel.name)
        except KeyError:
            return False
        return True

    def send_message(self, msg: str) -> None:
        if self.selected_server and self.selected_channel:
            self.send_queue.put(msg)
