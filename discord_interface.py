import sys
from asyncio import Task
from typing import List, Tuple, Optional, Callable, Union, Any
from threading import Thread
from queue import Queue

import discord
import asyncio

from discord import Client, ChannelType
from loguru import logger


logger.remove()
logger.add(sys.stdout, level="DEBUG", format="[{time:HH:mm:ss}] [{level}] {message}",
           backtrace=True, diagnose=True, enqueue=True)


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
    client_task: Optional[Task]

    selected_server: Optional[Union[discord.Guild, DMServer]]
    selected_channel: Optional[discord.TextChannel]

    ready_callback: Optional[Callable[[], None]]
    message_callback: Optional[Callable[[discord.Message], None]]

    send_queue: Queue
    send_thread_flag: bool

    def __init__(self) -> None:
        self.client = discord.Client()
        self.client_thread = None
        self.client_task = None

        self.selected_server = None
        self.selected_channel = None

        self.ready_callback = None
        self.message_callback = None

        self.send_queue = Queue()
        self.send_thread_flag = False
        self.event_loop = asyncio.get_event_loop()

        self.client.event(self.on_message)
        self.client.event(self.on_ready)

    def init(self, token: str) -> None:
        # asyncio.set_event_loop(self.event_loop)
        self.client_task = self.event_loop.create_task(self.client.start(token, bot=False))
        self.event_loop.create_task(self.send_loop_func())

        self.client_thread = Thread(target=self.event_loop.run_forever)
        self.client_thread.start()

        logger.debug("Logging in to discord...")

    async def on_message(self, message: discord.Message):
        if message.author == self.client.user:
            return

        if self.selected_channel and self.selected_channel.id == message.channel.id:
            if self.message_callback:
                self.message_callback(message)
            logger.debug("{} #{} <{}>: {}", message.guild, message.channel, message.author, message.clean_content)

    async def on_ready(self) -> None:
        logger.debug("Discord bot logged in as: {} ({})".format(self.client.user.name, self.client.user.id))
        if self.ready_callback:
            self.ready_callback()

    async def send_loop_func(self) -> None:
        while not self.send_thread_flag:
            while not self.send_queue.empty():
                if self.selected_server and self.selected_channel:
                    await self.selected_channel.send(self.send_queue.get())
                    await asyncio.sleep(1)
            await asyncio.sleep(1)

    def close(self) -> None:
        if self.client_thread and self.client_thread.is_alive():
            logger.debug("Exiting discord thread")
            self.send_thread_flag = True
            self.client_task.cancel()
            asyncio.ensure_future(self.client.close())
            self.event_loop.stop()
            self.client_thread.join()

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
        for i, channel in enumerate([c for c in self.selected_server.channels
                                     if c.type in [ChannelType.text, ChannelType.private, ChannelType.group]]):
            if channel.type is ChannelType.text:
                channels.append((i, "#"+channel.name))
            else:
                channels.append((i, channel.name))

        logger.debug("Channels in server: " + channels.__repr__())
        return channels

    def select_server(self, index: int) -> bool:
        if index == 0:
            self.selected_server = DMServer(self.client)
        else:
            try:
                self.selected_server = self.client.guilds[index-1]
            except KeyError:
                return False
        logger.debug("Selected server " + self.selected_server.name)
        return True

    def select_channel(self, index: int) -> bool:
        if not self.selected_server:
            return False
        try:
            self.selected_channel = [c for c in self.selected_server.channels
                                     if c.type in [ChannelType.text, ChannelType.private, ChannelType.group]][index]
            logger.debug("Selected channel " + self.selected_channel.name)
        except KeyError:
            return False
        return True

    def send_message(self, msg: str) -> None:
        if self.selected_server and self.selected_channel:
            self.send_queue.put(msg)
