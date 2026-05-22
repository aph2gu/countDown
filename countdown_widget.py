"""桌面倒计时小工具 - 无边框 + 自定义背景 + 颜色可调"""

import tkinter as tk
from tkinter import colorchooser, filedialog
import json
import os
import traceback
from datetime import datetime
from PIL import Image, ImageTk

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "countdown_settings.json")

DEFAULTS = {
    "target_date": "",
    "text_color": "#ffffff",
    "accent_color": "#00e5ff",
    "bg_image": "",
    "bg_opacity": 40,
    "overlay_opacity": 45,
    "widget_scale": 100,
    "always_on_top": False,
    "window_x": None,
    "window_y": None,
    "window_width": 420,
    "window_height": 300,
}


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_settings(data):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class CountdownWidget:
    def __init__(self):
        self.settings = {**DEFAULTS, **load_settings()}

        self.root = tk.Tk()
        self.root.title("Countdown")
        self.root.overrideredirect(True)
        self.root.configure(bg="#010101")
        self.root.attributes("-transparentcolor", "#010101")

        self.scale = self.settings["widget_scale"] / 100.0
        self.width = self.settings.get("window_width", 420)
        self.height = self.settings.get("window_height", 300)
        self.root.geometry(f"{self.width}x{self.height}")
        self.root.minsize(200, 140)

        # 窗口位置
        wx = self.settings.get("window_x")
        wy = self.settings.get("window_y")
        if wx is not None and wy is not None:
            self.root.geometry(f"+{wx}+{wy}")
        else:
            self.root.update_idletasks()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"+{(sw - self.width)//2}+{(sh - self.height)//2}")

        if self.settings.get("always_on_top"):
            self.root.attributes("-topmost", True)

        # ---- 单一 Canvas 承载所有内容 ----
        self.canvas = tk.Canvas(self.root, bg="#111111", highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # 背景图 + 叠加暗层 + 圆角遮罩（全在 canvas 上）
        self._bg_photo = None
        self._bg_img_obj = None
        self.root.update_idletasks()
        self._draw_all_canvas()

        # ---- 标题栏 (拖拽区) ----
        self.title_bar = tk.Frame(self.root, bg="#111111", bd=0, cursor="fleur")
        self.title_bar.place(x=0, y=0, relwidth=1, height=30)
        self.title_bar.bind("<Button-1>", self._drag_start)
        self.title_bar.bind("<B1-Motion>", self._drag_move)

        tk.Label(self.title_bar, text="Countdown", fg="#777777", bg="#111111",
                 font=("Microsoft YaHei", 9)).place(x=10, y=5)

        btn_frame = tk.Frame(self.title_bar, bg="#111111")
        btn_frame.place(relx=1.0, x=-108, y=3, width=100, height=24, anchor="ne")

        self.pin_btn = tk.Label(btn_frame, text="📍", fg="#aaaaaa", bg="#111111",
                                font=("", 10), cursor="hand2")
        self.pin_btn.pack(side="right", padx=1)
        self.pin_btn.bind("<Button-1>", lambda e: self._toggle_pin())
        if self.settings.get("always_on_top"):
            self.pin_btn.configure(text="📌", fg="#ffffff")
        self._bind_hover(self.pin_btn, "#333333")

        for char, cmd in [("⚙", lambda e: self._open_settings()),
                          ("─", lambda e: self.root.iconify()),
                          ("✕", lambda e: self._on_close())]:
            btn = tk.Label(btn_frame, text=char, fg="#aaaaaa", bg="#111111",
                           font=("", 11 if char == "⚙" else 10), cursor="hand2")
            btn.pack(side="right", padx=1)
            btn.bind("<Button-1>", cmd)
            self._bind_hover(btn, "#e81123" if char == "✕" else "#333333")

        # ---- 倒计时数字 (置于 canvas 上层) ----
        self.days_lbl = tk.Label(self.root, text="00", font=("Consolas", 52, "bold"),
                                 fg=self.settings["accent_color"], bg="#111111", bd=0)
        self.hours_lbl = tk.Label(self.root, text="00", font=("Consolas", 52, "bold"),
                                  fg=self.settings["accent_color"], bg="#111111", bd=0)
        self.mins_lbl = tk.Label(self.root, text="00", font=("Consolas", 52, "bold"),
                                 fg=self.settings["accent_color"], bg="#111111", bd=0)
        self.secs_lbl = tk.Label(self.root, text="00", font=("Consolas", 52, "bold"),
                                 fg=self.settings["accent_color"], bg="#111111", bd=0)
        self._unit_labels = []
        self._sep_labels = []

        self.target_info_lbl = tk.Label(
            self.root, text="", fg=self.settings["text_color"], bg="#111111",
            font=("Microsoft YaHei", int(11 * self.scale)), bd=0,
        )

        self._layout_countdown()

        # ---- 边缘缩放 ----
        self._resize_edge = None
        self._resize_rx = 0
        self._resize_ry = 0
        self._resize_rw = 0
        self._resize_rh = 0
        self._resize_rx_win = 0
        self._resize_ry_win = 0
        self._edge_width = 6

        # 所有鼠标事件用一个统一的处理器路由
        self.root.bind("<Motion>", self._on_motion)
        self.root.bind("<Button-1>", self._on_press)
        self.root.bind("<B1-Motion>", self._on_drag)
        self.root.bind("<ButtonRelease-1>", self._on_release)

        # ---- 右键菜单 ----
        self._menu = None
        self.root.bind("<Button-3>", self._context_menu)
        self.root.bind("<Button-1>", lambda e: self._hide_menu(), add="+")

        self._tick()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    # ====== Canvas 绘制 ======
    def _draw_all_canvas(self):
        """重绘 canvas 中所有内容：背景图、暗层、圆角"""
        self.canvas.delete("all")
        w = self.root.winfo_width() or self.width
        h = self.root.winfo_height() or self.height

        # 1. 背景图片
        path = self.settings.get("bg_image", "")
        if path and os.path.exists(path):
            try:
                img = Image.open(path).resize((w, h), Image.LANCZOS)
                opacity = self.settings.get("bg_opacity", 40) / 100.0
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                r, g, b, a = img.split()
                a = a.point(lambda p: int(p * opacity))
                img = Image.merge("RGBA", (r, g, b, a))
                self._bg_img_obj = img
                self._bg_photo = ImageTk.PhotoImage(img)
                self.canvas.create_image(0, 0, anchor="nw", image=self._bg_photo, tags="bg_img")
            except Exception:
                print("[背景加载失败]")
                traceback.print_exc()

        # 2. 叠加暗层 (canvas 半透明矩形)
        alpha = int(self.settings["overlay_opacity"] / 100 * 220)
        color = f"#{alpha:02x}{alpha:02x}{alpha:02x}"
        self.canvas.create_rectangle(0, 0, w, h, fill=color, outline="", tags="overlay")

        # 3. 圆角遮罩
        r = 16
        for x, y in [(0, 0), (w, 0), (0, h), (w, h)]:
            self.canvas.create_arc(
                x - r, y - r, x + r, y + r,
                start=0, extent=90, fill="#010101", outline="#010101", tags="corners",
            )

    # ====== 布局倒计时 ======
    def _layout_countdown(self):
        fs = int(52 * self.scale)
        ls = int(13 * self.scale)
        sep_fs = int(36 * self.scale)
        u = int(84 * self.scale)
        sep = int(8 * self.scale)

        total = u * 4 + sep * 3
        sx = (self.width - total) // 2
        block_h = fs + ls + 20
        avail_h = self.height - 30
        y = 30 + (avail_h - block_h) // 2

        self._countdown_y = y
        self._countdown_block_h = block_h

        tc = self.settings["text_color"]
        ac = self.settings["accent_color"]

        # 清理旧的辅助标签
        for lbl in self._unit_labels + self._sep_labels:
            lbl.destroy()
        self._unit_labels.clear()
        self._sep_labels.clear()

        data = [
            (self.days_lbl, "天"), (self.hours_lbl, "时"),
            (self.mins_lbl, "分"), (self.secs_lbl, "秒"),
        ]

        for i, (lbl, unit_text) in enumerate(data):
            x = sx + i * (u + sep)
            lbl.place_forget()
            lbl.configure(font=("Consolas", fs, "bold"), fg=ac, bg="#111111")
            lbl.place(x=x, y=y, width=u, height=fs + 10)

            ul = tk.Label(self.root, text=unit_text, fg=tc, bg="#111111", bd=0,
                          font=("Microsoft YaHei", ls))
            ul.place(x=x, y=y + fs + 5, width=u, height=ls + 8)
            self._unit_labels.append(ul)

            if i < 3:
                sl = tk.Label(self.root, text=":", fg=tc, bg="#111111", bd=0,
                              font=("Consolas", sep_fs))
                sl.place(x=x + u, y=y - 2, width=sep, height=sep_fs + 10)
                self._sep_labels.append(sl)

        # 目标信息标签
        info_y = y + block_h + int(14 * self.scale)
        self.target_info_lbl.place_forget()
        self.target_info_lbl.configure(
            font=("Microsoft YaHei", int(11 * self.scale)),
            fg=self.settings["text_color"], bg="#111111",
        )
        self.target_info_lbl.place(x=0, y=info_y, relwidth=1)

    # ====== 拖拽移动 ======
    def _drag_start(self, e):
        self._drag_dx = e.x_root - self.root.winfo_x()
        self._drag_dy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        if hasattr(self, "_drag_dx"):
            self.root.geometry(f"+{e.x_root - self._drag_dx}+{e.y_root - self._drag_dy}")

    # ====== 统一鼠标路由器 ======
    def _on_motion(self, e):
        if self._resize_edge:
            return
        edge = self._get_edge(e.x, e.y)
        cursors = {
            "nw": "size_nw_se", "se": "size_nw_se",
            "ne": "size_ne_sw", "sw": "size_ne_sw",
            "n": "size_ns", "s": "size_ns",
            "w": "size_we", "e": "size_we",
        }
        if edge:
            self.root.config(cursor=cursors.get(edge, "arrow"))
        elif e.y < 30:
            self.root.config(cursor="fleur")
        else:
            self.root.config(cursor="arrow")

    def _on_press(self, e):
        edge = self._get_edge(e.x, e.y)
        # 标题栏中间区域留给拖拽移动
        if e.y < 30 and not (edge in ("nw", "ne") and e.x <= self._edge_width or e.x >= self.root.winfo_width() - self._edge_width):
            edge = None  # 标题栏不触发边缘缩放
        if edge:
            self._resize_edge = edge
            self._resize_rx = e.x_root
            self._resize_ry = e.y_root
            self._resize_rw = self.root.winfo_width()
            self._resize_rh = self.root.winfo_height()
            self._resize_rx_win = self.root.winfo_x()
            self._resize_ry_win = self.root.winfo_y()
            return "break"

    def _on_drag(self, e):
        if not self._resize_edge:
            return
        edge = self._resize_edge
        dx = e.x_root - self._resize_rx
        dy = e.y_root - self._resize_ry
        new_w, new_h = self._resize_rw, self._resize_rh
        new_x, new_y = self._resize_rx_win, self._resize_ry_win
        min_w, min_h = 200, 140

        if "e" in edge:
            new_w = max(min_w, self._resize_rw + dx)
        if "s" in edge:
            new_h = max(min_h, self._resize_rh + dy)
        if "w" in edge:
            new_w = max(min_w, self._resize_rw - dx)
            new_x = self._resize_rx_win + (self._resize_rw - new_w)
        if "n" in edge:
            new_h = max(min_h, self._resize_rh - dy)
            new_y = self._resize_ry_win + (self._resize_rh - new_h)

        self.root.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")
        self.width, self.height = new_w, new_h

    def _on_release(self, e):
        if self._resize_edge:
            self._resize_edge = None
            self.root.update_idletasks()
            self._draw_all_canvas()
            self._layout_countdown()

    def _get_edge(self, ex, ey):
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        d = self._edge_width
        l, r, t, b = ex <= d, ex >= w - d, ey <= d, ey >= h - d
        if t and l: return "nw"
        if t and r: return "ne"
        if b and l: return "sw"
        if b and r: return "se"
        if t:       return "n"
        if b:       return "s"
        if l:       return "w"
        if r:       return "e"
        return None

    # ====== Hover ======
    def _bind_hover(self, widget, hover_color, base_color="#111111"):
        widget.bind("<Enter>", lambda e: widget.configure(bg=hover_color))
        widget.bind("<Leave>", lambda e: widget.configure(bg=base_color))

    # ====== 置顶 ======
    def _toggle_pin(self):
        cur = self.root.attributes("-topmost")
        self.root.attributes("-topmost", not cur)
        self.settings["always_on_top"] = not cur
        save_settings(self.settings)
        self.pin_btn.configure(text="📌" if not cur else "📍",
                               fg="#ffffff" if not cur else "#aaaaaa")

    # ====== 设置窗口 ======
    def _open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.geometry("360x440")
        win.resizable(False, False)
        win.configure(bg="#1e1e1e")
        win.attributes("-topmost", True)

        wx = self.root.winfo_x() + (self.width - 360) // 2
        wy = self.root.winfo_y() + (self.height - 440) // 2
        win.geometry(f"+{wx}+{wy}")

        fg, bg_color = "#cccccc", "#1e1e1e"
        entry_bg = "#2a2a2a"
        fs = ("Microsoft YaHei", 10)

        canvas = tk.Canvas(win, bg=bg_color, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=bg_color)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=340)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=8)

        def _mw(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        win.bind("<MouseWheel>", _mw)

        pad = {"padx": 12, "pady": 4}

        # 目标日期
        tk.Label(scroll_frame, text="目标日期", fg=fg, bg=bg_color, font=fs).pack(anchor="w", **pad)
        df = tk.Frame(scroll_frame, bg=bg_color)
        df.pack(fill="x", padx=12, pady=(0, 2))
        date_var = tk.StringVar(value=self.settings.get("target_date", ""))
        de = tk.Entry(df, textvariable=date_var, bg=entry_bg, fg=fg,
                      insertbackground=fg, font=fs, relief="flat", bd=6)
        de.pack(side="left", fill="x", expand=True)
        tk.Button(df, text="快速设定", bg="#333333", fg=fg, font=("", 9),
                  relief="flat", padx=8, pady=3, cursor="hand2",
                  command=lambda: self._quick_date(win, date_var)).pack(side="right", padx=(4, 0))

        # 文字颜色
        tk.Label(scroll_frame, text="文字颜色", fg=fg, bg=bg_color, font=fs).pack(anchor="w", **pad)
        tc_btn = tk.Button(scroll_frame, text="　　", bg=self.settings["text_color"],
                           relief="flat", bd=1, cursor="hand2",
                           command=lambda: self._pick_color(win, tc_btn, "text_color"))
        tc_btn.pack(anchor="w", padx=12, pady=(0, 2))

        # 强调色
        tk.Label(scroll_frame, text="强调色 (数字颜色)", fg=fg, bg=bg_color, font=fs).pack(anchor="w", **pad)
        ac_btn = tk.Button(scroll_frame, text="　　", bg=self.settings["accent_color"],
                           relief="flat", bd=1, cursor="hand2",
                           command=lambda: self._pick_color(win, ac_btn, "accent_color"))
        ac_btn.pack(anchor="w", padx=12, pady=(0, 2))

        # 背景图片
        tk.Label(scroll_frame, text="背景图片", fg=fg, bg=bg_color, font=fs).pack(anchor="w", **pad)
        bgf = tk.Frame(scroll_frame, bg=bg_color)
        bgf.pack(fill="x", padx=12, pady=(0, 2))
        tk.Button(bgf, text="选择图片...", bg="#333333", fg=fg, font=("", 9),
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  command=lambda: self._select_bg(win)).pack(side="left")
        tk.Button(bgf, text="清除", bg="#441111", fg="#cc6666", font=("", 9),
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  command=lambda: self._clear_bg(win)).pack(side="left", padx=(4, 0))

        # 背景不透明度
        tk.Label(scroll_frame, text="背景不透明度", fg=fg, bg=bg_color, font=fs).pack(anchor="w", **pad)
        tk.Scale(scroll_frame, from_=0, to=100, orient="horizontal", bg=bg_color,
                 fg=fg, troughcolor="#2a2a2a", highlightthickness=0, bd=0, length=300,
                 variable=tk.IntVar(value=self.settings["bg_opacity"]),
                 command=lambda v: self._on_slider("bg_opacity", int(v))).pack(fill="x", padx=12, pady=(0, 2))

        # 叠加层不透明度
        tk.Label(scroll_frame, text="叠加层不透明度", fg=fg, bg=bg_color, font=fs).pack(anchor="w", **pad)
        tk.Scale(scroll_frame, from_=0, to=100, orient="horizontal", bg=bg_color,
                 fg=fg, troughcolor="#2a2a2a", highlightthickness=0, bd=0, length=300,
                 variable=tk.IntVar(value=self.settings["overlay_opacity"]),
                 command=lambda v: self._on_slider("overlay_opacity", int(v))).pack(fill="x", padx=12, pady=(0, 2))

        # 窗口缩放
        tk.Label(scroll_frame, text="窗口缩放", fg=fg, bg=bg_color, font=fs).pack(anchor="w", **pad)
        tk.Scale(scroll_frame, from_=50, to=150, orient="horizontal", bg=bg_color,
                 fg=fg, troughcolor="#2a2a2a", highlightthickness=0, bd=0, length=300,
                 variable=tk.IntVar(value=self.settings["widget_scale"]),
                 command=lambda v: self._on_slider("widget_scale", int(v))).pack(fill="x", padx=12, pady=(0, 2))

        # 置顶
        top_var = tk.BooleanVar(value=self.settings.get("always_on_top", False))
        tk.Checkbutton(scroll_frame, text="窗口置顶", variable=top_var,
                       bg=bg_color, fg=fg, selectcolor="#2a2a2a", font=fs,
                       activebackground=bg_color, activeforeground=fg,
                       command=lambda: self._toggle_top(top_var.get())).pack(anchor="w", padx=12, pady=(2, 0))

        # 完成
        bf = tk.Frame(scroll_frame, bg=bg_color)
        bf.pack(fill="x", padx=12, pady=(12, 8))
        tk.Button(bf, text="完成", bg="#333333", fg=fg, font=fs,
                  relief="flat", padx=20, pady=5, cursor="hand2",
                  command=lambda: [self._save_date(date_var.get()), win.destroy()]).pack()

    # ====== 设置辅助 ======
    def _quick_date(self, parent, date_var):
        dlg = tk.Toplevel(parent)
        dlg.title("快速设定")
        dlg.geometry("300x200")
        dlg.configure(bg="#1e1e1e")
        dlg.attributes("-topmost", True)
        fg, bg_color = "#cccccc", "#1e1e1e"
        fs = ("Microsoft YaHei", 10)

        tk.Label(dlg, text="选择预设目标:", fg=fg, bg=bg_color, font=fs).pack(pady=10)
        for label, days in [("1 天后", 1), ("7 天后", 7), ("30 天后", 30),
                            ("100 天后", 100), ("365 天后", 365)]:
            tk.Button(dlg, text=label, bg="#333333", fg=fg, font=("", 9),
                      relief="flat", padx=16, pady=3, cursor="hand2",
                      command=lambda d=days: self._set_preset(dlg, date_var, d)).pack(fill="x", padx=40, pady=2)

        tk.Label(dlg, text="或输入具体日期:", fg=fg, bg=bg_color, font=fs).pack(pady=(10, 4))
        cv = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        tk.Entry(dlg, textvariable=cv, bg="#2a2a2a", fg=fg, insertbackground=fg,
                 font=fs, relief="flat").pack(fill="x", padx=40, pady=(0, 4))
        tk.Button(dlg, text="确认", bg="#333333", fg=fg, font=("", 9),
                  relief="flat", padx=16, pady=3, cursor="hand2",
                  command=lambda: (date_var.set(cv.get()), dlg.destroy())).pack(pady=(4, 0))

    def _set_preset(self, dlg, date_var, days):
        from datetime import timedelta
        target = datetime.now() + timedelta(days=days)
        target = target.replace(hour=0, minute=0, second=0, microsecond=0)
        date_var.set(target.strftime("%Y-%m-%d %H:%M:%S"))
        dlg.destroy()

    def _pick_color(self, parent, btn, key):
        result = colorchooser.askcolor(color=self.settings.get(key, "#ffffff"),
                                       title="选择颜色", parent=parent)
        if result and result[1]:
            self.settings[key] = result[1]
            btn.configure(bg=result[1])
            self._apply_colors()

    def _select_bg(self, parent):
        path = filedialog.askopenfilename(
            title="选择背景图片", parent=parent,
            filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.webp *.bmp")],
        )
        if path:
            self.settings["bg_image"] = path
            save_settings(self.settings)
            self._draw_all_canvas()

    def _clear_bg(self, parent):
        self.settings["bg_image"] = ""
        save_settings(self.settings)
        self._draw_all_canvas()

    def _on_slider(self, key, value):
        self.settings[key] = value
        self._draw_all_canvas()

    def _save_date(self, date_str):
        if date_str:
            self.settings["target_date"] = date_str
            save_settings(self.settings)

    def _toggle_top(self, flag):
        self.root.attributes("-topmost", flag)
        self.settings["always_on_top"] = flag
        self.pin_btn.configure(text="📌" if flag else "📍",
                               fg="#ffffff" if flag else "#aaaaaa")

    def _apply_colors(self):
        ac = self.settings["accent_color"]
        tc = self.settings["text_color"]
        for lbl in [self.days_lbl, self.hours_lbl, self.mins_lbl, self.secs_lbl]:
            lbl.configure(fg=ac)
        self.target_info_lbl.configure(fg=tc)
        save_settings(self.settings)

    # ====== 倒计时 ======
    def _tick(self):
        ts = self.settings.get("target_date", "")
        now = datetime.now()
        vals = ["--", "--", "--", "--"]

        if ts:
            target = None
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M",
                        "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    target = datetime.strptime(ts, fmt)
                    break
                except ValueError:
                    continue

            if target:
                diff = target - now
                if diff.total_seconds() > 0:
                    s = int(diff.total_seconds())
                    vals = [f"{s // 86400:02d}", f"{(s % 86400) // 3600:02d}",
                            f"{(s % 3600) // 60:02d}", f"{s % 60:02d}"]
                else:
                    vals = ["00", "00", "00", "00"]

        self.days_lbl.configure(text=vals[0])
        self.hours_lbl.configure(text=vals[1])
        self.mins_lbl.configure(text=vals[2])
        self.secs_lbl.configure(text=vals[3])

        # 目标信息
        if ts and vals[0] != "--":
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M",
                        "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    t = datetime.strptime(ts, fmt)
                    self.target_info_lbl.configure(
                        text=f"目标: {t.strftime('%Y年%m月%d日 %H:%M:%S')}")
                    break
                except ValueError:
                    continue
        elif vals == ["00", "00", "00", "00"]:
            self.target_info_lbl.configure(text="时间到！")
        else:
            self.target_info_lbl.configure(text="点击 ⚙ 设定目标日期")

        self.root.after(1000, self._tick)

    # ====== 右键菜单 ======
    def _context_menu(self, e):
        self._hide_menu()
        self._menu = tk.Toplevel(self.root)
        self._menu.overrideredirect(True)
        self._menu.attributes("-topmost", True)
        self._menu.configure(bg="#1e1e1e")

        for text, cmd in [("⚙ 设置", lambda: [self._hide_menu(), self._open_settings()]),
                          ("", None),
                          ("✕ 退出", lambda: [self._hide_menu(), self._on_close()])]:
            if not text:
                tk.Frame(self._menu, height=1, bg="#333333").pack(fill="x", padx=8)
            else:
                lbl = tk.Label(self._menu, text=text, fg="#cccccc", bg="#1e1e1e",
                               font=("Microsoft YaHei", 10), anchor="w",
                               padx=14, pady=6, cursor="hand2")
                lbl.pack(fill="x")
                lbl.bind("<Button-1>", lambda e, c=cmd: c())
                lbl.bind("<Enter>", lambda e, l=lbl: l.configure(bg="#333333"))
                lbl.bind("<Leave>", lambda e, l=lbl: l.configure(bg="#1e1e1e"))

        x = self.root.winfo_x() + e.x
        y = self.root.winfo_y() + e.y
        self._menu.geometry(f"+{x}+{y}")
        self._menu.focus_force()

    def _hide_menu(self):
        if self._menu:
            try:
                self._menu.destroy()
            except Exception:
                pass
            self._menu = None

    # ====== 关闭 ======
    def _on_close(self):
        self.settings["window_x"] = self.root.winfo_x()
        self.settings["window_y"] = self.root.winfo_y()
        self.settings["window_width"] = self.root.winfo_width()
        self.settings["window_height"] = self.root.winfo_height()
        save_settings(self.settings)
        self.root.destroy()


if __name__ == "__main__":
    CountdownWidget()
