import struct
import re
import random
import time
import hid

def has_key(dict, key):
    if key in dict.keys():
        return True
    return False

_hex = hex
def hex(val):
    if isinstance(val, str):
        return int(val, 16)
    else:
        return _hex(val)[2:]

def as_bytes(str):
    if isinstance(str, bytes):
        return str
    return str.encode("ascii")

def hexdump(hexarr, end="\n"):
    if isinstance(hexarr[0], str):
        hexarr = [hex(v) for v in hexarr]
    bytes = []
    repr = []
    for h in hexarr:
        bytes.append(h)
        if h >= 32 and h <= 127:
            repr.append(chr(h))
        else:
            repr.append(".")

    out = ""
    max = len(bytes)
    out += "(%s %s %s %s %s %s %s %s %s %s %s %s) [%s%s%s%s%s%s%s%s%s%s%s%s]" % (
        "%.2x" % bytes[0] if max > 0 else "..",
        "%.2x" % bytes[1] if max > 1 else "..",
        "%.2x" % bytes[2] if max > 2 else "..",
        "%.2x" % bytes[3] if max > 3 else "..",
        "%.2x" % bytes[4] if max > 4 else "..",
        "%.2x" % bytes[5] if max > 5 else "..",
        "%.2x" % bytes[6] if max > 6 else "..",
        "%.2x" % bytes[7] if max > 7 else "..",
        "%.2x" % bytes[8] if max > 8 else "..",
        "%.2x" % bytes[9] if max > 9 else "..",
        "%.2x" % bytes[10] if max > 10 else "..",
        "%.2x" % bytes[11] if max > 11 else "..",

        repr[0] if max > 0 else ".",
        repr[1] if max > 1 else ".",
        repr[2] if max > 2 else ".",
        repr[3] if max > 3 else ".",
        repr[4] if max > 4 else ".",
        repr[5] if max > 5 else ".",
        repr[6] if max > 6 else ".",
        repr[7] if max > 7 else ".",
        repr[8] if max > 8 else ".",
        repr[9] if max > 9 else ".",
        repr[10] if max > 10 else ".",
        repr[11] if max > 11 else ".",
    )
    out += end
    return out

class Handset:
    def __init__(self, id, base):
        self.id = int(id, 16)
        self.base = base

        self.service = None
        self.username = None
        self.password = None
        self.window = None
        self.blist = {}

    def _set_service(self, service):
        self.service = service

    def _set_username(self, username):
        self.username = username

    def _set_password(self, password):
        self.password = password

    def _set_window(self, window):
        self.window = window

    def _buddy_in(self, buddy):
        if has_key(self.blist, buddy["screenname"]):
            buddy["id"] = self.blist[buddy["screenname"]]["id"]
        else:
            buddy["id"] = len(self.blist.keys()) + 1
        self.blist[buddy["screenname"]] = buddy
        return self.base._send_buddy_in(self, buddy)

    def _locate_buddy_by_id(self, id: int):
        for b in self.blist.values():
            if b["id"] == id:
                return b
        return None

    def _locate_id_by_buddy(self, screenname):
        if has_key(self.blist, screenname):
            return self.blist[screenname]
        return None

    def _close_window(self):
        self.window = None
        return None

    def _send_im(self, window, msg):
        bid = struct.pack("BB", hex("8" + str(self.id)), window)
        send = b"\x00" + as_bytes(msg) + b"\xff\x00"
        send = bid + bid.join([send[i:i + 22] for i in range(0, len(send), 22)])
        if not self.base.write(send):
            return None
        if not self.base.write(struct.pack("BBB", hex("e" + str(self.id)), 0xce, window)):
            return None
        return 1

    def _range_error(self, error = "aaa"):
        return self.base.write(struct.pack("BB", hex("c" + str(self.id)), 0xc5))

class MX240a:
    MX240A_VENDOR = 0x22b8
    MX240A_DEVICE = 0x7f01
    READ_SIZE = 16
    WRITE_SIZE = 16

    def __init__(self):
        # REGISTRY
        self.handle = None
        self.data_in = None
        self.handsets = {}
        self._on_data_in = None
        self._on_data_out = None
        self._on_im = None
        self._on_registration = None
        self._on_connect = None
        self._on_login = None
        self._on_login_complete = None
        self._on_window_open = None
        self._on_window_close = None
        self._on_disconnect = None
        self.buff_data = None
        self.last_sent = None

        self._handle = None

        self.id_dispatch = {
            "a": self.id_dispatch_a,
            "c": self.id_dispatch_c,
            "d": self.id_dispatch_d,
            "e": self.id_dispatch_e,
            "f": self.id_dispatch_f,
            "8": self.id_dispatch_8
        }

        # new
        handle = self._open()
        if not handle:
            print("no handle")
            return
        self.handle = handle
        self.data_in = ""
        if self._init_USB:
            self._init_USB()

    def ACK(self, expect_NAK = False):
        if not self.write(struct.pack("BB", 0xad, 0xff), 1):
            return
        if expect_NAK:
            self.read()
        return 1

    def _get_handset(self, num):
        try:
            handset = self.handsets[num]
        except KeyError:
            handset = Handset(num, self)
            self.handsets[num] = handset
        return handset

    def id_dispatch_a(self, num, func):
        handset = self._get_handset(num)
        self._read_IM(handset)

    def id_dispatch_c(self, num, func):
        handset = self._get_handset(num)
        # same as d, but for NAK

    def id_dispatch_d(self, num, func):
        # address handset N (recv message, partial)
        handset = self._get_handset(num)
        self._read_IM(handset)

    def id_dispatch_e(self, num, func):
        # "administration"/chat/extra functionality
        handset = self._get_handset(num)
        if num == "8":
            # init base ACK?
            self.ACK(1)
        elif num == "c" or num == "0":
            # someone's trying to register
            self.write(struct.pack("BB", 0xee, 0xd3)) # reg: we like you!
            # self.write(struct.pack("BB", 0xee, 0xc5)) # reg: ...rejected!
            return 1
        elif num == "f":
            print("init?")
        elif num == "1":
            print("???")
        else:
            self.id_dispatch["f"](num, func, True)

    def id_dispatch_f(self, num, func, nak = False):
        # address handset N (recv message, complete)
        handset = self._get_handset(num)
        data_str = b"".join([b"%c" % b for b in self.data_in])
        if "fd" == func:
            # ACK?
            if nak:
                self.write(self.last_sent)
            #print("FD!!!!!")
            #print(hex(self.buff_data[0]))
            if hex(self.buff_data[0]) == 2 or hex(self.buff_data[0] == 1):
                self.ACK(0)
        elif "69" == func:
            self.ACK(1)
        elif "8c" == func:
            if not self.buff_data[0]:
                self.ACK(1)
            elif hex(self.buff_data[0]) == 0xff:#0xc1:
                # handset shut down?
                # testing
                #exit()
                #print(f"handset {handset.id} disconnect")
                if self._on_disconnect:
                    self._on_disconnect(handset)
            else:
                self.ACK(1)
        elif "8e" == func:
            print("connect")
            if self._on_connect:
                name, services = self._on_connect(self.handsets[num])
            self._send_name(self.handsets[num], name)
            self._send_services(self.handsets[num], services)
            # &send_tones
        elif "91" == func:
            # sending AIM username
            handset._set_service("A")
            user = b""
            _regex = b"\0?(.\x91)?([^\xff]+)?([^\w]*)?"
            while True:
                match = re.search(_regex, data_str)
                user += match.group(2)
                if len(match.group(3)):
                    break
                self.read()
            handset._set_username(user)
        elif "92" == func:
            # sending AIM password
            _pass = b""
            _regex = b"\0?(.\x92)?([^\xff]+)?([^\w]*)?"
            while True:
                match = re.search(_regex, data_str)
                if not match.group(2):
                    break
                _pass += match.group(2)
                if len(match.group(3)):
                    break
                self.read()
            handset._set_password(_pass)
            id = handset.id
            if self._on_login:
                self._on_login(handset)
                self.write(struct.pack("BBB", hex("e" + str(id)), 0xd3, 0xff))
                self.ACK()
                # XXX - ...should this exist?
                if self._on_login_complete:
                    self._on_login_complete(handset)
            else:
                return self.write(struct.pack("BBBB", hex("e" + id), 0xe5, 0x02, 0xff))
        elif "94" == func:
            # new/newly selected AIM window
            self._read_open_window(handset, self.buff_data)
        elif "95" == func:
            if self._on_window_close:
                self._on_window_close(handset)
            handset._close_window()
            if "f1" == func:
                # unused if statement?
                _ = ""
        elif "b1" == func:
            # YAHOO! username
            handset._set_service("Y")
            user = b""
            _regex = b"\0?(.\xb1)?([^\xff]+)?([^\w]*)?"
            while True:
                match = re.search(_regex, data_str)
                user += match.group(2)
                if len(match.group(3)):
                    break
                self.read()
            handset._set_username(user)
            print(f"(H|{handset.id}) sending Yahoo! username: {handset.username}")
        elif "b2" == func:
            # YAHOO! password
            _pass = b""
            _regex = b"\0?(.\xb2)?([^\xff]+)?([^\w]*)?"
            while True:
                match = re.search(_regex, data_str)
                if match.group(2):
                    _pass += match.group(2)
                if len(match.group(3)):
                    break
                self.read()
            handset._set_password(_pass)
            print(f"(H|{handset.id}) sending Yahoo! pass: {handset.password} | And we're logging in ...")
            id = handset.id
            if self._on_login:
                self._on_login(handset)
                self.write(struct.pack("BBB", hex("e" + str(id)), 0xd3, 0xff))
                if self._on_login_complete:
                    self._on_login_complete(handset)
            else:
                return self.write(struct.pack("BBBB", hex("e" + str(id)), 0xe5, 0x02, 0xff))
        else:
            self._read_IM(handset)

    def id_dispatch_8(self, num, func):
        handset = self._get_handset(num)
        return self._read_IM(handset)

    def do_one_loop(self):
        if self.read() == 0:
            return
        buff = []
        buff_h = []
        for d in self.data_in:
            buff.append("%04d" % d)
            buff_h.append("%#.4x" % d)

        null = 0
        if buff_h[0] == "0x000000":
            null = 1
        byte_1st = buff_h[0+null]
        byte_2nd = buff_h[1+null]
        self.buff_data = buff_h[2+null:]
        #print([c for c in byte_1st])
        #print([c for c in byte_2nd])
        if len(self.data_in):
            _, _, _, _, id, num = [c for c in byte_1st]
            _, _, _, _, func_a, func_b = [c for c in byte_2nd]
            func = func_a + func_b
            buff_str = ",".join(["%#.2x" % hex(c) for c in self.buff_data])
            print(f"id: {id}, func: {func}, buff: ({buff_str})")
            if has_key(self.id_dispatch, id):
                self.id_dispatch[id](num, func)
        return 1

    def _read_IM(self, handset):
        if not handset:
            return

        # 94  0x81  talk? not followed by talk ack
        # 94  0x02  talk?
        # 94  0x01  talk? IMFree Agent (in first group)

        IM = b""
        id = handset.id
        loops = 1
        regex = re.compile(b"^([%c%c%c%c])([^\xff\xfe]*)([\xff\xfe]*)" % (
            hex("a" + hex(id)),
            hex("f" + hex(id)),
            hex("d" + hex(id)),
            hex("8" + hex(id))
        ))
        four = 0
        while True:
            data_str = b"".join([b"%c" % b for b in self.data_in])
            print(data_str)
            print(IM)
            if match := regex.search(data_str):
                four = 0
                print("i1")
                if len(match.group(2)):
                    IM += match.group(2)
                if re.search(b"[\xff\xfe]+", data_str) or len(match.group(3)):
                    break
                self.read()
            elif match := re.search(b"^(.+)\xff", data_str):
                four = 0
                print("i2")
                IM += match.group(1)
                break
                self.read()
            elif match := re.search(b".\xff\xfe?", data_str):
                four = 0
                print("i3")
                self.ACK(0)
                break
            elif match := re.search(b"([^\xff]+)\xfe", data_str):
                if not four:
                    IM += match.group(1)
                    four += 1
                print(f"i4 ({four})")
                #self.ACK(0)
                self.read()
            else:
                four = 0
                print("i5s")
                if match := re.search(b"^([^\xff\xfe]*)\xff\xfe?", data_str):
                    if match.group(1):
                        IM += match.group(1)
                    break
                data_str = re.sub(b"^\0", b"", data_str)
                IM += data_str
                #self.ACK(0)
                self.read()
                data_str = b"".join([b"%c" % b for b in self.data_in])
                print("i5r: " + str([b for b in data_str]))
                if match := re.search(b"^([^\xff\xfe]*)\xff\xfe?", data_str):
                    if match.group(1):
                        IM += match.group(1)
                    break
            #if loops == 3:
                #print("3 loops break")
                #break
            loops += 1

        # if no terminator, just end after 3 chunks of 8.
        # if only room for ff in third chunk, put that.

        self.ACK(0)
        if self._on_im:
            self._on_im(handset, IM)
        return 1

    def _read_open_window(self, handset, buff_data):
        if not handset.service:
            print("No service")
            handset._range_error()
            return

        c_im = hex(buff_data[0])
        #c_im = re.sub(r"[^\d]", "", c_im)
        buddy = handset._locate_buddy_by_id(c_im)
        if not buddy:
            return
        self.ACK(0)
        result = handset._set_window(c_im)
        if self._on_window_open:
            _check = True if buff_data[2] == "fe" else False
            self._on_window_open(handset, c_im, buddy, _check)
        return result

    def _send_buddy_in(self, handset, args):
        if not args:
            return
        id = handset.id
        screenname = args["screenname"]
        group = args["group"]
        if not has_key(args, "away"):
            args["away"] = 0
        if not has_key(args, "mobile"):
            args["mobile"] = 0
        if not has_key(args, "idle"):
            args["idle"] = 0
        if not has_key(args, "id"):
            args["id"] = random.randint(0x0, 0xff - 1)

        status = "ANN" # basic
        if args["idle"]:
            status = re.sub(r"A", "I", status)
        elif args["away"]:
            status = re.sub(r"A", "U", status)
        elif args["mobile"]:
            status = re.sub(r"N", "Y", status)
        self.ACK(1) # Some action on the pipe first... just in case...

        #eNca  >    status 0x01-0x3c     0000  X  set buddy status (status: ANN, AYN, UNN)
        #ANN = (no icon)
        #AYN = Buddy is online using a mobile device
        #UNN = Buddy is away
        #UYN = Buddy is away
        #INN = Buddy is idle
        #IYN = Buddy is idle

        self.write(
            struct.pack("BB", hex("e" + str(id)), 0xca) +
            b"".join([c.encode("ascii") for c in status]) +
            struct.pack("B", args["id"]))

        if len(args["group"]) > 6:
            args["group"] = args["group"][0:6]
        else:
            args["group"] = "% 6s" % args["group"]

        self.write(
            struct.pack("BB", hex("c" + str(id)), 0xc9) +
            # cNc9  >    group name           ff00  X  send person data
            b"".join([c.encode("ascii") for c in (args["group"])]) +
            b"".join([c.encode("ascii") for c in args["screenname"]]) +
            struct.pack("6B", 0xff, 0x00,
            # aNc9  >    remaining-data       ff00  X  send more person data ?
            hex("a" +  str(id)), 0xc9, 0x01, 0xff))

        #000102  ]>  e1ca 414e 4e01 0000  ..ANN... # add person
        #000106  ]>  c1c9 2020 4d65 2020  ..  Me   # send person data
        #000107  ]>  494d 6672 6565 2041  IMfree A
        #000108  ]>  6765 6e74 ff00       gent.. A
        #000122  ]>  a1c9 20ff 00         .. ..    # status modifier?
        # flush the pipe

        return self.ACK(1)

    def _send_services(self, handset, services):
        i = 0
        for chr in "AYM":
            if has_key(services, chr):
                self.write(
                    struct.pack("BB", hex("e" + hex(handset.id)), 0xd7) +
                    b"".join([c.encode("ascii") for c in services[chr]]) +
                    struct.pack("B", 0xff)
                )
                i += 1
        return 1

    def _send_name(self, handset, name):
        d_len = len(name)
        return self.write(
            struct.pack(f"BB", handset.id, 0xd9) +
            b"".join([c.encode("ascii") for c in name]) +
            struct.pack("B", 0xff)
        )

    def read(self):
        #print("read")
        buf = self._read(MX240a.READ_SIZE)
        if len(buf) == 0:
            return 0
        self.data_in = buf
        if self._on_data_in:
            self._on_data_in(self.data_in)
        return len(self.data_in)

    def write(self, data, forget = False):
        if not data:
            return
        if not forget:
            self.last_sent = data

        #print(f"writing {len(data)} bytes")
        sent = 0
        parts = [data[i:i + 8] for i in range(0, len(data), 8)]
        for part in parts:
            part = part.ljust(8, b"\0")
            part = b"\0" + part
            sent += self._write(part)
            time.sleep(0.15)
            if self._on_data_out:
                self._on_data_out(part)
        return sent

class Base(MX240a):
    def __init__(self):
        super().__init__()
        #self._handle = None

    def _init_USB(self):
        return self.write(struct.pack("BBBB", 0xad, 0xef, 0x8d, 0xff))

    def _open(self):
        d = hid.device()
        try:
            d.open(0x22b8, 0x7f01)
            #d.set_nonblocking(1)
            print(f"mfr: {d.get_manufacturer_string()}")
            print(f"prd: {d.get_product_string()}")
            print(f"ser: {d.get_serial_number_string()}")
        except IOError as e:
            print("Base not connected?")
            raise
        self._handle = d
        return d

    def _write(self, data):
        return self._handle.write(data)

    def _read(self, amount):
        return self._handle.read(amount)

    def _close(self):
        return self._handle.close()
