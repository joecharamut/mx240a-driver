from time import sleep
from typing import Optional, Dict, Any

import old_driver as driver
from old_driver import Handset, Window, BaseStation, Buddy


class Echo:
    base: BaseStation
    handset: Optional[Handset]
    current_window: Optional[Window]

    def __init__(self) -> None:
        driver.set_log_level("TRACE")
        # driver.set_log_level("DEBUG")

        self.exit = False

        self.base = base = BaseStation()

        # setup some hooks
        base.register_callback = Echo.register_callback
        base.connect_callback = Echo.connect_callback
        base.disconnect_callback = self.disconnect_callback
        base.login_callback = Echo.login_callback
        base.post_login_callback = self.post_login_callback

        self.handset = None
        self.current_window = None

    def run(self) -> None:
        # lets go
        try:
            self.base.open()
            # idle to keep main thread active
            while not self.exit:
                sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.base.close()

    @staticmethod
    def register_callback(handset_id: str) -> bool:
        print("Registering Handset ID " + handset_id)
        return True

    @staticmethod
    def connect_callback(handset: Handset) -> Dict[str, Any]:
        return {
            "name": "IMFree",
            "tones": {},
        }

    def disconnect_callback(self, handset: Handset) -> None:
        self.exit = True

    @staticmethod
    def login_callback(handset: Handset) -> bool:
        print(f"Handset logging in with username '{handset.username}' and password '{handset.password}'")
        return True

    def post_login_callback(self, handset: Handset) -> None:
        handset.add_buddy(Buddy("Echo"), "Group")
        self.handset = handset

        handset.window_open_callback = self.window_open_callback
        handset.window_close_callback = self.window_close_callback
        handset.message_callback = self.message_callback

    def window_open_callback(self, window: Window) -> None:
        self.current_window = window

    def window_close_callback(self, window: Window) -> None:
        self.current_window = None

    def message_callback(self, message: str) -> None:
        self.current_window.send_message(message)


if __name__ == "__main__":
    Echo().run()
