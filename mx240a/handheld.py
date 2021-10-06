from typing import Optional, Dict, List

import mx240a


class Buddy:
    name: str
    buddy_id: int
    group: str
    status: str

    def __init__(self, name: str, group: str = "Group") -> None:
        self.name = name
        self.group = group[0:6].ljust(6, " ")

        self._status_idle = False
        self._status_mobile = False

    @property
    def status(self) -> str:
        status_str = ""

        if self._status_idle:
            status_str += "I"
        else:
            status_str += "A"

        if self._status_mobile:
            status_str += "Y"
        else:
            status_str += "N"

        status_str += "N"
        return status_str

    def set_status(self, *, idle: Optional[bool] = None, mobile: Optional[bool] = None):
        if idle is not None:
            self._status_idle = idle

        if mobile is not None:
            self._status_mobile = mobile

    def __repr__(self) -> str:
        return "<Buddy id: {} name: {} status: (Idle: {} Mobile: {})>".format(
            self.buddy_id,
            self.name,
            self._status_idle,
            self._status_mobile
        )


class Window:
    pass


class Handheld:
    driver: "mx240a.Driver"
    connection_id: int
    handheld_id: str

    username: Optional[str]
    password: Optional[str]

    next_buddy_id: int
    buddy_list: Dict[str, List[Buddy]]

    def __init__(self, driver: "mx240a.Driver", connection_id: int, handheld_id: str) -> None:
        self.driver = driver
        self.connection_id = connection_id
        self.handheld_id = handheld_id

        self.username = None
        self.password = None

        self.next_buddy_id = 1
        self.buddy_list = {}

    def add_buddy(self, buddy: Buddy) -> int:
        group = buddy.group
        if group not in self.buddy_list.keys():
            self.buddy_list[group] = []
        self.buddy_list[group].append(buddy)

        buddy.buddy_id = self.next_buddy_id
        self.next_buddy_id += 1

        self.driver.send_buddy_info(self.connection_id, buddy)
        return buddy.buddy_id

    def __repr__(self) -> str:
        return "<Handheld id: {} connection: {}>".format(self.handheld_id, self.connection_id)
