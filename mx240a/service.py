from abc import ABC, abstractmethod

import mx240a


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
    def connect_handheld(self, handheld_id: str) -> bool:
        """
        Called when a handheld is attempting to connect
        Intended for program to check whether the handheld is allowed to connect based on
            registration status and/or other conditions (ex: original driver had time restrictions)

        :param handheld_id: the id of the handheld
        :return: if the connection should be successful
        """
        # todo: return connect error instead of bool
        # todo: return tone data & handheld name
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
