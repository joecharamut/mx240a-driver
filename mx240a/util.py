import sys
from queue import Queue
from typing import Union


def as_bytes(string: str) -> bytes:
    """
    Convert a string to a bytes object containing ascii data

    :param string: string to encode as ascii
    :return: ascii bytes of string
    """
    if not isinstance(string, str):
        raise ValueError("string must be a str")
    return string.encode("ascii", "replace")


def to_hex(num: Union[int, bytes]) -> str:
    """
    Convert an int or bytes to a hex string representation

    :param num: int or bytes to convert
    :return: hex string
    """
    if isinstance(num, int):
        return "%.2x" % num
    elif isinstance(num, bytes):
        out = ""
        for b in num:
            out += "%.2x" % b
        return out
    else:
        raise ValueError("num must be one of (int, bytes)")


def hexdump(data: bytes, show_binary: bool = False) -> str:
    """
    Convert a bytes object to a hexdump-like string

    :param data: the bytes
    :param show_binary: whether to show binary of data or not
    :return: a representation of data in the format (hex bytes) [ascii representation] {optional binary}
    """

    if not isinstance(data, bytes):
        raise ValueError("data must be a bytes object")

    ascii_data = []
    for byte in data:
        # if printable ascii
        if 32 <= byte <= 127:
            ascii_data.append(chr(byte))
        else:
            ascii_data.append(".")

    hex_data = [to_hex(b) for b in data]
    output = "(%s)" % " ".join(hex_data + [".."] * (8 - len(hex_data)))
    output += " (%s)" % "".join(ascii_data)

    if show_binary:
        binary_data = []
        for byte in data:
            bits = ""
            for i in range(7, -1, -1):
                bits += str((byte >> i) & 1)
            binary_data.append(bits)
        output += " {%s}" % " ".join(binary_data)

    return output
