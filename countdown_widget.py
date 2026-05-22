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
        self.root.overrideredirect(True)  # 无边框
        self.root.configure(bg="#010101")
        self.root.attributes("-transparentcolor", "#010101")

        self.scale = self.settings["widget_scale"] / 100.0
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
            cx = (sw - self.width) // 2
            cy = (sh - self.height) // 2
            self.root.geometry(f"+{cx}+{cy}")

        if self.settings.get("always_on_top"):
            self.root.attributes("-topmost", True)

        # ---- 背景 Canvas ----
        self.canvas = tk.Canvas(self.root, bg="#111111", highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # 圆角效果：用4个弧遮住四角
        self._draw_corners()

        # 确保窗口尺寸已生效，再加载背景
        self.root.update_idletasks()
        self._bg_photo = None
        self._bg_img_obj = None
        self._apply_bg()

        # ---- 叠加暗层 ----
        self.overlay_lbl = tk.Label(self.root, bg="#111111", bd=0)
        self.overlay_lbl.place(x=0, y=0, relwidth=1, relheight=1)
        self._update_overlay()
        self.canvas.tag_raise("corners")

        # ---- 标题栏 (拖拽区) ----
        self.title_bar = tk.Frame(self.root, bg="#111111", bd=0, cursor="fleur")
        self.title_bar.place(x=0, y=0, relwidth=1, height=30)
        self.title_bar.bind("<Button-1>", self._drag_start)
        self.title_bar.bind("<B1-Motion>", self._drag_move)

        tk.Label(self.title_bar, text="Countdown", fg="#777777", bg="#111111",
                 font=("Microsoft YaHei", 9)).place(x=10, y=5)

        # 按钮容器 (靠右)
        btn_frame = tk.Frame(self.title_bar, bg="#111111")
        btn_frame.place(relx=1.0, x=-108, y=3, width=100, height=24, anchor="ne")

        self.pin_btn = tk.Label(btn_frame, text="📍", fg="#aaaaaa", bg="#111111",
                                font=("", 10), cursor="hand2")
        self.pin_btn.pack(side="right", padx=1)
        self.pin_btn.bind("<Button-1>", lambda e: self._toggle_pin())
        if self.settings.get("always_on_top"):
            self.pin_btn.configure(text="📌", fg="#ffffff")
        self._bind_hover(self.pin_btn, "#333333")

        settings_btn = tk.Label(btn_frame, text="⚙", fg="#aaaaaa", bg="#111111",
                                font=("", 11), cursor="hand2")
        settings_btn.pack(side="right", padx=1)
        settings_btn.bind("<Button-1>", lambda e: self._open_settings())
        self._bind_hover(settings_btn, "#333333")

        min_btn = tk.Label(btn_frame, text="─", fg="#aaaaaa", bg="#111111",
                           font=("", 11), cursor="hand2")
        min_btn.pack(side="right", padx=1)
        min_btn.bind("<Button-1>", lambda e: self.root.iconify())
        self._bind_hover(min_btn, "#333333")

        close_btn = tk.Label(btn_frame, text="✕", fg="#aaaaaa", bg="#111111",
                             font=("", 10), cursor="hand2")
        close_btn.pack(side="right", padx=1)
        close_btn.bind("<Button-1>", lambda e: self._on_close())
        self._bind_hover(close_btn, "#e81123", "#333333")

        # ---- 倒计时显示 ----
        self.days_lbl = tk.Label(self.root, text="00", font=("Consolas", 52, "bold"),
                                 fg=self.settings["accent_color"], bg="#111111", bd=0)
        self.hours_lbl = tk.Label(self.root, text="00", font=("Consolas", 52, "bold"),
                                  fg=self.settings["accent_color"], bg="#111111", bd=0)
        self.mins_lbl = tk.Label(self.root, text="00", font=("Consolas", 52, "bold"),
                                 fg=self.settings["accent_color"], bg="#111111", bd=0)
        self.secs_lbl = tk.Label(self.root, text="00", font=("Consolas", 52, "bold"),
                                 fg=self.settings["accent_color"], bg="#111111", bd=0)

        self._layout_countdown()

        # 目标日期提示标签
        self.target_info_lbl = tk.Label(
            self.root, text="", fg=self.settings["text_color"], bg="#111111",
            font=("Microsoft YaHei", int(11 * self.scale)), bd=0,
        )
        info_y = self._countdown_y + self._countdown_block_h + int(14 * self.scale)
        self.target_info_lbl.place(x=0, y=info_y, relwidth=1)

        # ---- 边缘缩放 ----
        self._resize_edge = None
        self._resize_x = 0
        self._resize_y = 0
        self._resize_w = 0
        self._resize_h = 0
        self._edge_width = 6

        self.root.bind("<Motion>", self._on_edge_motion)
        self.root.bind("<Button-1>", self._on_edge_press, add=True)
        self.root.bind("<B1-Motion>", self._on_edge_drag, add=True)
        self.root.bind("<ButtonRelease-1>", self._on_edge_release, add=True)

        # ---- 右键菜单 ----
        self._menu = None
        self.root.bind("<Button-3>", self._context_menu)
        self.root.bind("<Button-1>", lambda e: self._hide_menu())

        self._tick()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    # ====== 布局 ======
    def _layout_countdown(self):
        fs = int(52 * self.scale)
        ls = int(13 * self.scale)
        sep_fs = int(36 * self.scale)
        u = int(84 * self.scale)
        sep = int(8 * self.scale)

        total = u * 4 + sep * 3
        sx = (self.width - total) // 2
        # 垂直居中：标题栏30px，剩余空间居中倒计时区块
        block_h = fs + ls + 20  # 数值 + 标签 + 间距
        avail_h = self.height - 30
        y = 30 + (avail_h - block_h) // 2

        self._countdown_y = y
        self._countdown_block_h = block_h

        tc = self.settings["text_color"]
        ac = self.settings["accent_color"]

        labels = [
            (self.days_lbl, "天"), (self.hours_lbl, "时"),
            (self.mins_lbl, "分"), (self.secs_lbl, "秒"),
        ]

        for i, (lbl, unit_text) in enumerate(labels):
            x = sx + i * (u + sep)
            lbl.place_forget()
            lbl.configure(font=("Consolas", fs, "bold"), fg=ac, bg="#111111")
            lbl.place(x=x, y=y, width=u, height=fs + 10)

            unit_lbl = tk.Label(self.root, text=unit_text,
                                fg=tc, bg="#111111", bd=0,
                                font=("Microsoft YaHei", ls))
            unit_lbl.place(x=x, y=y + fs + 5, width=u, height=ls + 8)

            if i < 3:
                sep_lbl = tk.Label(self.root, text=":", fg=tc, bg="#111111", bd=0,
                                   font=("Consolas", sep_fs))
                sep_lbl.place(x=x + u, y=y - 2, width=sep, height=sep_fs + 10)

    # ====== 背景 ======
    def _apply_bg(self):
        self.canvas.delete("bg_img")
        path = self.settings.get("bg_image", "")
        if not path or not os.path.exists(path):
            return
        try:
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w < 10 or h < 10:
                w, h = self.width, self.height
            img = Image.open(path).resize((w, h), Image.LANCZOS)
            opacity = self.settings.get("bg_opacity", 40) / 100.0
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            # 对整个图像应用不透明度
            r, g, b, a = img.split()
            a = a.point(lambda p: int(p * opacity))
            img = Image.merge("RGBA", (r, g, b, a))
            self._bg_img_obj = img
            self._bg_photo = ImageTk.PhotoImage(img)
            self.canvas.create_image(0, 0, anchor="nw", image=self._bg_photo, tags="bg_img")
        except Exception:
            print("[背景加载失败]")
            traceback.print_exc()

    def _update_overlay(self):
        alpha = int(self.settings["overlay_opacity"] / 100 * 220)
        self.overlay_lbl.configure(bg=f"#{alpha:02x}{alpha:02x}{alpha:02x}")

    # ====== 圆角遮罩 ======
    def _draw_corners(self):
        self.canvas.delete("corners")
        r = 16
        w, h = self.width, self.height
        for x, y in [(0, 0), (w, 0), (0, h), (w, h)]:
            self.canvas.create_arc(
                x - r, y - r, x + r, y + r,
                start=0, extent=90, fill="#010101", outline="#010101",
                tags="corners",
            )

    # ====== 拖拽 ======
    def _drag_start(self, e):
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    # ====== Hover 效果 ======
    def _bind_hover(self, widget, hover_color, base_color="#111111"):
        widget.bind("<Enter>", lambda e: widget.configure(bg=hover_color))
        widget.bind("<Leave>", lambda e: widget.configure(bg=base_color))

    # ====== 置顶 ======
    def _toggle_pin(self):
        cur = self.root.attributes("-topmost")
        self.root.attributes("-topmost", not cur)
        self.settings["always_on_top"] = not cur
        save_settings(self.settings)
        if not cur:
            self.pin_btn.configure(text="📌", fg="#ffffff")
        else:
            self.pin_btn.configure(text="📍", fg="#aaaaaa")

    # ====== 设置窗口 ======
    def _open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.geometry("360x440")
        win.resizable(False, False)
        win.configure(bg="#1e1e1e")
        win.attributes("-topmost", True)

        # 居中于主窗口
        wx = self.root.winfo_x() + (self.width - 360) // 2
        wy = self.root.winfo_y() + (self.height - 440) // 2
        win.geometry(f"+{wx}+{wy}")

        fg = "#cccccc"
        bg = "#1e1e1e"
        entry_bg = "#2a2a2a"
        fs = ("Microsoft YaHei", 10)

        # 滚动区域
        canvas = tk.Canvas(win, bg=bg, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=bg)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=340)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=8)

        # 鼠标滚轮支持
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        win.bind("<MouseWheel>", _on_mousewheel)
        # 当鼠标在 canvas 上时也绑定
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        pad = {"padx": 12, "pady": 4}

        # --- 目标日期 ---
        tk.Label(scroll_frame, text="目标日期", fg=fg, bg=bg, font=fs).pack(anchor="w", **pad)
        date_frame = tk.Frame(scroll_frame, bg=bg)
        date_frame.pack(fill="x", padx=12, pady=(0, 2))

        date_var = tk.StringVar(value=self.settings.get("target_date", ""))
        date_entry = tk.Entry(date_frame, textvariable=date_var, bg=entry_bg,
                              fg=fg, insertbackground=fg, font=fs,
                              relief="flat", bd=6)
        date_entry.pack(side="left", fill="x", expand=True)

        tk.Button(date_frame, text="快速设定",
                  bg="#333333", fg=fg, font=("", 9), relief="flat", bd=0,
                  padx=8, pady=3, cursor="hand2",
                  command=lambda: self._quick_date(win, date_var)).pack(side="right", padx=(4, 0))

        # --- 文字颜色 ---
        tk.Label(scroll_frame, text="文字颜色", fg=fg, bg=bg, font=fs).pack(anchor="w", **pad)
        tc_btn = tk.Button(scroll_frame, text="　　", bg=self.settings["text_color"],
                           relief="flat", bd=1, cursor="hand2",
                           command=lambda: self._pick_color_entry(win, tc_btn, "text_color"))
        tc_btn.pack(anchor="w", padx=12, pady=(0, 2))

        # --- 强调色 ---
        tk.Label(scroll_frame, text="强调色 (数字颜色)", fg=fg, bg=bg, font=fs).pack(anchor="w", **pad)
        ac_btn = tk.Button(scroll_frame, text="　　", bg=self.settings["accent_color"],
                           relief="flat", bd=1, cursor="hand2",
                           command=lambda: self._pick_color_entry(win, ac_btn, "accent_color"))
        ac_btn.pack(anchor="w", padx=12, pady=(0, 2))

        # --- 背景图片 ---
        tk.Label(scroll_frame, text="背景图片", fg=fg, bg=bg, font=fs).pack(anchor="w", **pad)
        bg_f = tk.Frame(scroll_frame, bg=bg)
        bg_f.pack(fill="x", padx=12, pady=(0, 2))
        tk.Button(bg_f, text="选择图片...", bg="#333333", fg=fg, font=("", 9),
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  command=lambda: self._select_bg(win)).pack(side="left")
        tk.Button(bg_f, text="清除", bg="#441111", fg="#cc6666", font=("", 9),
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  command=lambda: self._clear_bg(win)).pack(side="left", padx=(4, 0))

        # --- 背景不透明度 ---
        tk.Label(scroll_frame, text="背景不透明度", fg=fg, bg=bg, font=fs).pack(anchor="w", **pad)
        bg_op_scale = tk.Scale(scroll_frame, from_=0, to=100, orient="horizontal",
                               bg=bg, fg=fg, troughcolor="#2a2a2a",
                               highlightthickness=0, bd=0, length=300,
                               variable=tk.IntVar(value=self.settings["bg_opacity"]),
                               command=lambda v: self._on_opacity_change("bg_opacity", int(v)))
        bg_op_scale.pack(fill="x", padx=12, pady=(0, 2))

        # --- 叠加层不透明度 ---
        tk.Label(scroll_frame, text="叠加层不透明度", fg=fg, bg=bg, font=fs).pack(anchor="w", **pad)
        ov_op_scale = tk.Scale(scroll_frame, from_=0, to=100, orient="horizontal",
                               bg=bg, fg=fg, troughcolor="#2a2a2a",
                               highlightthickness=0, bd=0, length=300,
                               variable=tk.IntVar(value=self.settings["overlay_opacity"]),
                               command=lambda v: self._on_opacity_change("overlay_opacity", int(v)))
        ov_op_scale.pack(fill="x", padx=12, pady=(0, 2))

        # --- 窗口缩放 ---
        tk.Label(scroll_frame, text="窗口缩放", fg=fg, bg=bg, font=fs).pack(anchor="w", **pad)
        scale_scale = tk.Scale(scroll_frame, from_=50, to=150, orient="horizontal",
                               bg=bg, fg=fg, troughcolor="#2a2a2a",
                               highlightthickness=0, bd=0, length=300,
                               variable=tk.IntVar(value=self.settings["widget_scale"]),
                               command=lambda v: self._on_scale_change(int(v)))
        scale_scale.pack(fill="x", padx=12, pady=(0, 2))

        # --- 置顶 ---
        top_var = tk.BooleanVar(value=self.settings.get("always_on_top", False))
        tk.Checkbutton(scroll_frame, text="窗口置顶", variable=top_var,
                       bg=bg, fg=fg, selectcolor="#2a2a2a", font=fs,
                       activebackground=bg, activeforeground=fg,
                       command=lambda: self._toggle_top(top_var.get())).pack(anchor="w", padx=12, pady=(2, 0))

        # --- 按钮区 ---
        btn_frame = tk.Frame(scroll_frame, bg=bg)
        btn_frame.pack(fill="x", padx=12, pady=(12, 8))
        tk.Button(btn_frame, text="完成", bg="#333333", fg=fg, font=fs,
                  relief="flat", padx=20, pady=5, cursor="hand2",
                  command=lambda: [self._save_from_ui(win, date_var), win.destroy()]).pack()

    def _quick_date(self, parent, date_var):
        """快速设定日期对话框"""
        dlg = tk.Toplevel(parent)
        dlg.title("快速设定")
        dlg.geometry("300x200")
        dlg.configure(bg="#1e1e1e")
        dlg.attributes("-topmost", True)

        fg = "#cccccc"
        bg = "#1e1e1e"
        fs = ("Microsoft YaHei", 10)

        tk.Label(dlg, text="选择预设目标:", fg=fg, bg=bg, font=fs).pack(pady=10)

        presets = [
            ("1 天后", 1),
            ("7 天后", 7),
            ("30 天后", 30),
            ("100 天后", 100),
            ("365 天后", 365),
        ]

        for label, days in presets:
            btn = tk.Button(dlg, text=label, bg="#333333", fg=fg, font=("", 9),
                            relief="flat", padx=16, pady=3, cursor="hand2",
                            command=lambda d=days: self._set_preset(dlg, parent, date_var, d))
            btn.pack(fill="x", padx=40, pady=2)

        tk.Label(dlg, text="或输入具体日期:", fg=fg, bg=bg, font=fs).pack(pady=(10, 4))
        custom_var = tk.StringVar()
        entry = tk.Entry(dlg, textvariable=custom_var, bg="#2a2a2a",
                         fg=fg, insertbackground=fg, font=fs, relief="flat")
        entry.pack(fill="x", padx=40, pady=(0, 4))
        entry.insert(0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        tk.Button(dlg, text="确认", bg="#333333", fg=fg, font=("", 9),
                  relief="flat", padx=16, pady=3, cursor="hand2",
                  command=lambda: [setattr(date_var, 'set', date_var.set),
                                   date_var.set(custom_var.get()),
                                   dlg.destroy()]).pack(pady=(4, 0))

    def _set_preset(self, dlg, parent, date_var, days):
        from datetime import timedelta
        target = datetime.now() + timedelta(days=days)
        target = target.replace(hour=0, minute=0, second=0, microsecond=0)
        date_var.set(target.strftime("%Y-%m-%d %H:%M:%S"))
        dlg.destroy()

    def _pick_color_entry(self, parent, btn, key):
        result = colorchooser.askcolor(
            color=self.settings.get(key, "#ffffff"),
            title="选择颜色",
            parent=parent,
        )
        if result and result[1]:
            self.settings[key] = result[1]
            btn.configure(bg=result[1])
            self._apply_colors()

    def _select_bg(self, parent):
        path = filedialog.askopenfilename(
            title="选择背景图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.webp *.bmp")],
            parent=parent,
        )
        if path:
            self.settings["bg_image"] = path
            save_settings(self.settings)
            self._apply_bg()

    def _clear_bg(self, parent):
        self.settings["bg_image"] = ""
        self.canvas.delete("bg_img")
        self._bg_photo = None

    def _on_opacity_change(self, key, value):
        self.settings[key] = value
        if key == "bg_opacity":
            self._apply_bg()
        elif key == "overlay_opacity":
            self._update_overlay()

    def _on_scale_change(self, value):
        self.settings["widget_scale"] = value

    def _toggle_top(self, flag):
        self.root.attributes("-topmost", flag)
        self.settings["always_on_top"] = flag
        if flag:
            self.pin_btn.configure(text="📌", fg="#ffffff")
        else:
            self.pin_btn.configure(text="📍", fg="#aaaaaa")

    def _save_from_ui(self, win, date_var):
        self.settings["target_date"] = date_var.get()
        save_settings(self.settings)
        self._apply_colors()

    def _apply_colors(self):
        tc = self.settings["text_color"]
        ac = self.settings["accent_color"]
        for lbl in [self.days_lbl, self.hours_lbl, self.mins_lbl, self.secs_lbl]:
            lbl.configure(fg=ac)
        self.target_info_lbl.configure(fg=tc)

    # ====== 倒计时 ======
    def _tick(self):
        ts = self.settings.get("target_date", "")
        now = datetime.now()

        vals = ["--", "--", "--", "--"]
        if ts:
            try:
                target = None
                for fmt in [
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M",
                    "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d",
                ]:
                    try:
                        target = datetime.strptime(ts, fmt)
                        break
                    except ValueError:
                        continue

                if target:
                    diff = target - now
                    if diff.total_seconds() > 0:
                        s = int(diff.total_seconds())
                        vals = [
                            f"{s // 86400:02d}",
                            f"{(s % 86400) // 3600:02d}",
                            f"{(s % 3600) // 60:02d}",
                            f"{s % 60:02d}",
                        ]
                    else:
                        vals = ["00", "00", "00", "00"]
            except Exception:
                pass

        self.days_lbl.configure(text=vals[0])
        self.hours_lbl.configure(text=vals[1])
        self.mins_lbl.configure(text=vals[2])
        self.secs_lbl.configure(text=vals[3])

        # 更新目标日期信息
        if ts and vals[0] != "--":
            try:
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M",
                            "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"]:
                    try:
                        t = datetime.strptime(ts, fmt)
                        self.target_info_lbl.configure(
                            text=f"目标: {t.strftime('%Y年%m月%d日 %H:%M:%S')}"
                        )
                        break
                    except ValueError:
                        continue
            except Exception:
                self.target_info_lbl.configure(text="")
        elif vals[0] == "00" and vals[1] == "00" and vals[2] == "00" and vals[3] == "00":
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

        items = [
            ("⚙ 设置", lambda: [self._hide_menu(), self._open_settings()]),
            ("", None),
            ("✕ 退出", lambda: [self._hide_menu(), self._on_close()]),
        ]

        for text, cmd in items:
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
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.settings["window_x"] = x
        self.settings["window_y"] = y
        self.settings["window_width"] = self.root.winfo_width()
        self.settings["window_height"] = self.root.winfo_height()
        save_settings(self.settings)
        self.root.destroy()

    # ====== 边缘缩放 ======
    def _get_edge(self, ex, ey):
        """检测鼠标在窗口边缘的位置，返回方向字符串或 None"""
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        d = self._edge_width
        l = ex <= d
        r = ex >= w - d
        t = ey <= d
        b = ey >= h - d
        if t and l:    return "nw"
        if t and r:    return "ne"
        if b and l:    return "sw"
        if b and r:    return "se"
        if t:          return "n"
        if b:          return "s"
        if l:          return "w"
        if r:          return "e"
        return None

    def _on_edge_motion(self, e):
        if self._resize_edge:
            return
        edge = self._get_edge(e.x, e.y)
        cursors = {
            "nw": "size_nw_se", "se": "size_nw_se",
            "ne": "size_ne_sw", "sw": "size_ne_sw",
            "n": "size_ns", "s": "size_ns",
            "w": "size_we", "e": "size_we",
        }
        cursor = cursors.get(edge, "fleur" if e.y < 30 else "arrow")
        if not edge and e.y < 30:
            cursor = "fleur"
        self.root.config(cursor=cursor)

    def _on_edge_press(self, e):
        edge = self._get_edge(e.x, e.y)
        # 标题栏区域 (顶部非边缘区) 留给拖拽移动
        if edge and not (e.y < 30 and edge in ("n", "ne", "nw") and e.y <= self._edge_width):
            pass
        if edge:
            # 标题栏中间区域留给拖拽移动
            if e.y <= 30 and edge == "n":
                return
            self._resize_edge = edge
            self._resize_x = e.x_root
            self._resize_y = e.y_root
            self._resize_w = self.root.winfo_width()
            self._resize_h = self.root.winfo_height()
            return "break"

    def _on_edge_drag(self, e):
        if not self._resize_edge:
            return
        dx = e.x_root - self._resize_x
        dy = e.y_root - self._resize_y
        edge = self._resize_edge
        new_w = self._resize_w
        new_h = self._resize_h
        new_x = self.root.winfo_x()
        new_y = self.root.winfo_y()
        min_w, min_h = 200, 140

        if "e" in edge:
            new_w = max(min_w, self._resize_w + dx)
        if "s" in edge:
            new_h = max(min_h, self._resize_h + dy)
        if "w" in edge:
            new_x = self._resize_x + dx
            new_w = max(min_w, self._resize_w - dx)
            if new_w == min_w:
                new_x = self._resize_x + self._resize_w - min_w
        if "n" in edge:
            new_y = self._resize_y + dy
            new_h = max(min_h, self._resize_h - dy)
            if new_h == min_h:
                new_y = self._resize_y + self._resize_h - min_h

        self.root.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")
        self.width = new_w
        self.height = new_h

    def _on_edge_release(self, e):
        if self._resize_edge:
            self._resize_edge = None
            self._relayout()

    def _relayout(self):
        """窗口大小变化后重建布局"""
        self.root.update_idletasks()
        self.canvas.delete("corners", "bg_img", "countdown_text")
        self._draw_corners()
        self._apply_bg()
        self.canvas.tag_raise("corners")
        self._layout_countdown()
        info_y = self._countdown_y + self._countdown_block_h + int(14 * self.scale)
        self.target_info_lbl.place(y=info_y)


if __name__ == "__main__":
    CountdownWidget()
