#!/usr/bin/env python3
import os
import sys
import json
import shlex
import signal
import argparse
import asyncio
from asyncio.selector_events import ssl
from asyncio.selector_events import socket
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.patch_stdout import patch_stdout
    from prompt_toolkit.completion import NestedCompleter
    from prompt_toolkit.styles import Style
    from prompt_toolkit.shortcuts.prompt import CompleteStyle
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
        self.sname = None
        self.nick = ""
        self.client = None
        self.addr = ("You are not connected ", " to any server")
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
        self.style = Style.from_dict({
                'bottom-toolbar': 'noreverse #ffffff bg:#000000',
        })
        self.fully_connected = False
        self.default_completions = self.completions.copy()
        self.completer = NestedCompleter.from_nested_dict(self.completions)
        signal.signal(signal.SIGTERM, self.exit)

    def bottom_text(self):
        """
        Returns text for bottom toolbar
        """
        return [("class:bottom-toolbar",
                f"{self.sname}> {self.addr[0]}:{self.addr[1]}")]

    def rprompt(self):
        return self.nick

    async def dict_to_dict(self, orig, clist):
        """
        Helps merging completion parameters
        """
        if len(clist) == 1:
            orig[clist[0]] = None
        else:
            orig[clist[0]] = {clist[1]: None}
            old = clist[0]
            clist.pop(0)
            orig[old] = await self.dict_to_dict(orig[old], clist)
        return orig

    async def update_completion(self, command):
        """
        Manipulates completion
        """
        if not command.startswith(self.csep):
            return
        command = command.split("-", 1)[0].split()
        for i, c in enumerate(command):
            if command[0] == c:
                continue
            if c.startswith("$"):
                c = c[1:]
                command[i] = c
        try:
            self.completions = await self.dict_to_dict(
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
                bottom_toolbar=self.bottom_text,
                rprompt=self.rprompt,
                complete_style=CompleteStyle.MULTI_COLUMN,
                style=self.style)
        return msg

    def print_method(self, msg):
        """
        Manages output
        """
        print(msg)

    async def receive(self):
        """
        Handles communication with server
        """
        timeout = 0
        while True:
            try:
                if self.client:
                    data = await asyncio.wait_for(
                        self.loop.sock_recv(self.client, self.buffer), 1)
                else:
                    raise AttributeError
                timeout = 0
                if not data:
                    raise AttributeError
                data = json.loads(data.decode("utf8"))
                if data['type'] == "message":
                    if data["attrib"] == "csep":
                        data['content'] = data['content'].replace(
                            "{csep}", self.csep)
                    if data['attrib'] == "welcome":
                        self.fully_connected = True
                    self.print_method(data['content'])
                elif data['type'] == "control":
                    if data['attrib'] == "alive":
                        await self.send("", "control", 'alive')
                    elif data['attrib'] == "csep":
                        command = data['content'].replace(
                            "{csep}", self.csep)
                        await self.update_completion(command)
                    elif data['attrib'] == "sname":
                        self.sname = data['content']
                    elif data['attrib'] == "client":
                        self.nick = data['content']
            except (ConnectionResetError, json.JSONDecodeError, TypeError):
                self.disconnect_recv(True)
                break
            except asyncio.TimeoutError:
                if timeout >= self.timeout:
                    self.print_method(
                        f"Connection with {self.addr[0]}:"
                        f"{self.addr[1]} timed out.")
                    self.disconnect_recv(True)
                    break
                else:
                    timeout += 1
            except (OSError, AttributeError):
                self.disconnect_recv(False)
                break

    async def send(self, content, mtype="message", attrib=""):
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
            await self.loop.sock_sendall(self.client, bytes(data, "utf8"))
        else:
            self.print_method(
                "Your message is too large! It can be at most "
                f"{self.buffer*0.8} (80% server's buffer "
                f"{self.buffer} is safe limit).")

    def exit(self, status, frame=None):
        """
        Handles exit signal
        """
        try:
            self.client.close()
        finally:
            sys.exit(status)

    def reset(self):
        """
        Resets server connection variables
        """
        self.completions = self.default_completions.copy()
        self.sname = None
        self.nick = ""
        self.addr = ("You are not connected", " to any server")
        self.client = None
        self.fully_connected = False

    async def disconnect_main(self):
        """
        Forces receive thread to exit
        """
        if self.client:
            try:
                self.client.shutdown(socket.SHUT_RDWR)
                self.client.close()
                while self.fully_connected:
                    await asyncio.sleep(0)
            except (BrokenPipeError, AttributeError, OSError):
                pass
        else:
            self.reset()

    def disconnect_recv(self, error):
        """
        Handles receive function exit
        """
        if self.client:
            if error and self.addr[0]:
                self.print_method(
                    "Connection lost with"
                    f" {self.addr[0]}"
                    f":{self.addr[1]}")
            else:
                self.print_method(
                    "Disconnected from"
                    f" {self.addr[0]}"
                    f":{self.addr[1]}")
            self.reset()

    async def command_connect(self, msg, secure):
        """
        Connect functionality
        """
        try:
            if len(msg) != 3:
                raise IndexError
            if self.client:
                await self.disconnect_main()
            while self.fully_connected:
                await asyncio.sleep(0)
            host = msg[1]
            port = int(msg[2])
            self.client = socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM)
            if secure:
                ssl_context = ssl.SSLContext(
                    ssl.PROTOCOL_TLS_CLIENT)
                ssl_context.load_verify_locations(secure)
                self.client = ssl_context.wrap_socket(self.client)
            self.client.setblocking(False)
            await asyncio.wait_for(
                self.loop.sock_connect(self.client, (host, port)), 15)
            self.print_method("Connected to"
                              f" {host}"
                              f":{port}")
            try:
                response = await asyncio.wait_for(
                    self.loop.sock_recv(self.client, 512), 15)
                self.buffer = int(response.decode("utf8"))
                await self.send(f"ACK{self.buffer}", "control", 'buffer')
                response = await asyncio.wait_for(
                    self.loop.sock_recv(self.client, self.buffer), 15)
                response = json.loads(response.decode("utf8"))
                if response['type'] == "control" and\
                        "timeout" in response['attrib']:
                    self.timeout = float(response['content'])
                else:
                    raise Exception
            except Exception:
                self.print_method(
                    "Failed to properly communicate with server or "
                    "hit 30s waiting limit! Disconnecting...")
                return
            self.addr = (host, port)
            self.loop.create_task(self.receive())
            while not self.fully_connected:
                await asyncio.sleep(0)
        except IndexError:
            self.print_method("Invalid arguments")
        except asyncio.TimeoutError:
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

    async def command_disconnect(self):
        """
        Disconnect functionality
        """
        if self.client:
            await self.disconnect_main()
        else:
            self.print_method("Not connected to any host")

    async def command_help(self):
        """
        Help functionality
        """
        self.print_method(f"Command separator: '{self.csep}'")
        self.print_method("Client commands:")
        for k, v in self.help.items():
            self.print_method(f"{k} - {v}")
        try:
            await self.send("h", "command")
        except (NameError, OSError, AttributeError):
            pass

    async def handle_commands(self, secure=False, command=[], file=""):
        """
        Main thread functionality
        """
        if not sys.stdin.isatty():
            sys.exit(66)
        filecontent = [""]
        if file:
            try:
                with open(file, "r") as f:
                    for i in f.readlines():
                        filecontent[0] += i
                filecontent = filecontent[0].split("\n")
                while "" in filecontent:
                    filecontent.remove("")
            except OSError:
                self.print_method("Couldn't read commands file!")
        commands = []
        for i in command:
            if i.startswith(" "):
                commands.append(i.lstrip())
        commands += filecontent
        for i in command:
            if not i.startswith(" "):
                commands.append(i)
        self.print_method(self.welcome)
        while True:
            try:
                self.completer = NestedCompleter.from_nested_dict(
                    self.completions)
                if commands:
                    msg = commands[0]
                    commands.pop(0)
                else:
                    msg = await self.input_method()
                if msg.startswith(f"{self.csep}"):
                    msg = shlex.split(msg)
                    if msg[0] == f"{self.csep}c":
                        await self.command_connect(msg, secure)
                    elif msg[0] == f"{self.csep}dc":
                        await self.command_disconnect()
                    elif msg[0] == f"{self.csep}h":
                        await self.command_help()
                    elif msg[0] == f"{self.csep}q":
                        self.exit(0)
                    else:
                        try:
                            msg = shlex.join(msg)
                            await self.send(msg[1:], "command")
                        except (NameError, OSError, AttributeError):
                            self.print_method(f"Unknown command: '{msg}'")
                else:
                    if not msg.strip():
                        continue
                    try:
                        await self.send(msg)
                    except (NameError, OSError, AttributeError):
                        self.print_method("Not connected to any host")
            except EOFError:
                self.exit(0)
            except (KeyboardInterrupt, ValueError):
                continue

    def start(self, secure=False, command=[], file=""):
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(
            self.handle_commands(secure, command, file))


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
        "-c", "--command", nargs="*", default=[],
        help="Allows start with given commands (same as in interactive)")
    arg.add_argument(
        "file", nargs="?",
        help="Path to file with commands, executed AFTER -, "
             "before if first character of - is space. When using with -c"
             " seperate arguments with '--' or give path first"
    )
    args = arg.parse_args()
    Client().start(args.secure, args.command, args.file)


if __name__ == "__main__":
    parse_args()
