import time
import os
import json
from typing import Optional, Any, Dict
import re

import tkinter as tk
from tkinter import messagebox, simpledialog

from driver import Window, BaseStation, Handset, Buddy, logger, set_log_level
from discord_interface import DiscordInterface
import discord


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


class IMDiscord:
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
        self.first_open = True
        self.running = True

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

    @staticmethod
    def connect_callback(handset: Handset) -> Dict[str, Any]:
        data = read_data()
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

    def post_login_callback(self, handset: Handset) -> None:
        handset.add_buddy(Buddy("Test"), "Group")
        self.handset = handset

        handset.window_open_callback = self.window_open_callback
        handset.window_close_callback = self.window_close_callback
        handset.message_callback = self.message_callback
        # client.init()

    def window_open_callback(self, window: Window) -> None:
        self.current_window = window
        if self.first_open:
            self.first_open = False
            window.send_message("Welcome to IMDiscord")
            window.send_message("To login send /login")

    def window_close_callback(self, window: Window) -> None:
        ...

    def message_callback(self, message: str) -> None:
        if message[0] == "/":
            self.process_command(message[1:])
        else:
            self.discord_client.send_message(message)

    def process_command(self, message: str) -> None:
        parts = message.split(" ")
        cmd = parts[0]

        if cmd == "login":
            self.current_window.send_message("Logging in...")
            with open("data/self.token") as f:
                self.discord_client.init(f.read().strip())
        elif cmd == "server" or cmd == "s":
            if parts[1].isdigit():
                i = int(parts[1])
                logger.debug(i.__repr__())
                self.discord_client.select_server(i)
                self.current_window.send_message(f"Selected server: {self.discord_client.get_servers()[i][1]}")
            else:
                search = " ".join(parts[1:])
                results = []
                for i, name in self.discord_client.get_servers():
                    if search in name:
                        results.append((i, name))
                if len(results) == 0:
                    self.current_window.send_message("No Results")
                for result in results:
                    self.current_window.send_message(f"({result[0]}): {result[1]}")
        elif cmd == "channel" or cmd == "c":
            if parts[1].isdigit():
                i = int(parts[1])
                self.current_window = self.handset.new_group()
                self.discord_client.select_channel(i)
                self.current_window.send_message(f"Joined Channel {self.discord_client.get_channels()[i][1]}", "Driver")
            else:
                search = " ".join(parts[1:])
                results = []
                for i, name in self.discord_client.get_channels():
                    if search in name:
                        results.append((i, name))
                if len(results) == 0:
                    self.current_window.send_message("No Results")
                for result in results:
                    self.current_window.send_message(f"({result[0]}): {result[1]}")
        else:
            self.current_window.send_message(f"Unknown Command: {cmd}")

    def discord_ready_callback(self) -> None:
        self.current_window.send_message(f"Logged in as {self.discord_client.client.user.name}")

    def discord_message_callback(self, message: discord.Message) -> None:
        message_text = message.clean_content

        # encode emojis
        message_text = re.sub(R"<(:[a-zA-Z0-9-_]+:)\d{18}>", R" \1", message_text)

        message_author = message.author.display_name.replace(":", "")
        self.current_window.send_message(message_text, message_author)


if __name__ == "__main__":
    IMDiscord().run()
