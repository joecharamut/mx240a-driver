from typing import Union

import mx240a
from mx240a import Ringtone


def log(msg: str) -> None:
    mx240a.logger.info(f"[TestService] {msg}")


class TestManager(mx240a.HandheldManager):
    def register_handheld(self, handheld_id: str) -> bool:
        log(f"register: handheld {handheld_id}")
        return True

    def connect_handheld(self, handheld_id: str) -> Union[mx240a.HandheldConnectData, None]:
        log(f"connect: handheld {handheld_id}")

        connect_data = mx240a.HandheldConnectData("Handheld#1")

        # Original driver default tones
        connect_data.tones.new_message = Ringtone("Dang:d=4,o=5,b=140:16g#5,16e5,16c#5"),  # aol-imrcv.txt
        connect_data.tones.contact_online = Ringtone("Rikasmiesjos:d=4,o=5,b=100:32b,32d6,32g6,32g6"),  # aol_ring.txt
        connect_data.tones.contact_offline = Ringtone("Bolero:d=4,o=5,b=80:c6"),  # bolero.txt
        connect_data.tones.message_sent = Ringtone("Dang:d=4,o=5,b=140:16b5,16e5,16g#5"),  # aol-imsend.txt
        connect_data.tones.service_disconnected = Ringtone("Dang:d=16,o=6,b=200:c,e,d7,c,e,a#,c,e"),  # aol_urgent.txt
        connect_data.tones.service_connected = Ringtone("Bulletme:d=4,o=5,b=112:b.5,g.5"),  # bulletme.txt
        connect_data.tones.out_of_range = Ringtone("Dang:d=4,o=5,b=140:4c,8g,8g,8a,4g,2b,c"),  # aol-outofrange.txt
        connect_data.tones.return_to_in_range = Ringtone("Dang:d=32,o=7,b=180:d#,e,g,d#,g,d#,f#,e"),  # aol_in_range.txt
        connect_data.tones.enter_sleep_mode = Ringtone("Dang:d=4,o=5,b=80:8e,8c,4f,4e,4d,4c"),  # aol_sleep.txt

        return connect_data


class TestService(mx240a.Service):
    @property
    def service_id(self) -> str:
        # noinspection SpellCheckingInspection
        return "AAAAAA"

    def login(self, handheld: mx240a.Handheld) -> bool:
        log(f"login: handheld {handheld.handheld_id} user '{handheld.username}' pass '{handheld.password}'")
        return True


if __name__ == "__main__":
    driver = mx240a.Driver(TestManager(), TestService())
    driver.loop()
