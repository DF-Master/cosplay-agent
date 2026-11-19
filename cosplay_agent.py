# -*- coding: utf-8 -*-
"""Cosplay Agent —— 给你的聊天消息套上 AI agent 的思考前缀。

全局热键唤出输入窗 -> 调用 DeepSeek 推断「（已思考X秒，已读取N个文件…）」
-> 写回目标输入框（默认不自动回车）。
"""

import ctypes
import http.client
import json
import os
import queue
import re
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from ctypes import wintypes
from urllib.parse import urlsplit

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
LOG_PATH = os.path.join(APP_DIR, "cosplay_agent.log")

DEFAULTS = {
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "hotkey": "ctrl+alt+shift+space",
    "timeout": 10,
    "auto_send": False,
}

SYSTEM_PROMPT = """你是「AI agent 运行日志」数据生成器。根据用户即将发出的一条消息，输出一段夹在消息最前面的执行摘要数据，模仿 AI agent 真实的工作痕迹。

第一步，反推工作量：想象一个 agent 为了说出这句话，之前实际做了哪些操作，再据此计数。
   - 「刚刚收到邮件，几分钟前」→ 要先打开邮箱看信、读邮件内容 → 打开 1 个网页、读取 1 个文件
   - 「这篇论文的方法我觉得可以再想想」→ 读过论文 → 读取 1~2 个文件
   - 「脚本改好了，跑出来是下面这个结果」→ 改过脚本并执行 → 编辑 1 个文件、执行 1~2 条命令
   - 「我在代码库里搜了一下，只有两处调用」→ 检索过 → 已搜索 2~4 个文件
   - 「报告初稿写完了，放在新文件里」→ 新建并写入 → 创建 1 个文件、编辑 1 个文件
   - 「这个报错你帮我看看」→ 查过资料 → 打开 1 个网页，可能读取 1 个文件
   - 纯寒暄、纯应答、纯情绪（「好的」「哈哈」「收到」）：所有计数为 0

字段（整数，没有就填 0，单类不超过 5）：
- thinking_seconds：0~180
- files_created：新建的文件数
- files_edited：修改、编辑过的文件数
- files_read：查看、读取过的文件数
- files_searched：检索、搜索过的文件数
- webpages_opened：打开过的网页数
- commands_run：执行过的命令数
- errors_fixed：遇到并修好的错误数（报错、失败、调不通）
- running：布尔值，仅当消息里明确出现「正在」「还在」「进行中」等表述时填 true，其余一律 false

thinking_seconds 分档：
- 4 字以内：0
- 5~10 字：1~5
- 一句话指令：5~30
- 两三句话、多个动作：20~60
- 明确的复杂任务（多文件、脚本、报告、方案）：60~180

约束：
- 字数档位优先：10 字以内的句子，即使描述完成了工作，thinking_seconds 一般不超过 15 秒，除非句子本身含多个步骤
- 单句只描述一件事时，非零类别不超过 2 个；长复合句（三个以上动作）才可以更多
  例：「简历更新了一版」→ 只记 已编辑 1 个文件；「代码跑通了」→ 已执行 1 条命令
- 非零类别通常 1~3 个，不要把所有字段都填上
- 数字要小而可信，与消息里体现的工作量相称
- 拿不准的类别填 0
- 不要复述消息原文，不要出现「模拟」「假装」「AI」等字样

只输出 JSON，不要 markdown 代码块：
{"thinking_seconds": 0, "files_created": 0, "files_edited": 0, "files_read": 0, "files_searched": 0, "webpages_opened": 0, "commands_run": 0, "errors_fixed": 0, "running": false}"""

# 配色（飞书风格）
C_BG = "#FFFFFF"
C_FIELD = "#F5F6F7"
C_TEXT = "#1F2329"
C_SUB = "#8F959E"
C_ACCENT = "#3370FF"
C_ACCENT_HOVER = "#245BDB"
C_GHOST = "#EFF0F1"
C_GHOST_HOVER = "#E4E6EB"
C_WARN = "#D97706"


# ---------------------------------------------------------------- 基础工具

def log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


def load_config():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (OSError, ValueError) as exc:
            log("配置文件读取失败: %s" % exc)
    if not cfg.get("api_key") or "填入" in cfg["api_key"]:
        cfg["api_key"] = os.environ.get("DEEPSEEK_API_KEY", "")
    if not cfg["api_key"].startswith("sk-"):
        cfg["api_key"] = ""
    return cfg


# ---------------------------------------------------------------- Win32

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                            ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.c_void_p]
user32.GetGUIThreadInfo.restype = wintypes.BOOL
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                 wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL,
                                  wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
WM_HOTKEY = 0x0312
HOTKEY_ID = 0xA17
KEYEVENTF_KEYUP = 0x0002
VK_MENU, VK_CONTROL, VK_RETURN, VK_V = 0x12, 0x11, 0x0D, 0x56

MOD_NAMES = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT, "shift": MOD_SHIFT,
    "win": MOD_WIN, "cmd": MOD_WIN, "super": MOD_WIN,
}
KEY_NAMES = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
    "backquote": 0xC0, "grave": 0xC0,
}
for _i in range(1, 13):
    KEY_NAMES["f%d" % _i] = 0x6F + _i


def parse_hotkey(spec):
    """'ctrl+alt+space' -> (mods, vk)"""
    mods, vk = 0, None
    for part in str(spec).lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in MOD_NAMES:
            mods |= MOD_NAMES[part]
        elif part in KEY_NAMES:
            vk = KEY_NAMES[part]
        elif len(part) == 1:
            vk = ord(part.upper())
        else:
            raise ValueError("无法识别的按键: %s" % part)
    if vk is None:
        raise ValueError("热键缺少主键: %s" % spec)
    return mods, vk


def hotkey_parts(spec):
    alias = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt",
             "shift": "Shift", "win": "Win", "cmd": "Win"}
    out = []
    for part in str(spec).split("+"):
        part = part.strip()
        if not part:
            continue
        name = part.lower()
        out.append(alias.get(name) or name.capitalize())
    return out


def window_title(hwnd):
    if not hwnd or not user32.IsWindow(hwnd):
        return ""
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def window_class(hwnd):
    if not hwnd or not user32.IsWindow(hwnd):
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def focused_class(hwnd):
    """取目标窗口所在线程当前拥有键盘焦点的控件类名。"""
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    if not tid:
        return ""
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    if not user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
        return ""
    return window_class(info.hwndFocus or info.hwndActive)


CHAT_HINTS = ("飞书", "lark", "微信", "wechat", "企业微信", "qq", "tim",
              "钉钉", "dingtalk", "telegram", "slack", "discord")
INPUT_CLASS_HINTS = ("edit", "richedit", "textbox", "textarea",
                     "scintilla", "chrome_widgetwin")


def looks_like_input(hwnd):
    """目标窗口是不是聊天类应用或带可编辑控件的窗口。"""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    probe = (window_title(hwnd) + " " + window_class(hwnd)).lower()
    if any(k in probe for k in CHAT_HINTS):
        return True
    return any(h in focused_class(hwnd).lower() for h in INPUT_CLASS_HINTS)


def force_foreground(hwnd):
    """绕过 Windows 前台锁定，把焦点还给目标窗口。"""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    # 先模拟一次 ALT 抬起，解除 SetForegroundWindow 的前台限制
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.08)
    return user32.GetForegroundWindow() == hwnd


def tap(vk):
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.012)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def paste_and_send(auto_send):
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    tap(VK_V)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.12)
    if auto_send:
        tap(VK_RETURN)


def hotkey_thread(spec, events):
    try:
        mods, vk = parse_hotkey(spec)
    except ValueError as exc:
        log(str(exc))
        events.put(("fatal", str(exc)))
        return
    if not user32.RegisterHotKey(None, HOTKEY_ID, mods, vk):
        msg = "热键 %s 注册失败，可能已被其他程序占用" % spec
        log(msg)
        events.put(("fatal", msg))
        return
    log("热键已就绪: %s" % spec)
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
            hwnd = int(user32.GetForegroundWindow() or 0)
            # 焦点信息只在目标还是前台时有效，必须此刻判定
            events.put(("show", hwnd, looks_like_input(hwnd)))
    user32.UnregisterHotKey(None, HOTKEY_ID)


# ---------------------------------------------------------------- 本地估算（API 失败时兜底）

FILE_RE = re.compile(r"[\w\-./\\]+\.(?:py|js|ts|tsx|jsx|md|txt|json|ya?ml|"
                     r"png|jpe?g|csv|xlsx?|docx?|pdf|zip|html?)\b", re.I)
URL_RE = re.compile(r"https?://\S+")
SHELL_WORDS = ("运行", "执行", "跑一下", "安装", "部署", "提交", "commit", "push")


def estimate_local(text):
    n = len(text.strip())
    if n <= 4:
        secs = 0
    else:
        secs = int(2 + n * 0.35)
    secs = max(0, min(240, secs))

    files = len(set(FILE_RE.findall(text)))
    web = len(set(URL_RE.findall(text)))
    lines = [ln for ln in text.splitlines() if ln.strip()]
    cmds = sum(1 for ln in lines if ln.strip().startswith(("$", ">", "#!")))
    cmds += sum(text.count(w) for w in SHELL_WORDS)
    cmds = min(20, cmds)

    return {
        "thinking_seconds": secs,
        "files_created": 0,
        "files_edited": 0,
        "files_read": files,
        "files_searched": 0,
        "webpages_opened": web,
        "commands_run": cmds,
        "errors_fixed": 0,
        "running": False,
    }


# ---------------------------------------------------------------- DeepSeek

_conn = None
_conn_lock = threading.Lock()


def _endpoint(cfg):
    parts = urlsplit(cfg["base_url"])
    host = parts.netloc or "api.deepseek.com"
    path = parts.path.rstrip("/") + "/chat/completions"
    return host, path


def ask_deepseek(cfg, text):
    global _conn
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.6,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + cfg["api_key"],
        "Connection": "keep-alive",
    }
    host, path = _endpoint(cfg)

    # 直连 DeepSeek，避免系统代理带来的额外往返；长连接复用
    for attempt in range(2):
        with _conn_lock:
            if _conn is None:
                _conn = http.client.HTTPSConnection(host, timeout=cfg["timeout"])
            conn = _conn
            try:
                conn.request("POST", path, body, headers)
                resp = conn.getresponse()
                raw = resp.read()
                status = resp.status
            except (http.client.HTTPException, OSError):
                try:
                    conn.close()
                except Exception:
                    pass
                _conn = None
                if attempt:
                    raise
                continue

        if status != 200:
            raise RuntimeError("DeepSeek HTTP %s: %s"
                               % (status, raw[:160].decode("utf-8", "ignore")))
        data = json.loads(raw.decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()
        data = sanitize(json.loads(content))
        if len(text.strip()) <= 4:  # 极短回复不消耗思考
            data["thinking_seconds"] = 0
        return data
    raise RuntimeError("DeepSeek 请求失败")


COUNT_FIELDS = ("files_created", "files_edited", "files_read",
                "files_searched", "webpages_opened", "commands_run",
                "errors_fixed")


def sanitize(data):
    def as_int(key, hi=20):
        try:
            return max(0, min(hi, int(float(data.get(key, 0)))))
        except (TypeError, ValueError):
            return 0

    clean = {"thinking_seconds": as_int("thinking_seconds", 240)}
    for key in COUNT_FIELDS:
        clean[key] = as_int(key, 5)
    clean["running"] = bool(data.get("running"))
    return clean


# ---------------------------------------------------------------- 组装前缀

def format_duration(secs):
    if secs < 60:
        return "\U0001f40b已思考%d秒" % secs
    minutes, rest = divmod(secs, 60)
    if rest:
        return "\U0001f40b已思考%d分%d秒" % (minutes, rest)
    return "\U0001f40b已思考%d分钟" % minutes


COUNT_LABELS = (
    ("files_created", "已创建%d个文件"),
    ("files_edited", "已编辑%d个文件"),
    ("files_read", "已读取%d个文件"),
    ("files_searched", "已搜索%d个文件"),
    ("webpages_opened", "已打开%d个网页"),
    ("commands_run", "已执行%d条命令"),
    ("errors_fixed", "已修复%d个错误"),
)


def build_prefix(data):
    parts = [format_duration(data["thinking_seconds"])]
    for key, label in COUNT_LABELS:
        if data.get(key):
            parts.append(label % data[key])
    if data.get("running"):
        parts.append("正在执行命令")
    return "\uff08" + "\uff0c".join(parts) + "\uff09"


# ---------------------------------------------------------------- 界面组件

def pick_font(root, size, weight="normal"):
    families = set(tkfont.families(root))
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"):
        if name in families:
            return (name, size, weight)
    return ("TkDefaultFont", size, weight)


class FlatButton(tk.Label):
    """扁平按钮，带 hover / pressed 反馈。"""

    def __init__(self, master, text, command, kind="primary", font=None):
        self.command = command
        self.enabled = True
        if kind == "primary":
            self._bg, self._hover, self._fg = C_ACCENT, C_ACCENT_HOVER, "#FFFFFF"
        else:
            self._bg, self._hover, self._fg = C_GHOST, C_GHOST_HOVER, "#4E5969"
        tk.Label.__init__(
            self, master, text=text, bg=self._bg, fg=self._fg,
            padx=16, pady=6, cursor="hand2", font=font,
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _on_enter(self, _):
        if self.enabled:
            self.configure(bg=self._hover)

    def _on_leave(self, _):
        if self.enabled:
            self.configure(bg=self._bg)

    def _on_click(self, _):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.configure(
            bg=self._bg if enabled else "#A9C0FF",
            fg=self._fg if enabled else "#FFFFFF",
            cursor="hand2" if enabled else "arrow",
        )


class KeyCap(tk.Label):
    def __init__(self, master, text, font):
        tk.Label.__init__(
            self, master, text=text, bg="#F2F3F5", fg="#646A73",
            padx=6, pady=1, font=font, bd=0,
        )


# ---------------------------------------------------------------- 主窗口

class Editor:
    SPIN = "\u25d0\u25d3\u25d1\u25d2"

    def __init__(self, root, cfg, events):
        self.root = root
        self.cfg = cfg
        self.events = events
        self.target_hwnd = 0
        self.target_is_input = False
        self.busy = False
        self.started_at = 0.0
        self._spin = 0

        f_body = pick_font(root, 11)
        f_small = pick_font(root, 9)
        f_title = pick_font(root, 10, "bold")
        f_cap = pick_font(root, 8)

        root.title("Agent 前缀")
        root.configure(bg=C_BG)
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", self.cancel)

        # 顶部强调条
        tk.Frame(root, bg=C_ACCENT, height=3).pack(fill="x")

        wrap = tk.Frame(root, bg=C_BG, padx=18, pady=14)
        wrap.pack(fill="both", expand=True)

        # 标题行
        head = tk.Frame(wrap, bg=C_BG)
        head.pack(fill="x", pady=(0, 10))
        tk.Label(head, text="\u273b", bg=C_BG, fg=C_ACCENT,
                 font=pick_font(root, 13, "bold")).pack(side="left")
        tk.Label(head, text="Agent 前缀", bg=C_BG, fg=C_TEXT,
                 font=f_title).pack(side="left", padx=(6, 0))

        caps = tk.Frame(head, bg=C_BG)
        caps.pack(side="right")
        for i, name in enumerate(hotkey_parts(cfg["hotkey"])):
            if i:
                tk.Label(caps, text="+", bg=C_BG, fg="#C0C4CC",
                         font=f_cap).pack(side="left", padx=2)
            KeyCap(caps, name, f_cap).pack(side="left")

        # 输入区（外层 1px 描边）
        field = tk.Frame(wrap, bg="#E4E6EB", padx=1, pady=1)
        self.text = tk.Text(
            field, width=61, height=6, wrap="word", bd=0,
            highlightthickness=0, bg=C_FIELD, fg=C_TEXT,
            insertbackground=C_ACCENT, padx=12, pady=10,
            font=f_body, undo=True, spacing1=2, spacing3=2,
        )
        self.text.pack(fill="both", expand=True)

        # 底部状态 + 按钮（先占位，避免被输入区挤压）
        bar = tk.Frame(wrap, bg=C_BG)
        bar.pack(side="bottom", fill="x", pady=(12, 0))
        field.pack(side="top", fill="both", expand=True)
        self.status = tk.Label(bar, text="", bg=C_BG, fg=C_SUB,
                               anchor="w", font=f_small)
        self.status.pack(side="left", fill="x", expand=True)

        self.send_btn = FlatButton(bar, "写入", self.submit, "primary",
                                   pick_font(root, 9, "bold"))
        self.send_btn.pack(side="right")
        self.cancel_btn = FlatButton(bar, "取消", self.cancel, "ghost", f_small)
        self.cancel_btn.pack(side="right", padx=(0, 8))

        self.text.bind("<Return>", self._on_return)
        self.text.bind("<Shift-Return>", lambda e: None)
        root.bind("<Escape>", lambda e: self.cancel())

        self.idle_hint = "Enter 写入飞书 · Shift+Enter 换行 · Esc 取消"
        self.set_status(self.idle_hint)

        root.update_idletasks()
        w, h = root.winfo_reqwidth(), root.winfo_reqheight()
        x = (root.winfo_screenwidth() - w) // 2
        y = int(root.winfo_screenheight() * 0.3)
        root.geometry("+%d+%d" % (x, y))
        root.withdraw()

    # -- 显示 / 关闭

    def show(self, target_hwnd, target_is_input=False):
        if self.busy:
            return
        self.target_hwnd = target_hwnd
        self.target_is_input = target_is_input
        self.text.delete("1.0", "end")
        self.set_status(self.idle_hint)
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.text.focus_force()

    def hide(self):
        self.root.withdraw()

    def cancel(self):
        if self.busy:
            return
        self.text.delete("1.0", "end")
        self.hide()

    def set_status(self, msg, color=C_SUB):
        self.status.configure(text=msg, fg=color)

    # -- 提交

    def _on_return(self, event):
        if event.state & 0x0001:  # Shift
            return None
        self.submit()
        return "break"

    def submit(self):
        if self.busy:
            return
        body = self.text.get("1.0", "end").strip()
        if not body:
            self.set_status("内容为空", C_WARN)
            return

        self.busy = True
        self.send_btn.set_enabled(False)
        self.started_at = time.time()
        self._spin = 0
        self.set_status("生成前缀中…")

        cfg = dict(self.cfg)
        threading.Thread(
            target=self._worker, args=(cfg, body, self.target_hwnd),
            daemon=True,
        ).start()
        self._tick()

    def _worker(self, cfg, body, hwnd):
        data, source = None, "deepseek"
        try:
            if cfg["api_key"]:
                data = ask_deepseek(cfg, body)
            else:
                source = "local"
        except Exception as exc:  # 任何异常都回退本地估算
            log("DeepSeek 调用失败，回退本地估算: %r" % exc)
            source = "local"
        if data is None:
            data = estimate_local(body)
        self.events.put(("result", body, data, source, hwnd))

    def _tick(self):
        if not self.busy:
            return
        self._spin = (self._spin + 1) % len(self.SPIN)
        elapsed = time.time() - self.started_at
        self.set_status("%s 生成前缀中  %.1fs" % (self.SPIN[self._spin], elapsed))
        self.root.after(110, self._tick)

    # -- 完成

    def finalize(self, body, data, source, hwnd):
        self.busy = False
        self.send_btn.set_enabled(True)
        self._deliver(build_prefix(data) + body, source, hwnd)

    def _deliver(self, full, source, hwnd):
        in_input = self.target_is_input

        self._copy(full)
        self.text.delete("1.0", "end")
        self.set_status(self.idle_hint)
        self.hide()
        self.root.update()

        if not in_input:
            log("目标窗口不是输入框，仅复制到剪贴板")
            return

        if not force_foreground(hwnd):
            log("无法激活目标窗口")
            return
        paste_and_send(bool(self.cfg.get("auto_send")))
        log("已写入 (%s, %d 字符)" % (source, len(full)))

    def _copy(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()


# ---------------------------------------------------------------- 入口

def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass

    # 单实例
    kernel32.CreateMutexW(None, False, "Local\\FeishuAgentPrefix")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return

    cfg = load_config()
    events = queue.Queue()
    root = tk.Tk()
    editor = Editor(root, cfg, events)

    def dispatch():
        try:
            while True:
                ev = events.get_nowait()
                kind = ev[0]
                if kind == "show":
                    editor.show(ev[1], ev[2])
                elif kind == "result":
                    editor.finalize(*ev[1:])
                elif kind == "fatal":
                    print(ev[1])
        except queue.Empty:
            pass
        root.after(60, dispatch)

    threading.Thread(
        target=hotkey_thread, args=(cfg["hotkey"], events), daemon=True
    ).start()

    print("飞书 AI Agent 前缀助手已启动，热键 %s"
          % "+".join(hotkey_parts(cfg["hotkey"])))
    dispatch()
    root.mainloop()


if __name__ == "__main__":
    main()
