from abc import ABC, abstractmethod
from typing import Union, Optional, Dict

import mx240a


class HandheldConnectData:
    handheld_name: str
    tones: "_Ringtones"

    class _Ringtones:
        """
        Helper class to store the ringtones by name
        """

        new_message: Optional[mx240a.Ringtone]
        contact_online: Optional[mx240a.Ringtone]
        contact_offline: Optional[mx240a.Ringtone]
        message_sent: Optional[mx240a.Ringtone]
        service_disconnected: Optional[mx240a.Ringtone]
        service_connected: Optional[mx240a.Ringtone]
        out_of_range: Optional[mx240a.Ringtone]
        return_to_in_range: Optional[mx240a.Ringtone]
        enter_sleep_mode: Optional[mx240a.Ringtone]

        def __init__(self) -> None:
            self.new_message = None
            self.contact_online = None
            self.contact_offline = None
            self.message_sent = None
            self.service_disconnected = None
            self.service_connected = None
            self.out_of_range = None
            self.return_to_in_range = None
            self.enter_sleep_mode = None

        def as_dict(self) -> Dict[str, Optional[mx240a.Ringtone]]:
            return {
                "new_message": self.new_message,
                "contact_online": self.contact_online,
                "contact_offline": self.contact_offline,
                "message_sent": self.message_sent,
                "service_disconnected": self.service_disconnected,
                "service_connected": self.service_connected,
                "out_of_range": self.out_of_range,
                "return_to_in_range": self.return_to_in_range,
                "enter_sleep_mode": self.enter_sleep_mode,
            }

    def __init__(self, handheld_name: str) -> None:
        self.handheld_name = handheld_name
        self.tones = self._Ringtones()


class HandheldManagerService(ABC):
    def init(self) -> None:
        ...

    @abstractmethod
    def register_handheld(self, handheld_id: str) -> bool:
        """
        Called when a user is attempting to register a new handheld

        :param handheld_id: the id of the handheld
        :return: if the registration is accepted
        """
        raise NotImplementedError

    @abstractmethod
    def connect_handheld(self, handheld_id: str) -> Union[HandheldConnectData, None]:
        """
        Called when a handheld is attempting to connect
        Intended for program to check whether the handheld is allowed to connect based on
            registration status and/or other conditions (ex: original driver had time restrictions)

        :param handheld_id: the id of the handheld
        :return: if the connection should be successful
        """
        # todo: return connect error instead of none
        raise NotImplementedError


class Service(ABC):
    def __init__(self) -> None:
        ...

    @property
    def service_id(self) -> str:
        """
        Service ID of this service
        Note: The second character must be "A", "a", or "M"

        :return: the service id
        """
        return " AIM  "

    @abstractmethod
    def handheld_login(self, handheld: mx240a.Handheld) -> bool:
        """
        Called when a handheld attempts to login

        :param handheld: the handheld
        :return: if the login is successful
        """
        # todo: return login error instead of bool
        raise NotImplementedError
