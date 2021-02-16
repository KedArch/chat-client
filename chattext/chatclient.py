#!/usr/bin/env python3
# Todo:
# -update completion
# -timeout
# -config
# -colors
# -commands
import os
import sys
import ssl
import json
import shlex
import select
import signal
import socket
import asyncio
import argparse
import threading
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
        self.csep = "/"
        self.client = None
        self.addr = (None, " not connected to any")
        self.welcome = f"Welcome! Type {self.csep}h for help."
        self.help = {
                f"{self.csep}c $addr $port": "connects to server",
                f"{self.csep}dc": "disconnects from the server",
                f"{self.csep}h": "help",
                f"{self.csep}q": "quits program",
                }
        self.completions = {
                f"{self.csep}c": {"localhost": {"1111": None}},
                f"{self.csep}dc": None,
                f"{self.csep}h": None,
                f"{self.csep}q": None,
                }
        self.completer = NestedCompleter.from_nested_dict(self.completions)
        signal.signal(signal.SIGTERM, self.exit)

    def bottom_text(self):
        return f"Server> {self.addr[0]}:{self.addr[1]}"

    def update_completion(self, msg):
        for i in msg[1:]:
            pass

    async def input_method(self):
        with patch_stdout():
            msg = await self.ps.prompt_async(
                    "> ",
                    complete_while_typing=False,
                    complete_in_thread=True,
                    completer=self.completer,
                    bottom_toolbar=self.bottom_text)
        return msg

    def print_method(self, msg):
        print(msg)

    def receive(self):
        while True:
            try:
                r, _, _ = select.select([self.client], [], [], 1)
                if r:
                    data = self.client.recv(self.buffer).decode("utf8")
                    if data == "":
                        self.disconnect_recv(False)
                        break
                    data = json.loads(data)
                    if data["type"] == "message":
                        if data["attrib"] == "csep":
                            self.print_method(
                                data["content"].replace(
                                    "{csep}", self.csep))
                        else:
                            self.print_method(data["content"])
                    elif data["type"] == "privmsg":
                        pass
                    elif data["type"] == "control":
                        pass
            except (OSError, ValueError, ConnectionResetError,
                    json.JSONDecodeError, TypeError):
                self.disconnect_recv(True)
                break

    def send(self, content, mtype="message", attrib=None):
        tmp = {
            "type": mtype,
            "attrib": attrib,
            "content": content.strip()
        }
        data = json.dumps(tmp)
        if not len(data) > int(self.buffer*0.8):
            data = data.ljust(self.buffer)
            self.client.sendall(bytes(data, "utf8"))
        else:
            self.print_method(
                "Your message is too large! It can be at most "
                f"{self.buffer*0.8} (80% server's buffer "
                f"{self.buffer} is safe limit).")

    def exit(self, status, frame=None):
        self.disconnect_main()
        sys.exit(status)

    def disconnect_main(self):
        if self.client:
            try:
                self.client.close()
                self.addr = (None, " not connected to any")
                self.receive_thread.join()
            except (BrokenPipeError, AttributeError):
                pass

    def disconnect_recv(self, error):
        if self.client:
            if error and self.addr[0]:
                self.print_method("Connection lost with"
                                  f" {self.host}"
                                  f":{self.port}")
            else:
                self.print_method("Disconnected from"
                                  f" {self.host}"
                                  f":{self.port}")
            self.client = None
            self.addr = (None, " not connected to any")

    def command_connect(self, msg, secure):
        try:
            if len(msg) > 3:
                self.print_method("Invalid arguments")
            if self.client:
                self.disconnect_main()
            self.host = msg[1]
            self.port = int(msg[2])
            addr = (self.host, self.port)
            self.client = socket.socket(
                    socket.AF_INET,
                    socket.SOCK_STREAM)
            if secure:
                context = ssl.SSLContext(
                    ssl.PROTOCOL_TLS_CLIENT)
                context.load_verify_locations(secure)
                self.client = ssl.wrap_socket(self.client)
            self.client.settimeout(5)
            self.client.connect(addr)
            self.client.settimeout(None)
            self.print_method("Connected to"
                              f" {self.host}"
                              f":{self.port}")
            try:
                self.buffer = int(
                    self.client.recv(1024).decode("utf8"))
                self.send(
                    f"ACK{self.buffer}", "control", "buffer")
            except Exception:
                self.print_method(
                    "Server didn't send buffer size!"
                    " Disconnecting...")
                self.disconnect_main()
                self.disconnect_recv(False)
                return True
            self.addr = (self.host, self.port)
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

    def command_disconnect(self):
        if self.client != "":
            self.disconnect_main()
        else:
            self.print_method("Not connected to any host")

    def command_help(self):
        self.print_method(f"Command separator: '{self.csep}'")
        self.print_method("Client commands:")
        for k, v in self.help.items():
            self.print_method(f"{k} - {v}")
        try:
            self.send("h", "command")
        except (NameError, OSError, AttributeError):
            pass

    def start(self, secure=False):
        if not sys.stdin.isatty():
            sys.exit(66)
        self.print_method(self.welcome)
        while True:
            try:
                self.completer = NestedCompleter.from_nested_dict(
                        self.completions)
                msg = asyncio.run(self.input_method())
                if msg.startswith(f"{self.csep}"):
                    msg = shlex.split(msg)
                    if not msg:
                        continue
                    elif msg[0] == f"{self.csep}c":
                        if self.command_connect(msg, secure):
                            continue
                    elif msg[0] == f"{self.csep}dc":
                        self.command_disconnect()
                    elif msg[0] == f"{self.csep}h":
                        self.command_help()
                    elif msg[0] == f"{self.csep}q":
                        self.exit(0)
                    else:
                        try:
                            msg = shlex.join(msg)
                            self.send(msg[1:], "command")
                        except (NameError, OSError, AttributeError):
                            self.print_method(f"Unknown command: '{msg}'")
                else:
                    try:
                        self.send(msg)
                    except (NameError, OSError, AttributeError):
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
