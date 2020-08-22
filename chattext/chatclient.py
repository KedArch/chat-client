#!/usr/bin/env python3

import os
import sys
import ssl
import socket
import select
import asyncio
import argparse
import threading
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.patch_stdout import patch_stdout
    from prompt_toolkit.completion import NestedCompleter
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
except ImportError:
    print("This client requires prompt_toolkit library to work.\n"
          "Download it with below command\n"
          "pip install --user prompt_toolkit")
    sys.exit(65)


class Client():
    def __init__(self):
        self.basedir = os.path.dirname(os.path.realpath(sys.argv[0]))
        self.ps = PromptSession()
        self.client = ""
        self.addr = (None, " not connected to any")
        self.welcome = "Welcome! Type :h for help."
        self.help = {
                ":c": "connects to server",
                ":dc": "disconnects from the server",
                ":h": "help",
                ":q": "quits program",
                }
        self.completions = {
                ":c": None,
                ":dc": None,
                ":h": None,
                ":q": None,
                }
        self.completer = NestedCompleter.from_nested_dict(self.completions)

    def bottom_text(self):
        return f"Server> {self.addr[0]}:{self.addr[1]}"

    async def input_method(self):
        with patch_stdout():
            msg = await self.ps.prompt_async(
                    "> ",
                    enable_history_search=True,
                    complete_in_thread=True,
                    completer=self.completer,
                    auto_suggest=AutoSuggestFromHistory(),
                    bottom_toolbar=self.bottom_text)
        return msg

    def print_method(self, msg):
        print(msg)

    def receive(self):
        while True:
            try:
                r, _, _ = select.select([self.client], [self.client],
                                        [self.client])
                if r:
                    data = self.client.recv(4096).decode("utf8")
                    if data == "":
                        self.client.close()
                        self.disconnect()
                        self.addr = (None, " not connected to any")
                        break
                    self.print_method(data)
            except (OSError, ValueError, ConnectionResetError):
                self.disconnect()
                self.addr = (None, " not connected to any")
                break

    def send(self, data):
        self.client.sendall(bytes(data, "utf8"))

    def exit_program(self, status):
        if self.client != "":
            try:
                self.disconnect()
            except (NameError, BrokenPipeError):
                pass
        sys.exit(status)

    def disconnect(self):
        if self.client:
            self.addr = (None, " not connected to any")
            self.client.close()
            self.print_method("Disconnected from"
                              f" {self.host}"
                              f":{self.port}")
            self.client = ""
        try:
            self.receive_thread.join()
        except (AttributeError, RuntimeError):
            pass

    def start(self, secure=False):
        if not sys.stdin.isatty():
            sys.exit(66)
        self.print_method(self.welcome)
        while True:
            try:
                msg = asyncio.run(self.input_method())
                if not msg:
                    continue
                elif msg.split(" ", 3)[0] == ":c":
                    try:
                        if len(msg.split(" ", 3)) > 3:
                            self.print_method("Invalid arguments")
                        if self.client:
                            self.disconnect()
                        self.host = msg.split(" ", 3)[1]
                        self.port = int(msg.split(" ", 3)[2])
                        self.addr = (self.host, self.port)
                        self.client = socket.socket(
                                socket.AF_INET,
                                socket.SOCK_STREAM)
                        if secure:
                            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                            context.load_verify_locations(secure)
                            self.client = ssl.wrap_socket(self.client)
                        self.client.connect(self.addr)
                        self.receive_thread = threading.Thread(
                            name="Receive",
                            target=self.receive
                        )
                        self.receive_thread.daemon = 1
                        self.receive_thread.start()
                        self.print_method("Connected to"
                                          f" {self.host}"
                                          f":{self.port}")
                    except (KeyboardInterrupt, EOFError):
                        self.exit_program(0)
                    except IndexError:
                        self.print_method("Invalid arguments")
                    except ConnectionRefusedError:
                        self.print_method("Host refused connection")
                    except socket.gaierror:
                        self.print_method("Unknown host")
                    except OSError:
                        self.print_method("No connection to host")
                    except (TypeError, ValueError, OverflowError):
                        self.print_method("Port must be in 0-65535 range")
                elif msg == ":dc":
                    if self.client != "":
                        self.disconnect()
                    else:
                        self.print_method("Not connected to any host")
                elif msg == ":h":
                    self.print_method("Client commands:")
                    for i in self.help.keys():
                        self.print_method(f"{i} - {self.help[i]}")
                    try:
                        self.send(msg)
                    except (NameError, OSError, AttributeError):
                        pass
                elif msg == ":q":
                    self.exit_program(0)
                else:
                    try:
                        self.send(msg)
                    except (NameError, OSError, AttributeError):
                        if msg.startswith(":"):
                            self.print_method(f"Unknown command: '{msg}'")
                        else:
                            self.print_method("Not connected to any host")
            except EOFError:
                self.exit_program(0)
            except KeyboardInterrupt:
                continue
            except BrokenPipeError:
                self.client.close()
                self.print_method("Connection to server lost")


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
