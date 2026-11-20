"""Canvas presentation and effects for the Dive Grid game window."""

from collections.abc import Callable
from dataclasses import dataclass
from math import cos, pi, sin, tau
from pathlib import Path
from random import Random
from time import perf_counter
import tkinter as tk
from tkinter import font

from main import BOARD_SIZE

INK = "#082343"
NAVY = "#102f59"
CREAM = "#fff8e8"
ORANGE = "#ff981f"
CYAN = "#6ce8f3"
WHITE = "#fffdf5"
CELL_COLORS = ("#d6edf0", "#c4e2e9")
MARKS = {"X": ("#2bcadf", "#bafdff"), "O": ("#ff9d28", "#ffe189")}
ASSETS = Path(__file__).with_name("assets")


@dataclass
class Action:
    bounds: tuple[int, int, int, int]
    label: str
    callback: Callable[[], None]
    primary: bool = False

    def contains(self, x, y):
        x1, y1, x2, y2 = self.bounds
        return x1 <= x < x2 and y1 <= y < y2


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    start: float
    life: float
    color: str
    size: float
    style: str


class ArenaView(tk.Canvas):
    WIDTH, HEIGHT = 940, 660
    CELL = 33
    BOARD_X, BOARD_Y = 52, 122
    BOARD_END = BOARD_X + CELL * BOARD_SIZE
    BOARD_BOTTOM = BOARD_Y + CELL * BOARD_SIZE

    def __init__(self, root, place, choose, restart):
        super().__init__(root, width=self.WIDTH, height=self.HEIGHT, bg=NAVY, highlightthickness=0, takefocus=True)
        self.place_move, self.choose_color, self.restart_match = place, choose, restart
        families = set(font.families(root))
        self.display = next(
            (family for family in ("Lilita One", "Arial Black", "Helvetica Neue", "Arial") if family in families),
            "TkDefaultFont",
        )
        self.arena = tk.PhotoImage(master=self, file=ASSETS / "dive-arena.png")
        self.trophy = tk.PhotoImage(master=self, file=ASSETS / "dive-trophy.png")
        self.random = Random()
        self.game = None
        self.stones = {}
        self.moving = {}
        self.particles = []
        self.banner = None
        self.frame_job = None
        self.actions = []
        self.mouse = (-1, -1)
        self.hover_cell = None
        self.hover_action = None
        self.focus_action = None

        self._background()
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda event: self._track(-1, -1))
        self.bind("<Button-1>", self._click)
        self.bind("<Tab>", lambda event: self._focus_button(1))
        self.bind("<Shift-Tab>", lambda event: self._focus_button(-1))
        self.bind("<Return>", self._activate_button)
        self.bind("<space>", self._activate_button)

    def lettering(self, x, y, text, size, color, tag, *, anchor="center", outline=None):
        face = (self.display, -size, "bold")
        if outline:
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 3), (-2, 2), (2, 2)):
                self.create_text(x + dx, y + dy, text=text, fill=outline, font=face, anchor=anchor, tags=tag)
        self.create_text(x, y, text=text, fill=color, font=face, anchor=anchor, tags=tag)

    def _text(self, x, y, text, color, tag, *, width=0, size=14, anchor="w"):
        self.create_text(x, y, text=text, fill=color, font=("Helvetica", -size), width=width, anchor=anchor,
                         justify="center" if anchor == "center" else "left", tags=tag)

    def _bevel(self, bounds, fill, tag, *, rim=INK, shadow="#04172f", cut=11):
        x1, y1, x2, y2 = bounds
        points = (x1 + cut, y1, x2 - cut, y1, x2, y1 + cut, x2, y2 - cut,
                  x2 - cut, y2, x1 + cut, y2, x1, y2 - cut, x1, y1 + cut)
        self.create_polygon(*(p + 5 if i % 2 else p for i, p in enumerate(points)), fill=shadow, tags=tag)
        self.create_polygon(*points, fill=fill, outline=rim, width=3, tags=tag)

    def _background(self):
        self.create_image(0, 0, anchor="nw", image=self.arena)
        self.lettering(34, 41, "DIVE GRID", 39, WHITE, "world", anchor="w", outline=INK)
        self.lettering(280, 42, "FIVE IN A ROW", 16, "#e0faff", "world", anchor="w", outline=INK)
        self._bevel((23, 82, 575, 639), CREAM, "world", cut=15)
        self.create_rectangle(48, 118, 551, 621, fill="#32647e", outline=INK, width=2)
        for index in range(BOARD_SIZE):
            offset = (index + .5) * self.CELL
            self.lettering(self.BOARD_X + offset, 103, chr(65 + index), 12, NAVY, "world")
            self.lettering(35, self.BOARD_Y + offset, str(index + 1), 11, NAVY, "world")
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                x, y = self.BOARD_X + col * self.CELL, self.BOARD_Y + row * self.CELL
                self.create_rectangle(
                    x, y, x + self.CELL - 1, y + self.CELL - 1,
                    fill=CELL_COLORS[(row + col) % 2], outline="#76a4b7",
                )
                self.create_line(x + 1, y + 1, x + self.CELL - 2, y + 1, fill="#eefcff")
        self._bevel((594, 82, 916, 639), CREAM, "world", cut=15)

    def show(self, game, *, new_match=False):
        self.game = game
        now = perf_counter()
        if new_match:
            self.stones.clear()
            self.moving.clear()
            self.particles.clear()
            self.focus_action = None
            detail = "Place three marks to open" if game.first == "human" else "The bot opens this match"
            self._announce("GAME STARTED!", detail, CYAN, now, 1.5)
            self._burst(301, 175, now, (WHITE, CYAN, "#9abfff"), 22, "bubble")
        updated = {(row, col): mark for row, line in enumerate(game.board)
                   for col, mark in enumerate(line) if mark != "_"}
        for index, (cell, mark) in enumerate(sorted(updated.items() - self.stones.items())):
            start = now + index * .055
            self.moving[cell] = start
            x, y = self._center(cell)
            self._burst(x, y, start, MARKS[mark], 7, "spark")
        self.stones = updated

        if game.phase == "finished" and not new_match:
            if game.winner == "human":
                self._announce("YOU WIN!", "Five in a row!", ORANGE, now, 2.8)
                colors = (CYAN, ORANGE, "#ffe69a", WHITE, "#a4aafc")
                self._burst(170, 266, now, colors, 36, "confetti")
                self._burst(712, 242, now + .12, colors, 42, "confetti")
            elif game.winner == "bot":
                self._announce("YOU LOSE", "The bot made five in a row", "#ff927c", now, 2.3)
                self._burst(302, 409, now, ("#ffac95", WHITE, "#7bd6f5"), 30, "bubble")
            else:
                self._announce("IT'S A DRAW", "Every tile is filled", CYAN, now, 2.3)
                self._burst(302, 380, now, (WHITE, CYAN), 22, "bubble")
        self._draw_board()
        self._draw_sidebar()
        self._track(*self.mouse, force=True)
        if self.frame_job is None:
            self._animate()

    def _center(self, cell):
        row, col = cell
        return self.BOARD_X + (col + .5) * self.CELL, self.BOARD_Y + (row + .5) * self.CELL

    def _tile(self, cell, fill, tag="board_marks"):
        x, y = self._center(cell)
        half = self.CELL / 2
        self.create_rectangle(x - half + 1, y - half + 1, x + half - 1, y + half - 1,
                              fill=fill, outline="", tags=tag)

    def _winning_lines(self):
        last = self.game.last_move
        if not last or not self.game.winner:
            return
        mark = self.stones[last]
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            row, col = last
            while self.stones.get((row - dr, col - dc)) == mark:
                row, col = row - dr, col - dc
            line = []
            while self.stones.get((row, col)) == mark:
                line.append((row, col))
                row, col = row + dr, col + dc
            if len(line) >= 5:
                yield line

    def _draw_board(self):
        self.delete("board_marks")
        last = self.game.last_move
        if last:
            self._tile(last, "#9fd3e2")
        for line in self._winning_lines():
            bright = "#ffe386" if self.game.winner == "human" else "#ffb4a1"
            for cell in line:
                self._tile(cell, bright)
            self.create_line(*self._center(line[0]), *self._center(line[-1]), fill=WHITE, width=6,
                             capstyle="round", tags="board_marks")
        for cell, mark in self.stones.items():
            if cell not in self.moving:
                self._token(*self._center(cell), mark, 1, "board_marks")
        self.tag_lower("board_marks", "sidebar")
        self.tag_raise("hover")
        self.tag_raise("fx")

    def _token(self, x, y, mark, scale, tag, *, ghost=False):
        color, shine = MARKS[mark] if not ghost else ("#93c1ce", "#d4ecf3")
        border = INK if not ghost else "#537f93"

        def stroke(points, fill, relative_width, dy=0):
            coords = [value for dx, off_y in points for value in (x + dx * scale, y + off_y * scale + dy)]
            self.create_line(*coords, fill=fill, width=max(1, relative_width * scale),
                             capstyle="round", tags=tag)

        if mark == "X":
            for points in (((-7, -7), (7, 7)), ((7, -7), (-7, 7))):
                stroke(points, "#6280a0", 9, 2 * scale)
                stroke(points, border, 9)
                stroke(points, color, 6)
                stroke(points, shine, 2, -scale)
        else:
            radius = 9 * scale
            coords = (x - radius, y - radius, x + radius, y + radius)
            self.create_oval(coords, outline=border, width=max(1, 8 * scale), tags=tag)
            self.create_oval(coords, outline=color, width=max(1, 5 * scale), tags=tag)
            self.create_arc(coords, start=25, extent=126, style="arc", outline=shine,
                            width=max(1, 2 * scale), tags=tag)

    def _draw_sidebar(self):
        self.delete("sidebar")
        game = self.game
        mode = "QUICK DUEL" if game.bot_takes_o else "FULL SWAP2"
        self._bevel((741, 23, 913, 62), NAVY, "sidebar", rim="#3b7a9a", cut=9)
        self.lettering(827, 42, mode, 17, WHITE, "sidebar")
        if game.phase == "finished":
            self._result_card()
        else:
            self.lettering(618, 112, "LIVE MATCH", 21, INK, "sidebar", anchor="w")
            for index, actor in enumerate(("human", "bot")):
                who = "YOU" if actor == "human" else "BOARD BOT"
                mark = next((mark for mark, owner in game.colors.items() if owner == actor), "–")
                y = 137 + index * 61
                active = game.actor == actor
                self._bevel((615, y, 893, y + 49), NAVY if active else "#e2edf0", "sidebar",
                            rim="#276780" if active else "#a8c3cc", shadow="#dedad2", cut=7)
                self.lettering(632, y + 24, who, 16, WHITE if active else NAVY, "sidebar", anchor="w")
                accent = MARKS.get(mark, ("#7191a4",))[0]
                self.create_oval(849, y + 8, 880, y + 39, fill=accent, outline=INK, width=2, tags="sidebar")
                self.lettering(864.5, y + 23, mark, 17, INK, "sidebar")
            self.lettering(618, 274, game.status_title(), 18, INK, "sidebar", anchor="w")
            self._text(618, 305, game.hint(), "#38586d", "sidebar", width=269)

        self.actions = []
        if game.actor == "human" and game.phase in ("respond", "choose"):
            self.actions.extend([
                Action((617, 351, 749, 386), "TAKE X", lambda: self.choose_color("TAKE_X"), True),
                Action((761, 351, 893, 386), "TAKE O", lambda: self.choose_color("TAKE_O")),
            ])
            if game.phase == "respond":
                self.actions.append(Action((617, 397, 893, 431), "PLACE TWO", lambda: self.choose_color("PLACE_TWO")))
        self.create_line(616, 445, 894, 445, fill="#c8d8d8", width=2, tags="sidebar")
        self.lettering(618, 466, "NEW MATCH", 15, NAVY, "sidebar", anchor="w")
        replay = game.phase == "finished"

        def start_or_replay():
            if replay:
                self.restart_match(game.first == "human", full_swap2=not game.bot_takes_o)
            else:
                self.restart_match(True)

        self.actions.extend([
            Action((617, 486, 893, 529), "PLAY AGAIN" if replay else "I START", start_or_replay, True),
            Action((617, 542, 893, 579), "BOT STARTS", lambda: self.restart_match(False)),
            Action((617, 590, 893, 622), "I START · FULL SWAP2",
                   lambda: self.restart_match(True, full_swap2=True)),
        ])
    def _result_card(self):
        win = self.game.winner == "human"
        lost = self.game.winner == "bot"
        fill = "#fff0be" if win else "#ffe1d9" if lost else "#e2f6f5"
        self._bevel((615, 105, 894, 418), fill, "sidebar", rim="#9c6b24" if win else "#617e99")
        x = 754
        if win:
            self.create_image(x, 195, image=self.trophy, tags="sidebar")
        else:
            mark = self.stones.get(self.game.last_move, "O") if lost else "O"
            self._token(x, 195, mark, 3.4, "sidebar")
        self.lettering(x, 279, "YOU WIN!" if win else "YOU LOSE" if lost else "IT'S A DRAW", 31, INK, "sidebar")
        self._text(x, 322, self.game.hint(), "#38586d", "sidebar", width=237, anchor="center")
        self.lettering(x, 373, f"{self.game.move_count} MOVES", 14, NAVY, "sidebar")

    def _draw_actions(self):
        self.delete("action")
        for action in self.actions:
            x1, y1, x2, y2 = action.bounds
            active = action.contains(*self.mouse)
            lift = -2 if active else 0
            bounds = x1, y1 + lift, x2, y2 + lift
            fill = ("#ffb74d" if active else ORANGE) if action.primary else ("#ffffff" if active else "#f7f3e6")
            self._bevel(bounds, fill, "action", rim="#247e94" if self.focus_action == action.label else INK,
                        shadow="#a25514" if action.primary else "#8babc0", cut=9)
            self.create_line(x1 + 11, bounds[1] + 4, x2 - 11, bounds[1] + 4, fill=WHITE, tags="action")
            self.lettering((x1 + x2) / 2, (y1 + y2) / 2 + lift, action.label,
                           16 if action.primary else 13, WHITE if action.primary else NAVY, "action",
                           outline="#7f4314" if action.primary else None)
        self.tag_raise("fx")

    def _board_cell(self, x, y):
        if self.BOARD_X <= x < self.BOARD_END and self.BOARD_Y <= y < self.BOARD_BOTTOM:
            return (y - self.BOARD_Y) // self.CELL, (x - self.BOARD_X) // self.CELL
        return None

    def _preview_mark(self):
        game = self.game
        if game.actor != "human":
            return None
        if game.phase in ("opening", "extra"):
            return game.pending[0]
        if game.phase == "play":
            return game.symbol
        return None

    def _motion(self, event):
        self._track(event.x, event.y)

    def _track(self, x, y, *, force=False):
        self.mouse = x, y
        hovered = next((i for i, action in enumerate(self.actions) if action.contains(x, y)), None)
        if force or hovered != self.hover_action:
            self.hover_action = hovered
            self._draw_actions()
        cell = self._board_cell(x, y)
        mark = self._preview_mark()
        if cell in self.stones or not mark:
            cell = None
        if force or cell != self.hover_cell:
            self.hover_cell = cell
            self.delete("hover")
            if cell is not None:
                self._tile(cell, "#a8d6e2", "hover")
                self._token(*self._center(cell), mark, .92, "hover", ghost=True)
                self.tag_raise("fx")
        self.configure(cursor="hand2" if cell is not None or hovered is not None else "")

    def _click(self, event):
        self.focus_set()
        for action in self.actions:
            if action.contains(event.x, event.y):
                action.callback()
                return
        cell = self._board_cell(event.x, event.y)
        if cell is not None and self._preview_mark():
            self.place_move(*cell)

    def _focus_button(self, direction):
        labels = [action.label for action in self.actions]
        initial = -1 if direction > 0 else 0
        index = labels.index(self.focus_action) if self.focus_action in labels else initial
        self.focus_action = labels[(index + direction) % len(labels)]
        self._draw_actions()
        return "break"

    def _activate_button(self, event):
        action = next((action for action in self.actions if action.label == self.focus_action), None)
        if action is not None:
            action.callback()
        return "break"

    def _announce(self, title, detail, accent, now, duration):
        self.banner = title, detail, accent, now, duration

    def _burst(self, x, y, now, colors, count, style):
        for _ in range(count):
            angle = self.random.uniform(0, tau)
            speed = self.random.uniform(80, 255) if style == "confetti" else self.random.uniform(35, 125)
            self.particles.append(Particle(
                x, y, cos(angle) * speed, sin(angle) * speed - (80 if style == "confetti" else 20),
                now, self.random.uniform(.9, 2.2) if style in ("bubble", "confetti") else .42,
                self.random.choice(colors), self.random.uniform(2, 6), style,
            ))

    def _animate(self):
        self.frame_job = None
        self.delete("fx")
        now = perf_counter()
        completed = [cell for cell, start in self.moving.items() if now - start >= .29]
        if completed:
            for cell in completed:
                del self.moving[cell]
            self._draw_board()
        for cell, start in self.moving.items():
            t = (now - start) / .29
            if t >= 0:
                q = t - 1
                scale = max(.16, 1 + 2.7 * q ** 3 + 1.7 * q ** 2)
                self._token(*self._center(cell), self.stones[cell], scale, "fx")

        self.particles = [particle for particle in self.particles if now - particle.start < particle.life]
        for particle in self.particles:
            self._draw_particle(particle, now)
        if self.banner is not None:
            self._draw_banner(now)
        if self.moving or self.particles or self.banner:
            self.frame_job = self.after(16, self._animate)

    def _draw_particle(self, particle, now):
        age = now - particle.start
        if age < 0:
            return
        f = age / particle.life
        bubble = particle.style == "bubble"
        gravity = 110 if particle.style == "confetti" else -27 if bubble else 18
        x = particle.x + particle.vx * age
        y = particle.y + particle.vy * age + gravity * age * age
        size = particle.size * min(1, 3 * (1 - f))
        if bubble:
            self.create_oval(x - size, y - size, x + size, y + size,
                             outline=particle.color, width=1.5, tags="fx")
        else:
            spin = age * 8 + particle.vx
            points = [(x + cos(spin + i * pi / 2) * size, y + sin(spin + i * pi / 2) * size)
                      for i in range(4)]
            self.create_polygon(*[v for point in points for v in point], fill=particle.color, tags="fx")

    def _draw_banner(self, now):
        title, detail, color, start, duration = self.banner
        age = now - start
        if age >= duration:
            self.banner = None
            return
        arrival = min(age / .26, 1)
        exit_progress = max(0, 1 - (duration - age) / .24)
        y = 173 - 104 * (1 - arrival) ** 3 - 94 * exit_progress ** 2
        self._bevel((136, y - 35, 466, y + 38), NAVY, "fx", rim=color, cut=13)
        self.lettering(301, y - 9, title, 31, color, "fx", outline=INK)
        self._text(301, y + 18, detail, WHITE, "fx", size=13, anchor="center")
