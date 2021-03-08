#!/usr/bin/env python
import os
import sys
import ssl
import json
import time
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
    """
    Main client class
    """
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
        self.fully_connected = False
        self.default_completions = self.completions.copy()
        self.completer = NestedCompleter.from_nested_dict(self.completions)
        signal.signal(signal.SIGTERM, self.exit)
        self.completion_replacements = {
            "nick": "nick",
            "user": "user",
            "pass": "pass",
            "message": "message",
            "sname": "sname"
        }

    def bottom_text(self):
        """
        Returns text for bottom toolbar
        """
        return f"Server> {self.addr[0]}:{self.addr[1]}"

    def dict_to_dict(self, orig, clist):
        """
        Helps merging completion parameters
        """
        if len(clist) == 1:
            orig[clist[0]] = None
        else:
            orig[clist[0]] = {clist[1]: None}
            old = clist[0]
            clist.pop(0)
            orig[old] = self.dict_to_dict(orig[old], clist)
        return orig

    def update_completion(self, command):
        """
        Manipulates completion
        """
        if not command.startswith(self.csep):
            return
        command = command.split("-", 1)[0].split()
        for k, v in self.completion_replacements.items():
            for i in range(len(command)):
                command[i] = command[i].replace(f"${k}", v)
        try:
            self.completions = self.dict_to_dict(
                self.completions, command)
        except Exception:
            pass

    async def input_method(self):
        """
        Manages input asynchronously (without destroying prompt)
        """
        with patch_stdout():
            msg = await self.ps.prompt_async(
                "> ",
                complete_while_typing=True,
                complete_in_thread=True,
                completer=self.completer,
                bottom_toolbar=self.bottom_text)
        return msg

    def print_method(self, msg):
        """
        Manages output
        """
        print(msg)

    def receive(self):
        """
        Handles communication with server
        """
        timeout = 0
        while True:
            try:
                rdy, _, _ = select.select([self.client], [], [], 1)
                if rdy and timeout < self.timeout:
                    timeout = 0
                    data = self.client.recv(self.buffer).decode("utf8")
                    if data == "":
                        self.disconnect_recv(False)
                        break
                    data = json.loads(data)
                    if data['type'] == "message":
                        if "csep" in data["attrib"]:
                            data['content'] = data['content'].replace(
                                "{csep}", self.csep)
                        if "welcome" in data["attrib"]:
                            self.fully_connected = True
                        self.print_method(data['content'])
                    elif data['type'] == "control":
                        if "alive" in data['attrib']:
                            self.send("", "control", ['alive'])
                        elif "csep" in data['attrib']:
                            command = data['content'].replace(
                                "{csep}", self.csep)
                            self.update_completion(command)
                elif timeout >= self.timeout:
                    raise ConnectionAbortedError
                else:
                    timeout += 1
            except (OSError, ValueError, ConnectionResetError,
                    json.JSONDecodeError, TypeError):
                self.disconnect_recv(True)
                break
            except ConnectionAbortedError:
                self.print_method(
                    f"Connection with {self.host}:{self.port} timed out.")
                self.disconnect_recv(True)
            except AttributeError:
                self.disconnect_recv(False)

    def send(self, content, mtype="message", attrib=[]):
        """
        Handles message sending with correct protocol
        """
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
        """
        Handles exit signal
        """
        self.disconnect_main()
        sys.exit(status)

    def disconnect_main(self):
        """
        Resets main thread variables
        """
        if self.client:
            try:
                self.addr = (None, " not connected to any")
                self.client.shutdown(socket.SHUT_RDWR)
                self.client.close()
                self.client = None
            except (BrokenPipeError, AttributeError, OSError):
                pass

    def disconnect_recv(self, error):
        """
        Handles receive function exit
        """
        if self.client:
            if error and self.addr[0]:
                self.print_method(
                    "Connection lost with"
                    f" {self.host}"
                    f":{self.port}")
            else:
                self.print_method(
                    "Disconnected from"
                    f" {self.host}"
                    f":{self.port}")
            self.addr = (None, " not connected to any")
            self.client = None
        else:
            self.print_method(
                "Disconnected from"
                f" {self.host}"
                f":{self.port}")
        self.completions = self.default_completions
        self.fully_connected = False

    def command_connect(self, msg, secure):
        """
        Connect functionality
        """
        try:
            if len(msg) > 3:
                self.print_method("Invalid arguments")
            if self.client:
                self.disconnect_main()
            while self.fully_connected:
                time.sleep(0.1)
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
            self.client.settimeout(10)
            self.client.connect(addr)
            self.client.settimeout(None)
            self.print_method("Connected to"
                              f" {self.host}"
                              f":{self.port}")
            try:
                rdy, _, _ = select.select([self.client], [], [], 15)
                if rdy:
                    self.buffer = int(
                        self.client.recv(1024).decode("utf8"))
                    self.send(
                        f"ACK{self.buffer}", "control", ['buffer'])
                    rdy2, _, _ = select.select([self.client], [], [], 15)
                    if rdy:
                        response = json.loads(self.client.recv(
                            self.buffer).decode("utf8"))
                        if response['type'] == "control" and\
                                "timeout" in response['attrib']:
                            self.timeout = float(response['content'])
                        else:
                            raise ConnectionRefusedError
                else:
                    raise ConnectionRefusedError
            except Exception:
                self.print_method(
                    "Failed to properly communicate with server or "
                    "hit 30s waiting limit! Disconnecting...")
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
            while not self.fully_connected:
                time.sleep(0.1)
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
        """
        Disconnect functionality
        """
        if self.client:
            self.disconnect_main()
        else:
            self.print_method("Not connected to any host")

    def command_help(self):
        """
        Help functionality
        """
        self.print_method(f"Command separator: '{self.csep}'")
        self.print_method("Client commands:")
        for k, v in self.help.items():
            self.print_method(f"{k} - {v}")
        self.print_method(
            "For server command completion call this "
            "command  when connected to server\n"
            "Completion for given command will be active "
            "after it will be printed in there\n"
            "There may be need to press 'ENTER' once for it to appear")
        try:
            self.send("h", "command")
        except (NameError, OSError, AttributeError):
            pass

    def start(self, secure=False, command=""):
        """
        Main thread functionality
        """
        if not sys.stdin.isatty():
            sys.exit(66)
        self.print_method(self.welcome)
        while True:
            try:
                self.completer = NestedCompleter.from_nested_dict(
                    self.completions)
                if command:
                    msg = command[0]
                    command.pop(0)
                else:
                    msg = asyncio.run(self.input_method())
                if msg.startswith(f"{self.csep}"):
                    msg = shlex.split(msg)
                    if msg[0] == f"{self.csep}c":
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
                    if not msg.strip():
                        continue
                    try:
                        self.send(msg)
                    except (NameError, OSError, AttributeError):
                        self.print_method("Not connected to any host")
            except EOFError:
                self.exit(0)
            except (KeyboardInterrupt, ValueError):
                continue


def parse_args():
    """
    Parses command line arguments
    """
    arg = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Simple chat client intended for personal use",
        epilog="Error codes an their element:"
        "\n65 - prompt_toolkit import"
        "\n66 - not a pts/tty")
    arg.add_argument(
        "-s", "--secure",
        help="Enables SSL/TLS. Argument is certfile for auth.")
    arg.add_argument(
        "-c", "--command", nargs="*",
        help="Allows start with given commands (same as in interactive)")
    args = arg.parse_args()
    Client().start(args.secure, args.command)


if __name__ == "__main__":
    parse_args()
