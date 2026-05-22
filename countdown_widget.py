"""桌面倒计时小工具 - 无边框 + 自定义背景 + 数字透明背景 + 等比例缩放"""

import tkinter as tk
from tkinter import colorchooser, filedialog
import json
import os
import traceback
from datetime import datetime, timedelta
from PIL import Image, ImageTk

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "countdown_settings.json")

DEFAULTS = {
    "target_date": "",
    "text_color": "#ffffff",
    "accent_color": "#00e5ff",
    "bg_color": "#111111",
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

        self.width = self.settings.get("window_width", 420)
        self.height = self.settings.get("window_height", 300)
        self.root.geometry(f"{self.width}x{self.height}")
        self.root.minsize(200, 140)

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

        # ---- 单一 Canvas 承载所有视觉内容 ----
        init_bg = self.settings.get("bg_color", "#111111")
        self.canvas = tk.Canvas(self.root, bg=init_bg, highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # ---- 标题栏 (拖拽区 + 按钮) ----
        self.title_bar = tk.Frame(self.root, bg=init_bg, bd=0, cursor="fleur")
        self.title_bar.place(x=0, y=0, relwidth=1, height=30)
        self.title_bar.bind("<Button-1>", self._drag_start)
        self.title_bar.bind("<B1-Motion>", self._drag_move)

        tk.Label(self.title_bar, text="Countdown", fg="#777777", bg=init_bg,
                 font=("Microsoft YaHei", 9)).pack(side="left", padx=(10, 0), pady=5)

        # 右侧按钮用 pack(side="right")，先 pack 的靠最右
        self.pin_btn = tk.Label(self.title_bar, text="📍", fg="#aaaaaa", bg=init_bg,
                                font=("", 10), cursor="hand2")
        self.pin_btn.pack(side="right", padx=1, pady=3)
        self.pin_btn.bind("<Button-1>", lambda e: self._toggle_pin())
        if self.settings.get("always_on_top"):
            self.pin_btn.configure(text="📌", fg="#ffffff")
        self._bind_hover(self.pin_btn, "#333333")

        for char, cmd in [("⚙", lambda e: self._open_settings()),
                          ("─", lambda e: self.root.iconify()),
                          ("✕", lambda e: self._on_close())]:
            btn = tk.Label(self.title_bar, text=char, fg="#aaaaaa", bg=init_bg,
                           font=("", 11 if char == "⚙" else 10), cursor="hand2")
            btn.pack(side="right", padx=1, pady=3)
            btn.bind("<Button-1>", cmd)
            self._bind_hover(btn, "#e81123" if char == "✕" else "#333333")

        # ---- 当前倒计时值 (内存状态) ----
        self._days_val = "--"
        self._hours_val = "--"
        self._mins_val = "--"
        self._secs_val = "--"
        self._target_info_text = ""

        # Canvas 文字对象 ID (用于每秒局部更新)
        self._days_id = None
        self._hours_id = None
        self._mins_id = None
        self._secs_id = None
        self._target_info_id = None

        # 背景/叠加层 PhotoImage 引用 (防 GC)
        self._bg_photo = None
        self._ov_photo = None

        # 首次绘制
        self.root.update_idletasks()
        self._draw_all_canvas()

        # ---- 边缘缩放 ----
        self._resize_edge = None
        self._resize_rx = 0
        self._resize_ry = 0
        self._resize_rw = 0
        self._resize_rh = 0
        self._resize_rx_win = 0
        self._resize_ry_win = 0
        self._edge_width = 6

        self.root.bind("<Motion>", self._on_motion)
        self.root.bind("<Button-1>", self._on_press)
        self.root.bind("<B1-Motion>", self._on_drag)
        self.root.bind("<ButtonRelease-1>", self._on_release)

        # 窗口大小变化 → 延迟重绘
        self._redraw_after_id = None
        self.root.bind("<Configure>", self._on_window_configure)

        # ---- 右键菜单 ----
        self._menu = None
        self.root.bind("<Button-3>", self._context_menu)
        self.root.bind("<Button-1>", lambda e: self._hide_menu(), add="+")

        self._tick()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    # ==================================================================
    # Canvas 绘制
    # ==================================================================

    def _draw_all_canvas(self):
        """全量重绘: 背景色 → 背景图(cover) → 叠加层 → 倒计时文字"""
        self.canvas.delete("all")
        w = self.root.winfo_width() or self.width
        h = self.root.winfo_height() or self.height
        bg_color = self.settings.get("bg_color", "#111111")
        self.canvas.configure(bg=bg_color)

        self._draw_bg_image(w, h)
        self._draw_overlay(w, h)
        self._draw_countdown_text(w, h)
        self._update_title_bar_bg(bg_color)

    def _draw_bg_image(self, w, h):
        """等比例缩放 + 居中裁剪 (cover 模式)，保留不透明度"""
        path = self.settings.get("bg_image", "")
        if not path or not os.path.exists(path):
            return
        try:
            img = Image.open(path)
            iw, ih = img.size
            # cover: 等比缩放填满窗口，超出部分居中裁剪
            scale = max(w / iw, h / ih)
            new_w = max(w, int(iw * scale))
            new_h = max(h, int(ih * scale))
            img = img.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - w) // 2
            top = (new_h - h) // 2
            img = img.crop((left, top, left + w, top + h))

            opacity = self.settings.get("bg_opacity", 40) / 100.0
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            r, g, b, a = img.split()
            a = a.point(lambda p: int(p * opacity))
            img = Image.merge("RGBA", (r, g, b, a))
            self._bg_photo = ImageTk.PhotoImage(img)
            self.canvas.create_image(0, 0, anchor="nw", image=self._bg_photo, tags="bg_img")
        except Exception:
            print("[背景加载失败]")
            traceback.print_exc()

    def _draw_overlay(self, w, h):
        ov = self.settings.get("overlay_opacity", 45)
        alpha = int(ov / 100 * 255)
        ov_img = Image.new("RGBA", (w, h), (0, 0, 0, alpha))
        self._ov_photo = ImageTk.PhotoImage(ov_img)
        self.canvas.create_image(0, 0, anchor="nw", image=self._ov_photo, tags="overlay")

    def _draw_countdown_text(self, w, h):
        """倒计时数字直接画在 canvas 上 —— 无 widget 背景，天然透明"""
        scale = self.settings["widget_scale"] / 100.0
        fs = int(52 * scale)
        ls = int(13 * scale)
        sep_fs = int(36 * scale)
        u = int(84 * scale)
        sep = int(8 * scale)

        total = u * 4 + sep * 3
        sx = (w - total) // 2
        block_h = fs + ls + 20
        avail_h = h - 30
        y = 30 + (avail_h - block_h) // 2

        ac = self.settings["accent_color"]
        tc = self.settings["text_color"]

        units = ["天", "时", "分", "秒"]
        vals = [self._days_val, self._hours_val, self._mins_val, self._secs_val]

        for i in range(4):
            x = sx + i * (u + sep)
            # 数字
            tid = self.canvas.create_text(
                x + u // 2, y + fs // 2,
                text=vals[i],
                font=("Consolas", fs, "bold"),
                fill=ac, anchor="center",
                tags="countdown",
            )
            if i == 0: self._days_id = tid
            elif i == 1: self._hours_id = tid
            elif i == 2: self._mins_id = tid
            else: self._secs_id = tid

            # 单位 (天/时/分/秒)
            self.canvas.create_text(
                x + u // 2, y + fs + 5 + ls // 2,
                text=units[i],
                font=("Microsoft YaHei", ls),
                fill=tc, anchor="center",
                tags="countdown",
            )

            # 分隔符 :
            if i < 3:
                self.canvas.create_text(
                    x + u + sep // 2, y + fs // 2 - 2,
                    text=":",
                    font=("Consolas", sep_fs),
                    fill=tc, anchor="center",
                    tags="countdown",
                )

        # 目标信息
        info_y = y + block_h + int(14 * scale)
        self._target_info_id = self.canvas.create_text(
            w // 2, info_y,
            text=self._target_info_text,
            font=("Microsoft YaHei", int(11 * scale)),
            fill=tc, anchor="n",
            tags="target_info",
        )

    def _update_countdown_values(self):
        """仅刷新数字文本，不重建 canvas"""
        if self._days_id:
            self.canvas.itemconfig(self._days_id, text=self._days_val)
        if self._hours_id:
            self.canvas.itemconfig(self._hours_id, text=self._hours_val)
        if self._mins_id:
            self.canvas.itemconfig(self._mins_id, text=self._mins_val)
        if self._secs_id:
            self.canvas.itemconfig(self._secs_id, text=self._secs_val)
        if self._target_info_id:
            self.canvas.itemconfig(self._target_info_id, text=self._target_info_text)

    def _update_title_bar_bg(self, color):
        try:
            self.title_bar.configure(bg=color)
        except Exception:
            pass

        def _recurse(parent):
            for child in parent.winfo_children():
                try:
                    child.configure(bg=color)
                except Exception:
                    pass
                _recurse(child)

        _recurse(self.title_bar)

    # ==================================================================
    # 窗口大小变化
    # ==================================================================

    def _on_window_configure(self, event):
        if event.widget != self.root:
            return
        if self._resize_edge:
            # 拖拽缩放中 — 等松手再重绘
            return
        new_w, new_h = event.width, event.height
        if new_w != self.width or new_h != self.height:
            self.width, self.height = new_w, new_h
            self._schedule_redraw()

    def _schedule_redraw(self):
        if self._redraw_after_id:
            self.root.after_cancel(self._redraw_after_id)
        self._redraw_after_id = self.root.after(80, self._do_redraw)

    def _do_redraw(self):
        self._redraw_after_id = None
        self._draw_all_canvas()

    # ==================================================================
    # 拖拽移动
    # ==================================================================

    def _drag_start(self, e):
        self._drag_dx = e.x_root - self.root.winfo_x()
        self._drag_dy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        if hasattr(self, "_drag_dx"):
            self.root.geometry(f"+{e.x_root - self._drag_dx}+{e.y_root - self._drag_dy}")

    # ==================================================================
    # 鼠标路由 (边缘检测 + 缩放)
    # ==================================================================

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
        if e.y < 30 and not (
            edge in ("nw", "ne")
            and e.x <= self._edge_width
            or e.x >= self.root.winfo_width() - self._edge_width
        ):
            edge = None
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

    # ==================================================================
    # Hover / 置顶
    # ==================================================================

    def _bind_hover(self, widget, hover_color, base_color=None):
        if base_color is None:
            base_color = self.settings.get("bg_color", "#111111")
        widget.bind("<Enter>", lambda e: widget.configure(bg=hover_color))
        widget.bind("<Leave>", lambda e: widget.configure(bg=base_color))

    def _toggle_pin(self):
        cur = self.root.attributes("-topmost")
        self.root.attributes("-topmost", not cur)
        self.settings["always_on_top"] = not cur
        save_settings(self.settings)
        self.pin_btn.configure(text="📌" if not cur else "📍",
                               fg="#ffffff" if not cur else "#aaaaaa")

    # ==================================================================
    # 设置窗口
    # ==================================================================

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

        # 标题栏 + 关闭按钮
        title_bar = tk.Frame(win, bg="#2a2a2a", height=28)
        title_bar.pack(fill="x", side="top")
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text="设置", fg="#aaaaaa", bg="#2a2a2a",
                 font=("Microsoft YaHei", 9)).place(x=10, y=5)
        close_btn = tk.Label(title_bar, text="✕", fg="#aaaaaa", bg="#2a2a2a",
                             font=("", 12), cursor="hand2")
        close_btn.place(relx=1.0, x=-6, y=2, width=24, height=24, anchor="ne")
        close_btn.bind("<Button-1>", lambda e: win.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.configure(fg="#ffffff", bg="#e81123"))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(fg="#aaaaaa", bg="#2a2a2a"))

        canvas = tk.Canvas(win, bg=bg_color, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=bg_color)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=340)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=(0, 8))

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

        # 背景颜色
        tk.Label(scroll_frame, text="背景颜色", fg=fg, bg=bg_color, font=fs).pack(anchor="w", **pad)
        bgc_btn = tk.Button(scroll_frame, text="　　", bg=self.settings.get("bg_color", "#111111"),
                            relief="flat", bd=1, cursor="hand2",
                            command=lambda: self._pick_bgcolor(win, bgc_btn))
        bgc_btn.pack(anchor="w", padx=12, pady=(0, 2))

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

    # ==================================================================
    # 设置辅助
    # ==================================================================

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

    def _pick_bgcolor(self, parent, btn):
        result = colorchooser.askcolor(
            color=self.settings.get("bg_color", "#111111"),
            title="选择背景颜色", parent=parent,
        )
        if result and result[1]:
            self.settings["bg_color"] = result[1]
            btn.configure(bg=result[1])
            save_settings(self.settings)
            self._draw_all_canvas()

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
        save_settings(self.settings)
        self._draw_all_canvas()

    # ==================================================================
    # 倒计时
    # ==================================================================

    def _tick(self):
        ts = self.settings.get("target_date", "")
        now = datetime.now()
        vals = ["--", "--", "--", "--"]
        info_text = ""

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

                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M",
                            "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"]:
                    try:
                        t = datetime.strptime(ts, fmt)
                        info_text = f"目标: {t.strftime('%Y年%m月%d日 %H:%M:%S')}"
                        break
                    except ValueError:
                        continue
            if vals == ["00", "00", "00", "00"]:
                info_text = "时间到！"
        else:
            info_text = "点击 ⚙ 设定目标日期"

        if (vals[0], vals[1], vals[2], vals[3], info_text) != \
           (self._days_val, self._hours_val, self._mins_val, self._secs_val, self._target_info_text):
            self._days_val, self._hours_val, self._mins_val, self._secs_val = vals
            self._target_info_text = info_text
            self._update_countdown_values()

        self.root.after(1000, self._tick)

    # ==================================================================
    # 右键菜单
    # ==================================================================

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

    # ==================================================================
    # 关闭
    # ==================================================================

    def _on_close(self):
        self.settings["window_x"] = self.root.winfo_x()
        self.settings["window_y"] = self.root.winfo_y()
        self.settings["window_width"] = self.root.winfo_width()
        self.settings["window_height"] = self.root.winfo_height()
        save_settings(self.settings)
        self.root.destroy()


if __name__ == "__main__":
    CountdownWidget()
