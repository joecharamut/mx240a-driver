import sys


class FallbackLogger:
    # stub
    def remove(self, *args, **kwargs) -> None:
        pass

    # stub
    def add(self, *args, **kwargs) -> None:
        pass

    def trace(self, msg: str, *args) -> None:
        print("[TRACE]", msg.format(*args))

    def debug(self, msg: str, *args) -> None:
        print("[DEBUG]", msg.format(*args))

    def info(self, msg: str, *args) -> None:
        print("[INFO]", msg.format(*args))

    def warning(self, msg: str, *args) -> None:
        print("[WARN]", msg.format(*args))

    def error(self, msg: str, *args) -> None:
        print("[ERROR]", msg.format(*args))


try:
    from loguru import logger
except ImportError:
    logger = FallbackLogger()


def set_log_level(level: str) -> None:
    logger.remove()
    if level == "TRACE" or level == "DEBUG":
        logger.add(sys.stdout, level=level, format="[{elapsed}] [{level}] {message}",
                   backtrace=True, diagnose=True, enqueue=True)
    else:
        logger.add(sys.stdout, level=level, format="[{time:HH:mm:ss}] [{level}] {message}",
                   backtrace=True, diagnose=True, enqueue=True)


# todo: make this not a constant
set_log_level("TRACE")

