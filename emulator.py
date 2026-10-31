import tkinter as tk
import os
import sys
import json
import base64
import getpass
import socket
import platform
import argparse
import re


class VFS:
    def __init__(self, data=None):
        if data is None:
            self.root = {"name": "/", "type": "dir", "children": []}
        else:
            self.root = self._decode_vfs(data)
        self.cwd = "/"
        self.prev_cwd = "/"

    def _decode_vfs(self, node):
        if node["type"] == "file" and "content" in node:
            if isinstance(node["content"], str):
                try:
                    node["content"] = base64.b64decode(node["content"])
                except Exception:
                    pass
        elif node["type"] == "dir" and "children" in node:
            for child in node["children"]:
                self._decode_vfs(child)
        return node

    def _encode_vfs(self, node):
        if node["type"] == "file" and "content" in node:
            if isinstance(node["content"], bytes):
                node["content"] = base64.b64encode(node["content"]).decode('utf-8')
        elif node["type"] == "dir" and "children" in node:
            for child in node["children"]:
                self._encode_vfs(child)
        return node

    def save_to_json(self, filepath):
        import copy
        data = copy.deepcopy(self.root)
        encoded_data = self._encode_vfs(data)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(encoded_data, f, indent=2, ensure_ascii=False)

    def _resolve(self, path):
        if not path or path == "~":
            return "/"
        if not path.startswith("/"):
            if self.cwd == "/":
                path = "/" + path
            else:
                path = self.cwd + "/" + path
        parts = []
        for p in path.split("/"):
            if p == "" or p == ".":
                continue
            elif p == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(p)
        return "/" + "/".join(parts) if parts else "/"

    def _find_node(self, path):
        if path == "/":
            return self.root
        parts = path.strip("/").split("/")
        node = self.root
        for part in parts:
            if node["type"] != "dir":
                return None
            found = None
            for child in node.get("children", []):
                if child["name"] == part:
                    found = child
                    break
            if found is None:
                return None
            node = found
        return node

    def list_dir(self, path=None):
        if path is None:
            path = self.cwd
        else:
            path = self._resolve(path)
        node = self._find_node(path)
        if node is None:
            return None, f"ls: cannot access '{path}': No such file or directory"
        if node["type"] != "dir":
            return [node["name"]], None
        return [c["name"] for c in node.get("children", [])], None

    def change_dir(self, path=None):
        if path is None or path == "~":
            target = "/"
        elif path == "-":
            target = self.prev_cwd
        else:
            target = self._resolve(path)
        node = self._find_node(target)
        if node is None:
            return f"cd: no such file or directory: {path}"
        if node["type"] != "dir":
            return f"cd: not a directory: {path}"
        self.prev_cwd = self.cwd
        self.cwd = target
        return None

    def make_dir(self, path):
        target = self._resolve(path)
        parts = target.strip("/").split("/")
        if not parts or (len(parts) == 1 and parts[0] == ""):
            return "mkdir: cannot create directory '/': File exists"
        parent_path = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"
        dir_name = parts[-1]
        parent = self._find_node(parent_path)
        if parent is None:
            return f"mkdir: cannot create directory '{path}': No such file or directory"
        if parent["type"] != "dir":
            return f"mkdir: cannot create directory '{path}': Not a directory"
        for child in parent.get("children", []):
            if child["name"] == dir_name:
                return f"mkdir: cannot create directory '{path}': File exists"
        parent.setdefault("children", []).append({
            "name": dir_name, "type": "dir", "children": []
        })
        return None

    def make_file(self, path, content=b""):
        target = self._resolve(path)
        parts = target.strip("/").split("/")
        if not parts or (len(parts) == 1 and parts[0] == ""):
            return "touch: cannot create file '/': Is a directory"
        parent_path = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"
        file_name = parts[-1]
        parent = self._find_node(parent_path)
        if parent is None:
            return f"touch: cannot create file '{path}': No such file or directory"
        if parent["type"] != "dir":
            return f"touch: cannot create file '{path}': Not a directory"
        for i, child in enumerate(parent.get("children", [])):
            if child["name"] == file_name:
                if child["type"] == "dir":
                    return f"touch: cannot create file '{path}': Is a directory"
                parent["children"][i]["content"] = content if isinstance(content, bytes) else content.encode('utf-8')
                return None
        parent.setdefault("children", []).append({
            "name": file_name,
            "type": "file",
            "content": content if isinstance(content, bytes) else content.encode('utf-8')
        })
        return None

    def read_file(self, path):
        target = self._resolve(path)
        node = self._find_node(target)
        if node is None:
            return None, f"cat: {path}: No such file or directory"
        if node["type"] != "file":
            return None, f"cat: {path}: Is a directory"
        content = node.get("content", b"")
        if isinstance(content, bytes):
            try:
                return content.decode('utf-8'), None
            except UnicodeDecodeError:
                return "[Binary file]", None
        return str(content), None


class Shell:
    def __init__(self, vfs):
        self.vfs = vfs
        self.username = getpass.getuser()
        self.hostname = socket.gethostname()
        self.running = True

    def get_prompt(self):
        return f"{self.username}@{self.hostname}:{self.vfs.cwd}$ "

    def expand_vars(self, text):
        def replace_var(match):
            var_name = match.group(1) or match.group(2)
            return os.environ.get(var_name, match.group(0))
        return re.sub(r'\$\{(\w+)\}|\$(\w+)', replace_var, text)

    def execute(self, line):
        line = line.strip()
        if not line:
            return ""
        line = self.expand_vars(line)
        parts = line.split()
        cmd = parts[0]
        args = parts[1:]

        if cmd == "exit":
            self.running = False
            return ""
        elif cmd == "ls":
            return self._cmd_ls(args)
        elif cmd == "cd":
            return self._cmd_cd(args)
        elif cmd == "uname":
            return self._cmd_uname(args)
        elif cmd == "clear":
            return "\x0c"
        elif cmd == "whoami":
            return self.username
        elif cmd == "mkdir":
            return self._cmd_mkdir(args)
        elif cmd == "touch":
            return self._cmd_touch(args)
        elif cmd == "cat":
            return self._cmd_cat(args)
        else:
            return f"{cmd}: command not found"

    def _cmd_ls(self, args):
        path = args[0] if args else None
        entries, err = self.vfs.list_dir(path)
        if err:
            return err
        return "  ".join(sorted(entries)) if entries else ""

    def _cmd_cd(self, args):
        path = args[0] if args else None
        err = self.vfs.change_dir(path)
        return err if err else ""

    def _cmd_uname(self, args):
        if "-a" in args:
            return (f"{platform.system()} {self.hostname} "
                    f"{platform.release()} {platform.version()} "
                    f"{platform.machine()}")
        return platform.system()

    def _cmd_mkdir(self, args):
        if not args:
            return "mkdir: missing operand"
        err = self.vfs.make_dir(args[0])
        return err if err else ""

    def _cmd_touch(self, args):
        if not args:
            return "touch: missing operand"
        err = self.vfs.make_file(args[0])
        return err if err else ""

    def _cmd_cat(self, args):
        if not args:
            return "cat: missing operand"
        content, err = self.vfs.read_file(args[0])
        if err:
            return err
        return content


class EmulatorGUI:
    def __init__(self, shell, startup_commands=None):
        self.shell = shell
        self.root = tk.Tk()
        self.root.title(
            f"\u042d\u043c\u0443\u043b\u044f\u0442\u043e\u0440 - "
            f"[{shell.username}@{shell.hostname}]"
        )
        self.root.configure(bg="black")
        self.root.geometry("800x500")

        self.text = tk.Text(
            self.root,
            bg="black",
            fg="lime",
            insertbackground="lime",
            font=("Consolas", 12),
            wrap=tk.WORD,
        )
        self.text.pack(fill=tk.BOTH, expand=True)

        self.text.bind("<Return>", self._on_enter)
        self.text.bind("<BackSpace>", self._on_backspace)
        self.text.bind("<Key>", self._on_key)

        if startup_commands:
            self.root.after(100, lambda: self._run_startup(startup_commands))
        else:
            self._show_prompt()

    def _show_prompt(self):
        prompt = self.shell.get_prompt()
        self.text.insert(tk.END, prompt)
        self.text.mark_set("input_start", "end-1c")
        self.text.mark_gravity("input_start", tk.LEFT)
        self.text.mark_set(tk.INSERT, "end-1c")
        self.text.see(tk.END)

    def _on_backspace(self, event):
        if self.text.compare(tk.INSERT, "<=", "input_start"):
            return "break"

    def _on_key(self, event):
        if event.keysym in ("BackSpace", "Return"):
            return
        nav = (
            "Left", "Right", "Up", "Down", "Home", "End",
            "Control_L", "Control_R", "Shift_L", "Shift_R",
            "Alt_L", "Alt_R", "Caps_Lock",
        )
        if event.keysym in nav:
            return
        if self.text.compare(tk.INSERT, "<", "input_start"):
            return "break"

    def _on_enter(self, event):
        line = self.text.get("input_start", "end-1c").strip()
        self.text.insert(tk.END, "\n")
        output = self.shell.execute(line)
        if not self.shell.running:
            self.root.destroy()
            return "break"
        if output == "\x0c":
            self.text.delete("1.0", tk.END)
        elif output:
            self.text.insert(tk.END, output + "\n")
        self._show_prompt()
        return "break"

    def _run_startup(self, commands):
        for cmd in commands:
            if not self.shell.running:
                break
            prompt = self.shell.get_prompt()
            self.text.insert(tk.END, prompt + cmd + "\n")
            output = self.shell.execute(cmd)
            if not self.shell.running:
                break
            if output == "\x0c":
                self.text.delete("1.0", tk.END)
            elif output:
                self.text.insert(tk.END, output + "\n")
        if self.shell.running:
            self._show_prompt()

    def run(self):
        self.root.mainloop()


def load_startup_script(path):
    commands = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                commands.append(line)
    return commands


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vfs", default=None)
    parser.add_argument("--script", default=None)
    args = parser.parse_args()

    print(f"  VFS папка:    {args.vfs}")
    print(f"  Папка скрипта: {args.script}")
    print(f"  User:        {getpass.getuser()}")
    print(f"  Host:        {socket.gethostname()}")

    vfs_data = None
    if args.vfs:
        with open(args.vfs, "r", encoding="utf-8") as f:
            vfs_data = json.load(f)

    vfs = VFS(vfs_data)
    shell = Shell(vfs)

    startup_commands = None
    if args.script:
        startup_commands = load_startup_script(args.script)

    gui = EmulatorGUI(shell, startup_commands)
    gui.run()


if __name__ == "__main__":
    main()