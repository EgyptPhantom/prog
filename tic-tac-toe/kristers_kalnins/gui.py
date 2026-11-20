"""
Vizuālais laukums 5-rindu Tic-Tac-Toe botam (noteikumi: ../../RULES.md).

Palaišana (no šīs mapes):
    ../../.venv/bin/python gui.py

Režīmi
------
* Cilvēks pret botu: bots izliek Swap2 atklātni (3 akmeņi), tu izvēlies
  krāsu un spēlē, klikšķinot uz laukuma.
* Bots pret botu: divi boti spēlē pilnu Swap2 spēli. Gājienus var rādīt pa
  vienam ("Nākamais gājiens") vai automātiski.

Analīze ("Rādīt analīzi") parāda, ko bots redz laukumā: kur gājiena
veicējam ir uzvaras rūtiņas, četrinieki un atvērti trijnieki, kur ir
pretinieka draudi, un kurus gājienus heiristika vērtē augstāk.
Spēles loģika un gājienu izvēle ir bot.py; GUI tikai attēlo laukumu.
"""

import copy
import glob
import importlib.util
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bot as kb                                                     # noqa: E402
from bot import get_move, swap2_propose, swap2_respond, swap2_final_choice  # noqa: E402,F401

N = 15
EMPTY = "_"
CELL = 40                # viena lauciņa izmērs
FRAME = 30               # koka rāmis ar koordinātām
SIZE = FRAME * 2 + CELL * N
TIME_LIMIT = 1.0

FRAME_COL = "#5b3a21"    # tumšs koks
BOARD_COL = "#f0d9b5"    # visi lauciņi vienā krāsā
LINE_COL = "#b58863"
LABEL_COL = "#f0d9b5"
X_COL = "#1f2937"        # krustiņi
O_COL = "#c0392b"        # nullītes
LAST_COL = "#cfe2f3"     # pēdējā gājiena lauciņš (gaiši zils)
COL_WIN = "#d62828"      # uzvaras rūtiņa (5 pēc kārtas)
COL_STRONG = "#f77f00"   # atvērts vai dubults četrinieks
COL_FOUR = "#d4a017"     # četrinieks
COL_THREE = "#2a9d8f"    # atvērts trijnieks
COL_CAND = "#1d3557"     # heiristikas labākie gājieni
TINT = {COL_WIN: "#f5b7b1", COL_STRONG: "#fad7a0", COL_FOUR: "#f9e79f", COL_THREE: "#a9dfbf"}


def load_bots():
    """Ielādē visus ../*/bot.py botus. Atgriež sarakstu ar (nosaukums, modulis)."""
    bots = [(kb.BOT_NAME + " (mans)", kb)]
    mine = os.path.abspath(kb.__file__)
    for path in sorted(glob.glob(os.path.join(HERE, "..", "*", "bot.py"))):
        path = os.path.abspath(path)
        if path == mine:
            continue
        folder = os.path.basename(os.path.dirname(path))
        try:
            spec = importlib.util.spec_from_file_location("gui_bot_" + folder, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            bots.append((getattr(mod, "BOT_NAME", folder), mod))
        except Exception as e:                       # bojāts bots netraucē GUI
            print("Neizdevās ielādēt", folder, ":", e)
    return bots


def five_line(board, r, c):
    """Ja (r, c) veido 5 pēc kārtas, atgriež līnijas galus, citādi None."""
    p = board[r][c]
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        ends = []
        for sgn in (-1, 1):
            rr, cc = r, c
            while (0 <= rr + sgn * dr < N and 0 <= cc + sgn * dc < N
                   and board[rr + sgn * dr][cc + sgn * dc] == p):
                rr += sgn * dr
                cc += sgn * dc
            ends.append((rr, cc))
        (r1, c1), (r2, c2) = ends
        if max(abs(r2 - r1), abs(c2 - c1)) + 1 >= 5:
            return ends
    return None


def valid_cell(board, mv):
    return (isinstance(mv, (tuple, list)) and len(mv) == 2
            and all(isinstance(v, int) for v in mv)
            and 0 <= mv[0] < N and 0 <= mv[1] < N and board[mv[0]][mv[1]] == EMPTY)


class App:
    def __init__(self, root):
        self.root = root
        root.title("5 pēc kārtas: vizuālais laukums")
        self.bots = load_bots()
        self.names = [n for n, _ in self.bots]

        self.board = [[EMPTY] * N for _ in range(N)]
        self.history = []          # (r, c, simbols, gājiena nr. vai None atklātnei)
        self.phase = "idle"
        self.colors = {}           # simbols -> "human" vai bota modulis
        self.to_move = "O"
        self.busy = False
        self.over = False
        self.win_ends = None
        self.job = None
        self.result = None

        self._build_ui()
        self.new_game()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.canvas = tk.Canvas(self.root, width=SIZE, height=SIZE, bg=FRAME_COL,
                                highlightthickness=0)
        self.canvas.grid(row=0, column=0, padx=10, pady=10, sticky="n")
        self.canvas.bind("<Button-1>", self.on_click)

        side = ttk.Frame(self.root, padding=(0, 10, 10, 10))
        side.grid(row=0, column=1, sticky="ns")

        box = ttk.LabelFrame(side, text="Spēle", padding=8)
        box.pack(fill="x")
        self.mode = tk.StringVar(value="human")
        ttk.Radiobutton(box, text="Cilvēks pret botu", value="human",
                        variable=self.mode).pack(anchor="w")
        ttk.Radiobutton(box, text="Bots pret botu", value="bots",
                        variable=self.mode).pack(anchor="w")
        ttk.Label(box, text="Bots 1 (izliek atklātni):").pack(anchor="w", pady=(6, 0))
        self.bot1 = ttk.Combobox(box, values=self.names, state="readonly", width=28)
        self.bot1.current(0)
        self.bot1.pack(anchor="w")
        ttk.Label(box, text="Bots 2 (tikai režīmā bots pret botu):").pack(anchor="w", pady=(6, 0))
        self.bot2 = ttk.Combobox(box, values=self.names, state="readonly", width=28)
        self.bot2.current(next((i for i, n in enumerate(self.names) if "Peteris" in n), 0))
        self.bot2.pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Jauna spēle", command=self.new_game).pack(side="left")
        ttk.Button(row, text="Atsaukt", command=self.undo).pack(side="left", padx=6)

        self.choose = ttk.LabelFrame(side, text="Izvēlies krāsu", padding=8)
        ttk.Button(self.choose, text="Spēlēt ar X (melnie)",
                   command=lambda: self.human_choose("X")).pack(fill="x")
        ttk.Button(self.choose, text="Spēlēt ar O (baltie, gājiens tagad)",
                   command=lambda: self.human_choose("O")).pack(fill="x", pady=(4, 0))

        play = ttk.LabelFrame(side, text="Bots pret botu", padding=8)
        play.pack(fill="x", pady=(8, 0))
        ttk.Button(play, text="Nākamais gājiens", command=self.step).pack(fill="x")
        self.auto = tk.BooleanVar(value=False)
        ttk.Checkbutton(play, text="Spēlēt automātiski", variable=self.auto,
                        command=self.on_auto).pack(anchor="w", pady=(4, 0))
        ttk.Label(play, text="Pauze starp gājieniem (ms):").pack(anchor="w")
        self.delay = tk.IntVar(value=300)
        ttk.Scale(play, from_=0, to=2000, variable=self.delay,
                  orient="horizontal").pack(fill="x")

        view = ttk.LabelFrame(side, text="Skats", padding=8)
        view.pack(fill="x", pady=(8, 0))
        self.show_analysis = tk.BooleanVar(value=True)
        self.show_numbers = tk.BooleanVar(value=False)
        ttk.Checkbutton(view, text="Rādīt analīzi", variable=self.show_analysis,
                        command=self.redraw).pack(anchor="w")
        ttk.Checkbutton(view, text="Rādīt gājienu numurus", variable=self.show_numbers,
                        command=self.redraw).pack(anchor="w")
        legend = tk.Canvas(view, width=290, height=150, highlightthickness=0,
                           bg=self.root.cget("bg"))
        legend.pack(anchor="w", pady=(6, 0))
        items = [(COL_WIN, "5 pēc kārtas (uzvara)"),
                 (COL_STRONG, "atvērts vai dubults četrinieks"),
                 (COL_FOUR, "četrinieks"),
                 (COL_THREE, "atvērts trijnieks")]
        for n, (col, text) in enumerate(items):
            y = 10 + n * 20
            legend.create_rectangle(4, y - 7, 18, y + 7, fill=TINT[col], outline=LINE_COL)
            legend.create_rectangle(24, y - 7, 38, y + 7, fill=BOARD_COL, outline=col, width=3)
            legend.create_text(44, y, text=text, anchor="w", font=("Helvetica", 11))
        legend.create_text(4, 92, anchor="nw", font=("Helvetica", 11),
                           text="iekrāsots lauciņš: gājiena veicēja iespējas\n"
                                "krāsains rāmītis: pretinieka draudi\n"
                                "1-5: heiristikas labākie kandidāti")

        self.status = ttk.Label(side, text="", font=("Helvetica", 13, "bold"),
                                wraplength=290)
        self.status.pack(anchor="w", pady=(10, 0))
        self.why = ttk.Label(side, text="", wraplength=290, justify="left")
        self.why.pack(anchor="w", pady=(4, 0))

        logf = ttk.Frame(side)
        logf.pack(fill="both", expand=True, pady=(8, 0))
        self.log = tk.Text(logf, width=40, height=12, font=("Menlo", 10), wrap="word")
        sb = ttk.Scrollbar(logf, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set, state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_status(self, text, why=""):
        self.status.configure(text=text)
        self.why.configure(text=why)

    # ------------------------------------------------------------ zīmēšana
    def xy(self, r, c):
        """Lauciņa centrs pikseļos."""
        return FRAME + c * CELL + CELL // 2, FRAME + r * CELL + CELL // 2

    def cell_box(self, r, c, inset=0):
        x0, y0 = FRAME + c * CELL + inset, FRAME + r * CELL + inset
        return x0, y0, x0 + CELL - 2 * inset, y0 + CELL - 2 * inset

    def redraw(self):
        cv = self.canvas
        cv.delete("all")
        last = tuple(self.history[-1][:2]) if self.history else None
        for r in range(N):
            for c in range(N):
                fill = LAST_COL if (r, c) == last else BOARD_COL
                cv.create_rectangle(*self.cell_box(r, c), fill=fill, outline=LINE_COL)
        cv.create_rectangle(FRAME, FRAME, FRAME + N * CELL, FRAME + N * CELL,
                            outline="#2b1a0e", width=3)
        for i in range(N):
            x, y = self.xy(i, i)
            for pos in (FRAME // 2, SIZE - FRAME // 2):
                cv.create_text(x, pos, text=str(i), fill=LABEL_COL, font=("Helvetica", 11, "bold"))
                cv.create_text(pos, y, text=str(i), fill=LABEL_COL, font=("Helvetica", 11, "bold"))

        if self.show_analysis.get() and self.phase == "play" and not self.over:
            self.draw_analysis()

        numbers = {(r, c): num for r, c, _, num in self.history}
        pad = CELL // 4
        for r in range(N):
            for c in range(N):
                sym = self.board[r][c]
                if sym == EMPTY:
                    continue
                x0, y0, x1, y1 = self.cell_box(r, c, pad)
                if sym == "X":
                    for a, b in (((x0, y0), (x1, y1)), ((x0, y1), (x1, y0))):
                        cv.create_line(*a, *b, fill=X_COL, width=5, capstyle="round")
                else:
                    cv.create_oval(x0, y0, x1, y1, outline=O_COL, width=4)
                if self.show_numbers.get():
                    num = numbers.get((r, c))
                    bx, by = self.cell_box(r, c)[:2]
                    cv.create_text(bx + 3, by + 2, anchor="nw", text=str(num) if num else "a",
                                   fill="#7f6a55", font=("Helvetica", 8))
        if self.win_ends:
            (r1, c1), (r2, c2) = self.win_ends
            cv.create_line(*self.xy(r1, c1), *self.xy(r2, c2), fill=COL_WIN, width=6,
                           capstyle="round")

    def draw_analysis(self):
        """Ko bot.py redz: draudi abiem spēlētājiem un labākie kandidāti."""
        try:
            g = kb._Game(self.board)
            k = kb.KIDX[self.to_move]
            mine, theirs = g.threats(k), g.threats(1 - k)
            cands = g.candidates(k, 5)
        except Exception:
            return
        cv = self.canvas

        def strongest(th):
            wins, strong, fours, threes = th
            out = {}
            for col, group in ((COL_THREE, threes), (COL_FOUR, fours),
                               (COL_STRONG, strong), (COL_WIN, wins)):
                for i in group:
                    out[i] = col
            return out

        for i, col in strongest(mine).items():
            cv.create_rectangle(*self.cell_box(*divmod(i, N), 1), fill=TINT[col], outline="")
        for i, col in strongest(theirs).items():
            cv.create_rectangle(*self.cell_box(*divmod(i, N), 4), outline=col, width=3)
        for n, i in enumerate(cands, 1):
            x0, y0, x1, y1 = self.cell_box(*divmod(i, N))
            cv.create_text(x1 - 4, y1 - 3, anchor="se", text=str(n), fill=COL_CAND,
                           font=("Helvetica", 11, "bold"))

    def name_of(self, who):
        if who == "human":
            return "Tu"
        return next(n for n, m in self.bots if m is who)

    def new_game(self):
        self.cancel_job()
        self.board = [[EMPTY] * N for _ in range(N)]
        self.history = []
        self.over = False
        self.win_ends = None
        self.colors = {}
        self.to_move = "O"
        self.busy = False
        self.result = None
        self.choose.pack_forget()
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.A = self.bots[self.bot1.current()][1]
        self.B = "human" if self.mode.get() == "human" else self.bots[self.bot2.current()][1]
        self.write_log("Bots 1: %s\n%s: %s" % (
            self.name_of(self.A), "Pretinieks" if self.B == "human" else "Bots 2",
            self.name_of(self.B)))
        self.phase = "propose"
        self.redraw()
        if self.B == "human":
            self.set_status("%s izliek atklātni..." % self.name_of(self.A))
            self.step()
        else:
            self.set_status("Spied \"Nākamais gājiens\" vai ieslēdz automātisko spēli.")
            if self.auto.get():
                self.step()

    def cancel_job(self):
        if self.job is not None:
            self.root.after_cancel(self.job)
            self.job = None

    def on_auto(self):
        if self.auto.get() and self.B != "human":
            self.step()

    def run_bot(self, bot, fname, args, then):
        """Izsauc bota funkciju atsevišķā pavedienā, lai logs nesastingst."""
        self.busy = True
        board = copy.deepcopy(self.board)
        holder = []                    # katram izsaukumam savs rezultāta trauks
        self.result = holder

        def work():
            t0 = time.perf_counter()
            try:
                res = getattr(bot, fname)(board, *args)
                err = None
            except Exception as e:
                res, err = None, e
            holder.append((res, err, time.perf_counter() - t0))

        threading.Thread(target=work, daemon=True).start()

        def poll():
            if self.result is not holder:      # spēle tika sākta no jauna
                return
            if not holder:
                self.job = self.root.after(30, poll)
                return
            self.job = None
            self.busy = False
            res, err, dt = holder[0]
            label = self.name_of(bot)
            if err is not None:
                self.finish(None, "%s kļūda (%s): %r" % (label, fname, err), loser=bot)
                return
            if dt > TIME_LIMIT:
                self.write_log("  ! %s domāja %.2f s (> %.1f s)" % (label, dt, TIME_LIMIT))
            then(res, dt)

        self.job = self.root.after(30, poll)

    def step(self):
        """Nākamais solis: atklātne vai bota gājiens."""
        if self.busy or self.over:
            return
        if self.phase == "propose":
            self.run_bot(self.A, "swap2_propose", (), self.after_propose)
        elif self.phase == "respond" and self.B != "human":
            self.run_bot(self.B, "swap2_respond", (), self.after_respond)
        elif self.phase == "final":
            self.run_bot(self.A, "swap2_final_choice", (), self.after_final)
        elif self.phase == "play":
            who = self.colors[self.to_move]
            if who == "human":
                return
            self.set_status("%s (%s) domā..." % (self.name_of(who), self.to_move))
            self.run_bot(who, "get_move", (self.to_move,), self.after_move)

    def continue_auto(self):
        """Pēc katra soļa: ja nākamais ir bots, turpina."""
        if self.over or self.phase != "play" and self.B == "human":
            return
        if self.phase == "play" and self.colors.get(self.to_move) == "human":
            return
        if self.B == "human" or self.auto.get():
            delay = 50 if self.B == "human" else int(self.delay.get())
            self.job = self.root.after(delay, self.step)

    def place_stones(self, moves, what, owner):
        for m in moves:
            if not (isinstance(m, (tuple, list)) and len(m) == 3
                    and valid_cell(self.board, (m[0], m[1])) and m[2] in ("X", "O")):
                self.finish(None, "%s: nederīgs %s %r" % (self.name_of(owner), what, m), loser=owner)
                return False
            self.board[m[0]][m[1]] = m[2]
            self.history.append((m[0], m[1], m[2], None))
        return True

    def after_propose(self, res, dt):
        if not isinstance(res, (list, tuple)) or sorted(str(m[2]) for m in res) != ["O", "X", "X"]:
            self.finish(None, "swap2_propose: jābūt 2 X un 1 O", loser=self.A)
            return
        if not self.place_stones(res, "atklātnes akmens", self.A):
            return
        self.write_log("Atklātne: " + ", ".join("%s(%d,%d)" % (m[2], m[0], m[1]) for m in res))
        self.phase = "respond"
        self.redraw()
        if self.B == "human":
            self.set_status("Izvēlies krāsu.", "X ir divi akmeņi, O ir nākamais gājiens.")
            self.choose.pack(fill="x", pady=(8, 0), after=self.choose.master.winfo_children()[0])
        else:
            self.set_status("%s izvēlas krāsu..." % self.name_of(self.B))
            self.continue_auto()

    def human_choose(self, sym):
        if self.phase != "respond" or self.B != "human":
            return
        self.choose.pack_forget()
        other = "O" if sym == "X" else "X"
        self.colors = {sym: "human", other: self.A}
        self.write_log("Tu spēlē ar %s" % sym)
        self.start_play()

    def after_respond(self, res, dt):
        action = res.get("action") if isinstance(res, dict) else None
        if action == "TAKE_X":
            self.colors = {"X": self.B, "O": self.A}
        elif action == "TAKE_O":
            self.colors = {"X": self.A, "O": self.B}
        elif action == "PLACE_TWO":
            moves = res.get("moves")
            if not isinstance(moves, (list, tuple)) or [m[2] for m in moves] != ["X", "O"]:
                self.finish(None, "PLACE_TWO: nederīgi gājieni", loser=self.B)
                return
            if not self.place_stones(moves, "PLACE_TWO akmens", self.B):
                return
            self.write_log("%s: PLACE_TWO" % self.name_of(self.B))
            self.phase = "final"
            self.redraw()
            self.continue_auto()
            return
        else:
            self.finish(None, "swap2_respond: nederīga atbilde %r" % (res,), loser=self.B)
            return
        self.write_log("%s: %s" % (self.name_of(self.B), action))
        self.start_play()

    def after_final(self, res, dt):
        if res == "X":
            self.colors = {"X": self.A, "O": self.B}
        elif res == "O":
            self.colors = {"X": self.B, "O": self.A}
        else:
            self.finish(None, "swap2_final_choice: nederīga izvēle %r" % (res,), loser=self.A)
            return
        self.write_log("%s izvēlas %s" % (self.name_of(self.A), res))
        self.start_play()

    def start_play(self):
        self.phase = "play"
        self.to_move = "O"
        self.write_log("X: %s, O: %s" % (self.name_of(self.colors["X"]),
                                         self.name_of(self.colors["O"])))
        self.announce_turn()
        self.redraw()
        self.continue_auto()

    def announce_turn(self, why=""):
        who = self.colors[self.to_move]
        if who == "human":
            self.set_status("Tavs gājiens (%s). Klikšķini uz lauciņa." % self.to_move, why)
        else:
            self.set_status("Gājiens: %s (%s)" % (self.name_of(who), self.to_move), why)

    def apply_move(self, r, c, who):
        sym = self.to_move
        self.board[r][c] = sym
        num = sum(1 for h in self.history if h[3]) + 1
        self.history.append((r, c, sym, num))
        ends = five_line(self.board, r, c)
        if ends:
            self.win_ends = ends
            self.finish(who, "%s (%s) uzvar: 5 pēc kārtas!" % (self.name_of(who), sym))
            return
        if all(cell != EMPTY for row in self.board for cell in row):
            self.finish(None, "Neizšķirts: laukums ir pilns.")
            return
        self.to_move = "X" if sym == "O" else "O"

    def after_move(self, res, dt):
        who = self.colors[self.to_move]
        if not valid_cell(self.board, res):
            self.finish(None, "%s: nederīgs gājiens %r" % (self.name_of(who), res), loser=who)
            return
        r, c = res
        why = ""
        if who is kb and kb._INFO.get("why"):
            v = kb._INFO.get("value", 0)
            if v >= kb.WIN - 1000:
                vtxt = "uzvara atrasta"
            elif v <= -kb.WIN + 1000:
                vtxt = "zaudējums neizbēgams"
            else:
                vtxt = "%+d" % v
            why = "Mana bota gājiens (%d,%d): %s\nNovērtējums: %s.  Laiks: %.2f s" % (
                r, c, kb._INFO["why"], vtxt, dt)
        num = sum(1 for h in self.history if h[3]) + 1
        self.write_log("%3d. %s %s (%d,%d)  %.2f s" % (num, self.to_move,
                                                       self.name_of(who), r, c, dt))
        if who is kb and kb._INFO.get("why"):
            self.write_log("     " + kb._INFO["why"])
        self.apply_move(r, c, who)
        if not self.over:
            self.announce_turn(why)
        else:
            self.why.configure(text=why)
        self.redraw()
        self.continue_auto()

    def on_click(self, event):
        if self.over or self.busy or self.phase != "play":
            return
        if self.colors.get(self.to_move) != "human":
            return
        c = (event.x - FRAME) // CELL
        r = (event.y - FRAME) // CELL
        if not (0 <= r < N and 0 <= c < N) or self.board[r][c] != EMPTY:
            return
        num = sum(1 for h in self.history if h[3]) + 1
        self.write_log("%3d. %s Tu (%d,%d)" % (num, self.to_move, r, c))
        self.apply_move(r, c, "human")
        if not self.over:
            self.announce_turn()
        self.redraw()
        self.continue_auto()

    def undo(self):
        """Atsauc gājienus līdz brīdim, kad atkal ir tavs gājiens (tikai pret botu)."""
        if self.busy or self.B != "human" or self.phase != "play":
            return
        human = "X" if self.colors.get("X") == "human" else "O"
        removed = False
        while self.history and self.history[-1][3]:
            r, c, sym, _ = self.history.pop()
            self.board[r][c] = EMPTY
            self.to_move = sym
            removed = True
            if sym == human:
                break
        if removed:
            self.over = False
            self.win_ends = None
            self.write_log("(atsaukts)")
            self.announce_turn()
            self.redraw()
            self.continue_auto()

    def finish(self, winner, text, loser=None):
        self.over = True
        self.busy = False
        self.cancel_job()
        if loser is not None and winner is None:
            others = [w for w in (self.A, self.B) if w is not loser]
            if others:
                text += "  Uzvar: %s." % self.name_of(others[0])
        self.set_status(text)
        self.write_log(text)
        self.redraw()


def main():
    root = tk.Tk()
    root.resizable(False, False)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
