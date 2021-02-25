from typing import Optional

import mx240a


class Handheld:
    driver: "mx240a.Driver"
    connection_id: int
    handheld_id: str

    username: Optional[str]
    password: Optional[str]

    def __init__(self, driver: "mx240a.Driver", connection_id: int, handheld_id: str) -> None:
        self.driver = driver
        self.connection_id = connection_id
        self.handheld_id = handheld_id

        self.username = None
        self.password = None

