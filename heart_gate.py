import ctypes
import random
import subprocess
import sys
import tkinter as tk

# settings
PASSPHRASE = "changeme"
MAX_HP = 3
SHUTDOWN_ENABLED = False
SHUTDOWN_DELAY = 20
DEV_ESCAPE = True
KEEP_FOCUS = True
FOCUS_RETRIES = 12

BG = "#000000"
HEART_RED = "#ff0000"
HEART_FLASH = "#ffffff"
HEART_DEAD = "#3a3a3a"
TEXT = "#ffffff"

# messages
MSG_PROMPT = "* Who goes there?"
MSG_WIN = "* Hey it's you!"
MSG_FAIL = "* That wasn't it."
MSG_GAME_OVER = "GAME OVER"
MSG_DEAD = "* :P"
MSG_SHUTDOWN = "* Shutting down in {}s."
MSG_SHUTDOWN_REASON = "You ran out of HP."


HEART = [
    "  XX  XX  ",
    " XXXXXXXX ",
    " XXXXXXXX ",
    " XXXXXXXX ",
    "  XXXXXX  ",
    "   XXXX   ",
    "    XX    ",
]
PIXEL = 6
BIG_PIXEL = 14


def _hwnd_of(root):
    hwnd = root.winfo_id()
    parent = ctypes.windll.user32.GetParent(hwnd)
    return parent or hwnd


def is_foreground(root):
    if sys.platform != "win32":
        return bool(root.focus_displayof())
    try:
        return ctypes.windll.user32.GetForegroundWindow() == _hwnd_of(root)
    except Exception:
        return True


def force_foreground(root):
    root.deiconify()
    root.lift()
    root.focus_force()

    if sys.platform != "win32":
        return

    try:
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32

        hwnd = _hwnd_of(root)
        fg = u32.GetForegroundWindow()
        if fg == hwnd:
            return

        fg_tid = u32.GetWindowThreadProcessId(fg, None)
        our_tid = k32.GetCurrentThreadId()

        attached = False
        if fg_tid and fg_tid != our_tid:
            attached = bool(u32.AttachThreadInput(fg_tid, our_tid, True))
        try:
            u32.ShowWindow(hwnd, 9)
            u32.BringWindowToTop(hwnd)
            u32.SetForegroundWindow(hwnd)
            u32.SetActiveWindow(hwnd)
            u32.SetFocus(hwnd)
        finally:
            if attached:
                u32.AttachThreadInput(fg_tid, our_tid, False)
    except Exception:
        pass


class Gate:
    def __init__(self, root):
        self.root = root
        self.hp = MAX_HP
        self.dead = False

        root.attributes("-fullscreen", True)
        root.attributes("-topmost", True)
        root.configure(bg=BG)
        root.config(cursor="none")

        self.w = root.winfo_screenwidth()
        self.h = root.winfo_screenheight()

        self.canvas = tk.Canvas(
            root, bg=BG, highlightthickness=0, width=self.w, height=self.h
        )
        self.canvas.pack(fill="both", expand=True)

        self.heart_ids = self.draw_heart(
            self.w // 2, self.h // 2 - 120, BIG_PIXEL, HEART_RED
        )

        self.build_hp_row()

        self.prompt = self.canvas.create_text(
            self.w // 2, self.h // 2 + 60,
            text=MSG_PROMPT,
            fill=TEXT, font=("Consolas", 26),
        )

        self.entry = tk.Entry(
            root, show="\u2022", font=("Consolas", 24), justify="center",
            bg="#111111", fg=TEXT, insertbackground=TEXT,
            relief="flat", width=18,
        )
        self.canvas.create_window(
            self.w // 2, self.h // 2 + 120, window=self.entry
        )
        self.entry.bind("<Return>", self.submit)

        self.grab_focus(FOCUS_RETRIES)

        if KEEP_FOCUS:
            root.bind("<FocusOut>", self.on_focus_out)

        if DEV_ESCAPE:
            root.bind("<Control-Shift-Q>", lambda e: root.destroy())

    def grab_focus(self, retries=0):
        if self.dead and retries <= 0:
            return
        force_foreground(self.root)
        try:
            self.entry.focus_force()
        except tk.TclError:
            pass
        if retries > 0:
            self.root.after(120, lambda: self.grab_focus(retries - 1))

    def on_focus_out(self, _event=None):
        self.root.after(150, self._reclaim)

    def _reclaim(self):
        if self.dead or is_foreground(self.root):
            return
        self.grab_focus()

    def draw_heart(self, cx, cy, size, colour):
        ids = []
        rows = len(HEART)
        cols = len(HEART[0])
        x0 = cx - (cols * size) // 2
        y0 = cy - (rows * size) // 2
        for r, row in enumerate(HEART):
            for c, ch in enumerate(row):
                if ch != "X":
                    continue
                x = x0 + c * size
                y = y0 + r * size
                ids.append(
                    self.canvas.create_rectangle(
                        x, y, x + size, y + size,
                        fill=colour, outline="",
                    )
                )
        return ids

    def build_hp_row(self):
        """Create the HP hearts once. Colour changes happen in update_hp_row."""
        self.hp_hearts = []
        spacing = len(HEART[0]) * PIXEL + 20
        start = self.w // 2 - (spacing * (MAX_HP - 1)) // 2
        for i in range(MAX_HP):
            self.hp_hearts.append(
                self.draw_heart(start + i * spacing, self.h - 120, PIXEL, HEART_RED)
            )
        self.hp_label = self.canvas.create_text(
            self.w // 2, self.h - 60,
            text=f"HP {self.hp}/{MAX_HP}",
            fill=TEXT, font=("Consolas", 18),
        )

    def update_hp_row(self):
        for i, ids in enumerate(self.hp_hearts):
            colour = HEART_RED if i < self.hp else HEART_DEAD
            for item in ids:
                self.canvas.itemconfig(item, fill=colour)
        self.canvas.itemconfig(self.hp_label, text=f"HP {self.hp}/{MAX_HP}")

    def submit(self, _event=None):
        if self.dead:
            return
        guess = self.entry.get()
        self.entry.delete(0, "end")
        if guess == PASSPHRASE:
            self.canvas.itemconfig(self.prompt, text=MSG_WIN)
            self.root.after(900, self.root.destroy)
        else:
            self.take_damage()

    def take_damage(self):
        self.hp -= 1
        self.update_hp_row()
        if self.hp <= 0:
            self.die()
        else:
            self.canvas.itemconfig(self.prompt, text=MSG_FAIL)
            self.flash()
            self.shake(8)

    def flash(self):
        for i in self.heart_ids:
            self.canvas.itemconfig(i, fill=HEART_FLASH)
        self.root.after(90, self.unflash)

    def unflash(self):
        for i in self.heart_ids:
            self.canvas.itemconfig(i, fill=HEART_RED)

    def shake(self, times):
        if times <= 0 or self.dead:
            return
        dx = random.choice((-6, 6))
        for i in self.heart_ids:
            self.canvas.move(i, dx, 0)
        self.root.after(30, lambda: self._unshake(dx, times))

    def _unshake(self, dx, times):
        for i in self.heart_ids:
            self.canvas.move(i, -dx, 0)
        if self.dead:
            return
        self.root.after(30, lambda: self.shake(times - 1))

    def die(self):
        self.dead = True
        self.entry.destroy()
        self.canvas.itemconfig(self.prompt, text="")
        # give every heart pixel a velocity and let gravity have it
        self.shards = []
        for i in self.heart_ids:
            self.shards.append([i, random.uniform(-7, 7), random.uniform(-11, -4)])
        self.root.after(250, self.shatter_step)

    def shatter_step(self):
        alive = False
        for shard in self.shards:
            item, vx, vy = shard
            self.canvas.move(item, vx, vy)
            shard[2] = vy + 0.6  # gravity
            if self.canvas.coords(item)[1] < self.h:
                alive = True
        if alive:
            self.root.after(16, self.shatter_step)
        else:
            self.game_over()

    def game_over(self):
        self.canvas.create_text(
            self.w // 2, self.h // 2,
            text=MSG_GAME_OVER, fill=HEART_RED, font=("Consolas", 64, "bold"),
        )
        self.canvas.create_text(
            self.w // 2, self.h // 2 + 80,
            text=MSG_SHUTDOWN.format(SHUTDOWN_DELAY) if SHUTDOWN_ENABLED else MSG_DEAD,
            fill=TEXT, font=("Consolas", 22),
        )
        self.root.after(3000, self.finish)

    def finish(self):
        if SHUTDOWN_ENABLED and sys.platform == "win32":
            subprocess.run([
                "shutdown", "/s", "/t", str(SHUTDOWN_DELAY),
                "/c", MSG_SHUTDOWN_REASON,
            ])
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Gate(root)
    root.mainloop()
