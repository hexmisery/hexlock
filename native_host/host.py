import json
import struct
import sys
import os
import ctypes
import msvcrt
from multiprocessing.connection import Client

from app.ipc import runtime_file


MAX_BYTES = 65536


def connect_streams():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [ctypes.c_uint32]
    kernel.GetStdHandle.restype = ctypes.c_void_p
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.DuplicateHandle.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    process = kernel.GetCurrentProcess()
    for name, standard, flags, mode in (("stdin", -10, os.O_RDONLY, "rb"), ("stdout", -11, os.O_WRONLY, "wb")):
        handle = kernel.GetStdHandle(standard & 0xffffffff)
        duplicate = ctypes.c_void_p()
        if not kernel.DuplicateHandle(process, handle, process, ctypes.byref(duplicate), 0, False, 2):
            raise ctypes.WinError(ctypes.get_last_error())
        descriptor = msvcrt.open_osfhandle(duplicate.value, flags | os.O_BINARY)
        setattr(sys, name, os.fdopen(descriptor, mode))


def read_message():
    header = sys.stdin.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ValueError("header")
    size = struct.unpack("<I", header)[0]
    if size > MAX_BYTES:
        raise ValueError("size")
    payload = sys.stdin.read(size)
    if len(payload) != size:
        raise ValueError("body")
    return json.loads(payload)


def write_message(message):
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    sys.stdout.write(struct.pack("<I", len(payload)) + payload)
    sys.stdout.flush()


def forward(request):
    try:
        config = json.loads(runtime_file().read_text(encoding="utf-8"))
        with Client(config["address"], family="AF_PIPE", authkey=bytes.fromhex(config["auth"])) as connection:
            connection.send_bytes(json.dumps(request).encode("utf-8"))
            if not connection.poll(90 if request.get("action") == "get" else 5):
                return {"error": "offline"}
            return json.loads(connection.recv_bytes(maxlength=65536))
    except (OSError, EOFError, KeyError, ValueError):
        return {"error": "offline"}


def main():
    connect_streams()
    while True:
        try:
            request = read_message()
            if request is None:
                return
            if not isinstance(request, dict) or request.get("action") not in ("list", "get"):
                write_message({"error": "request"})
                continue
            write_message(forward(request))
        except (ValueError, json.JSONDecodeError):
            write_message({"error": "request"})
            return


if __name__ == "__main__":
    main()
