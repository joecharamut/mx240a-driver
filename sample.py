from driver import Handset, MX240a, Base

base = Base()

def on_im(handset, message):
    print(f"IM > {message}")
    handset._send_im(handset.window, message)
base._on_im = on_im

def on_connect(handset):
    return ("Sample Program", {
        "A": "AAAAAA",
        #"Y": "BBBBBB",
        #"M": " MSN"
    })
base._on_connect = on_connect

def on_login(handset):
    print(f"Login: {handset.username}:{handset.password} @ {handset.service}")
    return 1 # okay
    return 0 # deny
base._on_login = on_login

def on_login_complete(handset):
    buddies = [
        {"screenname": "MX240a Agent", "group": "Group"},
        {"screenname": "Eval", "group": "Group"},
        {"screenname": "system", "group": "Group"}
    ]
    for b in buddies:
        handset._buddy_in(b)
base._on_login_complete = on_login_complete

def on_window_open(handset, buddy, with_ack, check = False):
    print(f"(H|{handset.id}) Open window with buddy #{handset.window} ({buddy}), check: {check}")
    return 1
base._on_window_open = on_window_open

def on_window_close(handset):
    print("Close window")
    return 1
base._on_window_close = on_window_close

def on_data_in(data):
    for byte in data:
        print("[<] %#.6x" % byte)
    print()
base._on_data_in = on_data_in

def on_data_out(data):
    for byte in data:
        print("[>] %#.6x" % byte)
    print()
base._on_data_out = on_data_out

try:
    while True:
        base.do_one_loop()
except KeyboardInterrupt:
    base._close()
