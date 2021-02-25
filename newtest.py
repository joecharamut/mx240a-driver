import mx240a


def log(msg: str) -> None:
    mx240a.logger.info(f"[TestService] {msg}")


class TestService(mx240a.Service):
    @property
    def service_id(self) -> str:
        # noinspection SpellCheckingInspection
        return "dAscor"

    def register_handheld(self, handheld_id: str) -> bool:
        log(f"register: handheld {handheld_id}")
        return True

    def handheld_login(self, handheld: mx240a.Handheld) -> bool:
        log(f"login: handheld {handheld.handheld_id} user '{handheld.username}' pass '{handheld.password}'")
        return True


if __name__ == "__main__":
    driver = mx240a.Driver(TestService())
    driver.loop()
