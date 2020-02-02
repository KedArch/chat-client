#!/usr/bin/env python3

import argparse, socket, threading, sys, os, select, configparser
if os.name!="nt":
    import readline


class Client():

    def __init__(self):
        self.basedir=os.path.dirname(os.path.realpath(sys.argv[0]))
        self.languagefile=os.path.join(self.basedir,"languages.ini")
        self.languagetempfile=os.path.join(self.basedir,"languages.template.ini")
        self.configfile=os.path.join(self.basedir,"config.ini")
        self.configtempfile=os.path.join(self.basedir,"config.template.ini")
        self.bufsiz=4096
        self.code="utf8"
        self.client=""
        self.english={
                "welcome":"Welcome! Type :h for help.", 
                "help":"List of available commands from the client (Executed before server commands):",
                "help_c":"connects to server",
                "help_dc":"disconnects from the server",
                "help_h":"display this help list",
                "help_q":"quits program",
                "help_tl":"explains app technical limitations.",
                "i_opt":"Invalid option: ",
                "tk_init_err":"Can't initialize Tk interface.", 
                "tkinter_err":"Can't import tkinter module.", 
                "tk_err":"An error occured when initializing Tk interface, falling back to CLI.", 
                "tk_title":"Text chat", 
                "dconn":"Disconnected from", 
                "conn":"Connected to", 
                "tm_args":"Too much arguments.",
                "ne_args":"Not enough arguments",
                "refused":"Host refused connection.",
                "u_host":"Unknown host.",
                "nct_host":"No connection to host.",
                "i_port":"Port must be in 0-65535 range.",
                "n_conn":"Not connected to any host.",
                "t_limit":"Due to technical limitations after receiving the message at the time of writing the value before '|' is in the buffer and also will be sent after pressing Enter. To prevent this please press delete key as many times as this character has.",
                "u_comm":"Unknown command: ",
                "conn_lost":"Connection to server lost.",
                    }
        self.defaults=(
            ("main", "language", "builtin"),
            ("main", "interface", "tk"),
            ("tk", "width", "400"),
            ("tk", "height", "200")
            )
        self.settings={
        "main":{
            "language":"",
            "interface":"",
                },
        "tk":{
            "width":"",
            "height":""
        }
            }

    def init_tk(self, tkinter):
        try:
            self.tk=tkinter.Tk()
            self.tk.title(self.lang_check("tk_title"))
            self.tk.resizable(1, 1)
            self.tk.protocol('WM_DELETE_WINDOW', lambda status=0: self.exit_program(status))
            swidth=self.tk.winfo_screenwidth()
            sheight=self.tk.winfo_screenheight()
            try:
                wwidth=int(self.settings["tk"]["width"])
                self.verbose("Tk window width: {}".format(wwidth))
                if wwidth<1:
                    raise ValueError
                elif swidth<wwidth:
                    self.verbose("Selected width too large. Scaling to screen's {}.".format(swidth))
                    wwidth=swidth
            except ValueError:
                self.verbose("Invalid integer given for width. Using default 400.")
                wwidth=400
            try:
                wheight=int(self.settings["tk"]["height"])
                self.verbose("Tk window height: {}".format(wheight))
                if wheight<1:
                    raise ValueError
                elif sheight<wheight:
                    self.verbose("Selected height too large. Scaling to screen's {}.".format(sheight))
                    wheight=sheight
            except ValueError:
                self.verbose("Invalid integer given for height. Using default 200.")
                wheight=200
            xcord=int(swidth/2-wwidth/2)
            ycord=int(sheight/2-wheight/2)
            self.tk.geometry("{}x{}+{}+{}".format(wwidth, wheight, xcord, ycord))
            self.frame=tkinter.Frame(self.tk)
            self.out=tkinter.Text(self.frame, height=0, width=0)
            self.scroll=tkinter.Scrollbar(self.frame)
            self.scroll.config(command=self.out.yview)
            self.out.config(yscrollcommand=self.scroll.set)
            self.entry=tkinter.Entry(self.tk)
            self.out.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=1)
            self.scroll.pack(side=tkinter.RIGHT, fill=tkinter.Y)
            self.frame.pack(side=tkinter.TOP, fill=tkinter.BOTH, expand=1)
            self.entry.pack(side=tkinter.BOTTOM, fill=tkinter.X)
            self.entry.bind('<Return>', self.on_enter)
            self.entry.bind('<Control-q>', self.exit_on_bind)
            self.entry.bind('<Up>', self.tk_history_up)
            self.entry.bind('<Down>', self.tk_history_down)
            self.entry.focus_set()
            self.tkhistory=[""]
            self.tkhistpos=0
        except tkinter.TclError:
            return 1

    def start_tk(self):
        try:
            self.tk.mainloop()
        except (KeyboardInterrupt, EOFError):
            self.exit_program(0)

    def tk_history_up(self, event=""):
        if self.tkhistpos > 0:
            self.tkhistpos-=1
            self.entry.delete(0, "end")
            self.entry.insert("end", self.tkhistory[self.tkhistpos])

    def tk_history_down(self, event=""):
        if self.tkhistpos < len(self.tkhistory)-1:
            self.tkhistpos+=1
            self.entry.delete(0, "end")
            self.entry.insert("end", self.tkhistory[self.tkhistpos])
        elif self.tkhistpos==len(self.tkhistory)-1:
            self.entry.delete(0, "end")
            self.entry.insert("end", self.tkhistory[self.tkhistpos])

    def init_lang(self, lang):
        if lang=="builtin":
            self.verbose("Using builtin English.")
            return self.english
        else:
            languages=configparser.ConfigParser()
            languages.read(self.languagefile)
            try:
                sellang={}
                language=languages.get("main", lang)
                for key in self.english.keys():
                    try:
                        sellang[key]=languages.get(language, key)
                    except configparser.NoOptionError:
                        languages.set(language, key, self.english[key])
                        sellang[key]=self.english[key]
                        self.verbose("No key '{}' in {} in language file. Adding it with English text.".format(key, lang))
                return sellang
            except configparser.NoSectionError:
                self.verbose("It seems that {} is in main section, but associated section doesn't exist. Ignoring it and using builtin English.".format(lang))
            except (configparser.NoSectionError, configparser.NoOptionError):
                self.verbose("Can't find language {} in file. Using builtin English.".format(lang))
            return self.english

    def lang_template(self, err):
        self.verbose("Creating language template file.")
        languages=configparser.ConfigParser()
        languages.add_section("main")
        languages.set("main", "en", "english")
        languages.add_section("english")
        for i in self.english:
            languages.set("english", i, self.english[i])
        try:
            with open(self.languagetempfile, "w", encoding="utf-8") as langfile:
                languages.write(langfile)
            self.verbose("Done. Rename it to {} to make it work.".format(os.path.basename(self.languagefile)))
            if not err:
                sys.exit(0)
        except PermissionError:
            self.verbose("Can't write in folder. Check permissions. Language template file not created")
        finally:
            sys.exit(3)

    def config_template(self):
        config=configparser.ConfigParser()
        config.add_section("main")
        config.add_section("tk")
        for i in self.defaults:
            config.set(*i)
        try:
            self.verbose("Creating config template.")
            with open(self.configtempfile, "w", encoding="utf-8") as conffile:
                config.write(conffile)
            self.verbose("Done. Rename it to {} to make it work.".format(os.path.basename(self.configfile)))
            if not self.args.template:
                sys.exit(0)
        except PermissionError:
            print("Can't write in folder. Check permissions. Config template file not generated.")
            if not self.args.template:
                sys.exit(3)
            else:
                err=1
                return err

    def lang_check(self, key):
        try:
            if key in self.lang.keys():
                if self.lang[key]!="":
                    return self.lang[key]
                else:
                    raise KeyError
        except KeyError:
            return self.english[key]

    def check_setting(self, section, setting, default):
        try:
            var=self.config.get(section, setting)
            self.verbose("Got {} {} from config file.".format(setting, var))
            err=0
        except (configparser.NoSectionError, configparser.NoOptionError):
            try:
                self.config.add_section(section)
            except configparser.NoSectionError:
                pass
            var=default
            self.verbose("No setting for {}. Using default {}.".format(setting, default))
        return var

    def verbose(self, text):
        if self.args.verbose:
            print(text)

    def start(self, args):
        self.config=configparser.ConfigParser()
        self.config.read(self.configfile)
        self.args=args
        if self.args.config:
            err=self.config_template()
        else:
            err=0
        if self.args.template:
            self.lang_template(err)
        for i in self.defaults:
            var=self.check_setting(*i)
            self.settings[i[0]][i[1]]=var
        if self.args.lang:
            self.verbose("Language overriden with {}.".format(self.args.lang))
            self.lang=self.init_lang(self.args.lang)
        else:
            self.lang=self.init_lang(self.settings["main"]["language"])
        if self.args.interface=="cli":
            self.gui=0
            self.verbose("Interface overriden with CLI.")
        elif self.args.interface=="tk":
            self.gui=1
            self.verbose("Interface overriden with Tk.")
        else:
            if self.settings["main"]["interface"]=="cli":
                self.gui=0
            elif self.settings["main"]["interface"]=="tk":
                self.gui=1
            elif not self.args.interface:
                    self.gui=1
        if self.gui==1:
            t=0
            try:
                self.verbose("Initializing Tk interface.")
                import tkinter
                t=self.init_tk(tkinter)
                if t:
                    raise ImportError
                self.print_method(self.lang_check("welcome"))
                self.start_tk()
            except ImportError:
                if t:
                    print(self.lang_check("tk_init_err"))
                else:
                    print(self.lang_check("tkinter_err"))
                print(self.lang_check("tk_err"))
                self.gui=0
        if self.gui==0 and sys.stdin.isatty() is True:
            self.verbose("Initializing CLI interface.")
            self.print_method(self.lang_check("welcome"))
            self.on_enter()
        else:
            sys.exit(1)

    def input_method(self):
        if self.gui==1:
            if self.entry.get()=="":
                return ""
            if self.tkhistory[len(self.tkhistory)-1]!=self.entry.get():
                del self.tkhistory[len(self.tkhistory)-1]
            msg=self.entry.get()
            self.entry.delete(0, "end")
            self.tkhistory.append(msg)
            self.tkhistory.append("")
            self.tkhistpos=len(self.tkhistory)-1
        if self.gui==0:
            msg=input()
        return msg
    
    def print_method(self, msg):
        if self.gui==1:
            self.out.config(state="normal")
            self.out.insert("end", msg+"\n")
            self.out.config(state="disabled")
            self.out.see("end")
        if self.gui==0:
            print("|"+msg)

    def receive(self):
        while 1:
            try:
                r,_,_=select.select([self.client],[self.client],[self.client])
                if r:
                    data=self.client.recv(self.bufsiz).decode(self.code)
                    if data=="":
                        self.client.close()
                        break
                    self.print_method(data)
            except (OSError, ValueError, ConnectionResetError):
                break

    def send(self, data):
        self.client.sendall(bytes(data, self.code))
    
    def exit_on_bind(self, event=""):
        self.exit_program(0)

    def exit_program(self, status):
        if self.client!= "":
            try:
                self.disconnect()
            except (NameError, BrokenPipeError):
                pass
        if self.gui==1:
            self.tk.destroy()
        sys.exit(status)

    def disconnect(self):
        self.client.close()
        self.print_method("|{} {}:{}".format(self.lang_check("dconn"), self.host, self.port))
        self.receive_thread.join()

    def on_enter(self, event=""):
        while 1:
            try:
                msg=self.input_method()
                if msg=="":
                    if self.gui==0:
                        continue
                    if self.gui==1:
                        break
                elif msg.split(" ", 3)[0]==":c":
                    try:
                        if len(msg.split(" ", 3))>3:
                            self.print_method(self.lang_check("tm_args"))
                        if self.client:
                            self.disconnect()
                        self.host=msg.split(" ", 3)[1]
                        self.port=int(msg.split(" ", 3)[2])
                        addr=(self.host, self.port)
                        self.client=socket.create_connection(addr)
                        self.receive_thread=threading.Thread(name="Receive", target=self.receive)
                        self.receive_thread.daemon=1
                        self.receive_thread.start()
                        self.print_method("|{} {}:{}".format(self.lang_check("conn"), self.host, self.port))
                    except (KeyboardInterrupt, EOFError):
                        self.exit_program(0)
                    except IndexError:
                        self.print_method(self.lang_check("tm_args"))
                    except ConnectionRefusedError:
                        self.print_method(self.lang_check("refused"))
                    except socket.gaierror:
                        self.print_method(self.lang_check("u_host"))
                    except OSError:
                        self.print_method(self.lang_check("nct_host"))
                    except (TypeError, ValueError, OverflowError):
                        self.print_method(self.lang_check("i_port"))
                elif msg==":dc":
                    if self.client!="":
                        self.disconnect()
                    else:
                        self.print_method(self.lang_check("n_conn"))
                elif msg==":h":
                    self.print_method(self.lang_check("help"))
                    self.print_method(":c $ip/dns $port - "+self.lang_check("help_c"))
                    self.print_method(":dc - "+self.lang_check("help_dc"))
                    self.print_method(":h - "+self.lang_check("help_h"))
                    self.print_method(":q - "+self.lang_check("help_q"))
                    try:
                        self.send(msg)
                    except (NameError, OSError, AttributeError):
                        pass
                    if self.gui==0:
                        self.print_method(":tl - "+self.lang_check("help_tl"))
                elif msg==":q":
                    self.exit_program(0)
                elif self.gui==0 and msg==":tl":
                    self.print_method(":ot - "+self.lang_check("t_limit"))
                else:
                    try:
                        self.send(msg)
                    except (NameError, OSError, AttributeError):
                        if msg.startswith(":"):
                            self.print_method("|{}'{}'".format(self.lang_check("u_comm"), msg))
                        else:
                            self.print_method(self.lang_check("n_conn"))
                if self.gui==1:
                    break
            except (KeyboardInterrupt, EOFError):
                self.exit_program(0)
            except BrokenPipeError:
                self.client.close()
                self.print_method(self.lang_check("conn_lost"))
                if self.gui==1:
                    break

if __name__=="__main__":
        arg=argparse.ArgumentParser(description="Simple chat client.", epilog="Command line arguments override config arguments, otherwise defaults will be used. In an event, where Tk interface cannot be initialized, a CLI interface will be started, otherwise exit code 1 will be returned. If given invalid argument, exit code 2 will be returned.")
        arg.add_argument("-i", "--interface", help="Select interface: CLI or Tk (default)")
        arg.add_argument("-l", "--lang", help="Set language (default builtin)")
        arg.add_argument("-v", "--verbose", action="store_true", help="Show debug info (in English only).")
        arg.add_argument("-c", "--config", action="store_true", help="Generate config template.")
        arg.add_argument("-t", "--template", action="store_true", help="Generate language template.")
        args=arg.parse_args()
        Client().start(args)
