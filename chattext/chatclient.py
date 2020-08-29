#!/usr/bin/env python3
# Todo:
# -update completion
# -timeout
# -protocol
# -config
# -colors
# -commands
import os
import sys
import ssl
import shlex
import select
import signal
import socket
import asyncio
import argparse
import threading
from collections.abc import Mapping
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.patch_stdout import patch_stdout
    from prompt_toolkit.completion import NestedCompleter
except ImportError:
    print("This client requires prompt_toolkit library to work.\n"
          "Download it with below command\n"
          "pip install --user prompt_toolkit")
    sys.exit(65)


class Client():
    def __init__(self):
        self.basedir = os.path.dirname(os.path.realpath(sys.argv[0]))
        self.ps = PromptSession()
        self.client = None
        self.addr = (None, " not connected to any")
        self.welcome = "Welcome! Type :h for help."
        self.help = {
                ":c": "connects to server",
                ":dc": "disconnects from the server",
                ":h": "help",
                ":q": "quits program",
                }
        self.completions = {
                ":c": {"localhost": {"1111": None}},
                ":dc": None,
                ":h": None,
                ":q": None,
                }
        self.completer = NestedCompleter.from_nested_dict(self.completions)
        signal.signal(signal.SIGTERM, self.exit)

    def bottom_text(self):
        return f"Server> {self.addr[0]}:{self.addr[1]}"

    def merge_dicts(self, d, u):
        for k, v in u.items():
            if isinstance(v, Mapping):
                d[k] = self.merge_dicts(d.get(k, {}), v)
            elif isinstance(d, dict):
                d[k] = u[k]
            else:
                d = {k: u[k]}
        return d

    def update_completion(self, msg):
        for i in msg[1:]:
            pass
        # self.merge_dicts(self.completions, new)

    async def input_method(self):
        with patch_stdout():
            msg = await self.ps.prompt_async(
                    "> ",
                    complete_while_typing=True,
                    complete_in_thread=True,
                    completer=self.completer,
                    bottom_toolbar=self.bottom_text)
        return msg

    def print_method(self, msg):
        print(msg)

    def receive(self):
        while True:
            try:
                r = select.select([self.client], [], [])
                if r:
                    data = self.client.recv(4096).decode("utf8")
                    if data == "":
                        self.disconnect_recv(False)
                        break
                    self.print_method(data)
            except (OSError, ValueError, ConnectionResetError):
                self.disconnect_recv(True)
                break

    def send(self, data):
        self.client.sendall(bytes(data, "utf8"))

    def exit(self, status, frame=None):
        self.disconnect_main()
        sys.exit(status)

    def disconnect_main(self):
        if self.client:
            try:
                self.client.close()
                self.receive_thread.join()
            except (BrokenPipeError, AttributeError):
                pass

    def disconnect_recv(self, error):
        if self.client:
            self.addr = (None, " not connected to any")
            self.client = None
            if error:
                self.print_method("Connection lost with"
                                  f" {self.host}"
                                  f":{self.port}")
            else:
                self.print_method("Disconnected from"
                                  f" {self.host}"
                                  f":{self.port}")

    def start(self, secure=False):
        if not sys.stdin.isatty():
            sys.exit(66)
        self.print_method(self.welcome)
        while True:
            try:
                self.completer = NestedCompleter.from_nested_dict(
                        self.completions)
                msg = shlex.split(asyncio.run(self.input_method()))
                if not msg:
                    continue
                elif msg[0] == ":c":
                    try:
                        if len(msg) > 3:
                            self.print_method("Invalid arguments")
                        if self.client:
                            self.disconnect_main()
                        self.host = msg[1]
                        self.port = int(msg[2])
                        self.addr = (self.host, self.port)
                        self.client = socket.socket(
                                socket.AF_INET,
                                socket.SOCK_STREAM)
                        if secure:
                            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                            context.load_verify_locations(secure)
                            self.client = ssl.wrap_socket(self.client)
                        self.client.settimeout(5)
                        self.client.connect(self.addr)
                        self.client.settimeout(None)
                        self.print_method("Connected to"
                                          f" {self.host}"
                                          f":{self.port}")
                        self.receive_thread = threading.Thread(
                            name="Receive",
                            target=self.receive
                        )
                        self.receive_thread.daemon = 1
                        self.receive_thread.start()
                        self.update_completion(msg)
                    except IndexError:
                        self.print_method("Invalid arguments")
                    except ConnectionRefusedError:
                        self.print_method("Host refused connection")
                    except socket.gaierror:
                        self.print_method("Unknown host")
                    except OSError as e:
                        if "[Errno 2]" in str(e):
                            self.print_method(
                                    "No certificate file. Please restart "
                                    "program with valid certificate.")

                        elif "[X509" in str(e):
                            self.print_method(
                                    "Invalid certificate. Please restart "
                                    "program with valid certificate.")
                        else:
                            self.print_method("No connection to host")
                    except (TypeError, ValueError, OverflowError):
                        self.print_method("Port must be in 0-65535 range")
                elif msg[0] == ":dc":
                    if self.client != "":
                        self.disconnect_main()
                    else:
                        self.print_method("Not connected to any host")
                elif msg[0] == ":h":
                    self.print_method("Client commands:")
                    for v, k in self.help.items():
                        self.print_method(f"{v} - {self.help[k]}")
                    try:
                        self.send(shlex.join(msg))
                    except (NameError, OSError, AttributeError):
                        pass
                elif msg[0] == ":q":
                    self.exit(0)
                else:
                    try:
                        self.send(shlex.join(msg))
                    except (NameError, OSError, AttributeError):
                        if msg.startswith(":"):
                            self.print_method(f"Unknown command: '{msg}'")
                        else:
                            self.print_method("Not connected to any host")
            except EOFError:
                self.exit(0)
            except KeyboardInterrupt:
                continue


def parse_args():
    arg = argparse.ArgumentParser(
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description="Simple chat client intended for personal use",
            epilog="Error codes an their element:"
                   "\n65 - prompt_toolkit import"
                   "\n66 - not a pts/tty")
    arg.add_argument(
        "-s", "--secure",
        help="Enables SSL/TLS. Argument is certfile for auth.")
    Client().start(arg.parse_args().secure)


if __name__ == "__main__":
    parse_args()
