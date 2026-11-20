"""
5-rindu Tic-Tac-Toe ar Swap2 — grafiskais interfeiss (tkinter).

Palaišana:  python gui.py   (no mapes, kurā atrodas arī bot.py)

GUI tikai attēlo laukumu un pieņem cilvēka klikšķus. Visus bota lēmumus
pieņem bot.py funkcijas (get_move, swap2_propose, swap2_respond,
swap2_final_choice) — GUI tām padod laukuma kopiju un attēlo atbildi.
"""

import tkinter as tk

from bot import BOT_NAME, get_move, swap2_propose, swap2_respond, swap2_final_choice

N = 15
EMPTY, X, O = "_", "X", "O"
HUMAN, BOT = "human", "bot"

CELL = 38                  # rūtiņas izmērs pikseļos
PAD = 28                   # atstarpe ap laukumu (koordinātu numuriem)
BOARD_BG = "#e3c08d"
LINE_COLOR = "#7a5a2f"
BOT_DELAY = 80             # ms pirms bota gājiena (lai paspēj uzzīmēt)
BOT_VS_BOT_DELAY = 250

X_COLOR = "#1b1b1b"
O_COLOR = "#1f4e9c"

COLOR_NAME = {X: "X", O: "O"}


# ---------------------------------------------------------------------------
# Noteikumu palīgfunkcijas (tiesneša loģika, nevis AI)
# ---------------------------------------------------------------------------
def new_board():
    return [[EMPTY] * N for _ in range(N)]


def copy_board(board):
    return [row[:] for row in board]


def five_line(board, r, c):
    """Ja gājiens (r, c) izveidoja >= 5 pēc kārtas, atgriež līnijas galus, citādi None."""
    p = board[r][c]
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        ends = []
        for sgn in (1, -1):
            rr, cc = r, c
            while 0 <= rr + sgn * dr < N and 0 <= cc + sgn * dc < N \
                    and board[rr + sgn * dr][cc + sgn * dc] == p:
                rr += sgn * dr
                cc += sgn * dc
            ends.append((rr, cc))
        (r1, c1), (r2, c2) = ends
        if max(abs(r1 - r2), abs(c1 - c2)) + 1 >= 5:
            return ends
    return None


def is_full(board):
    return all(cell != EMPTY for row in board for cell in row)


def valid_free(board, r, c):
    return isinstance(r, int) and isinstance(c, int) \
        and 0 <= r < N and 0 <= c < N and board[r][c] == EMPTY


# ---------------------------------------------------------------------------
# Grafiskais interfeiss
# ---------------------------------------------------------------------------
class TicTacToeGUI:
    def __init__(self, root):
        self.root = root
        root.title("5 pēc kārtas — Swap2")
        root.resizable(False, False)

        self.status = tk.Label(root, font=("Segoe UI", 13, "bold"), anchor="w", padx=12, pady=6)
        self.status.pack(fill="x")
        self.info = tk.Label(root, font=("Segoe UI", 10), fg="#444", anchor="w", padx=12)
        self.info.pack(fill="x")

        size = 2 * PAD + CELL * N
        self.canvas = tk.Canvas(root, width=size, height=size, bg=BOARD_BG, highlightthickness=0)
        self.canvas.pack(padx=12, pady=6)
        self.canvas.bind("<Button-1>", self.on_click)

        self.actions = tk.Frame(root, pady=8)
        self.actions.pack()

        self.game_id = 0
        self.reset()
        self.show_menu()

    # ----------------------------------------------------------- stāvoklis
    def reset(self):
        self.game_id += 1          # atceļ iepriekšējās spēles ieplānotos bota gājienus
        self.board = new_board()
        self.phase = "menu"        # menu | place | wait | choose | play | over
        self.kinds = {}            # 1/2 -> HUMAN/BOT
        self.names = {}            # 1/2 -> nosaukums
        self.colors = {}           # X/O -> 1/2 (kurš spēlētājs ar kuru simbolu)
        self.queue = []            # simboli, kas cilvēkam jānovieto atklātnē
        self.after_place = None    # ko darīt, kad cilvēks tos novietojis
        self.bots_after_opening = False
        self.to_move = None
        self.last = None
        self.win_ends = None
        self.redraw()

    def later(self, fn, delay=None):
        """Ieplāno bota darbību, ja tikmēr nav sākta jauna spēle."""
        gid = self.game_id
        if delay is None:
            delay = BOT_VS_BOT_DELAY if self.kinds.get(1) == self.kinds.get(2) == BOT else BOT_DELAY
        self.root.after(delay, lambda: fn() if gid == self.game_id else None)

    def set_actions(self, buttons):
        for w in self.actions.winfo_children():
            w.destroy()
        for i, (text, cmd) in enumerate(buttons):      # līdz 3 pogām rindā
            tk.Button(self.actions, text=text, command=cmd, font=("Segoe UI", 10),
                      padx=10, pady=3).grid(row=i // 3, column=i % 3, padx=4, pady=3,
                                            sticky="ew")

    def say(self, text):
        self.status.config(text=text)

    def update_info(self):
        if not self.colors:
            self.info.config(text=f"1. spēlētājs: {self.names.get(1, '')}    "
                                  f"2. spēlētājs: {self.names.get(2, '')}")
            return
        parts = [f"{self.names[self.colors[s]]}: {COLOR_NAME[s]}" for s in (X, O)]
        self.info.config(text="    ".join(parts))

    # ------------------------------------------------------------- izvēlne
    def show_menu(self):
        self.reset()
        self.say("Izvēlies spēles režīmu")
        self.info.config(text=f"Bots: {BOT_NAME}.  Uzvar tas, kurš pirmais saliek 5 pēc kārtas.")
        self.set_actions([
            ("Es pret botu — es sāku ar X", self.start_classic),
            ("Swap2: es sāku", lambda: self.start(HUMAN, BOT)),
            ("Swap2: bots sāk", lambda: self.start(BOT, HUMAN)),
            ("Bots pret botu", lambda: self.start(BOT, BOT)),
            ("Es lieku 3 figūras, tālāk bots pret botu",
             lambda: self.start(HUMAN, BOT, bots_after_opening=True)),
        ])

    def start_classic(self):
        """Parastā spēle bez Swap2: cilvēks sāk ar X, bots spēlē ar O."""
        self.reset()
        self.kinds = {1: HUMAN, 2: BOT}
        self.names = {1: "Tu", 2: "Bots"}
        self.colors = {X: 1, O: 2}
        self.set_actions([("Jauna spēle", self.show_menu)])
        self.update_info()
        self.phase = "play"
        self.to_move = X
        self.next_turn("Spēle bez Swap2. ")

    def start(self, first, second, bots_after_opening=False):
        self.reset()
        self.bots_after_opening = bots_after_opening
        self.kinds = {1: first, 2: second}
        if first == second == BOT:
            self.names = {1: "Bots 1", 2: "Bots 2"}
        else:
            self.names = {1: "Tu" if first == HUMAN else "Bots",
                          2: "Tu" if second == HUMAN else "Bots"}
        self.set_actions([("Jauna spēle", self.show_menu)])
        self.update_info()
        self.step_propose()

    # ------------------------------------------------- Swap2 1. solis
    def step_propose(self):
        if self.kinds[1] == HUMAN:
            then = self.hand_over_to_bots if self.bots_after_opening else self.step_respond
            # Noteikumi prasa divus X un vienu O; liekam pamīšus: X, O, X
            self.ask_place([X, O, X], then,
                           "Swap2: novieto 3 figūras pēc kārtas — X, O, X")
        else:
            self.phase = "wait"
            self.say(f"{self.names[1]} novieto 3 sākuma figūras...")
            self.later(self.bot_propose)

    def hand_over_to_bots(self):
        """Cilvēks novietoja sākuma figūras — tālāk abu spēlētāju vietā spēlē bots."""
        self.kinds = {1: BOT, 2: BOT}
        self.names = {1: "Bots 1", 2: "Bots 2"}
        self.update_info()
        self.step_respond()

    def bot_propose(self):
        moves = swap2_propose(copy_board(self.board))
        if not self.apply_bot_stones(moves, [X, X, O], "swap2_propose"):
            return
        self.step_respond()

    # ------------------------------------------------- Swap2 2. solis
    def step_respond(self):
        if self.kinds[2] == HUMAN:
            self.phase = "choose"
            self.say("Swap2: izvēlies — ņemt X, ņemt O vai novietot vēl divas figūras")
            self.set_actions([
                ("Ņemt X", lambda: self.handle_response({"action": "TAKE_X"})),
                ("Ņemt O", lambda: self.handle_response({"action": "TAKE_O"})),
                ("Novietot vēl X un O", lambda: self.handle_response({"action": "PLACE_TWO"})),
                ("Jauna spēle", self.show_menu),
            ])
        else:
            self.phase = "wait"
            self.say(f"{self.names[2]} izvērtē sākuma pozīciju...")
            self.later(lambda: self.handle_response(swap2_respond(copy_board(self.board))))

    def handle_response(self, resp):
        self.set_actions([("Jauna spēle", self.show_menu)])
        action = resp.get("action") if isinstance(resp, dict) else None
        if action == "TAKE_X":
            self.colors = {X: 2, O: 1}
            self.begin_play(f"{self.names[2]} izvēlējās X.")
        elif action == "TAKE_O":
            self.colors = {X: 1, O: 2}
            self.begin_play(f"{self.names[2]} izvēlējās O.")
        elif action == "PLACE_TWO":
            if self.kinds[2] == HUMAN:
                self.ask_place([X, O], self.step_final, "Swap2: novieto vēl vienu X un vienu O")
            else:
                if self.apply_bot_stones(resp.get("moves"), [X, O], "swap2_respond"):
                    self.step_final()
        else:
            self.bot_error(f"swap2_respond atgrieza nederīgu atbildi: {resp!r}")

    # ------------------------------------------------- Swap2 3. solis
    def step_final(self):
        if self.kinds[1] == HUMAN:
            self.phase = "choose"
            self.say("Swap2: izvēlies, ar kuru simbolu spēlēsi")
            self.set_actions([
                ("Spēlēt ar X", lambda: self.handle_final(X)),
                ("Spēlēt ar O", lambda: self.handle_final(O)),
                ("Jauna spēle", self.show_menu),
            ])
        else:
            self.phase = "wait"
            self.say(f"{self.names[1]} izvēlas krāsu...")
            self.later(lambda: self.handle_final(swap2_final_choice(copy_board(self.board))))

    def handle_final(self, choice):
        self.set_actions([("Jauna spēle", self.show_menu)])
        if choice not in (X, O):
            self.bot_error(f"swap2_final_choice atgrieza nederīgu izvēli: {choice!r}")
            return
        other = O if choice == X else X
        self.colors = {choice: 1, other: 2}
        self.begin_play(f"{self.names[1]} izvēlējās {choice}.")

    # ------------------------------------------------- atklātnes palīgi
    def ask_place(self, symbols, then, title):
        self.phase = "place"
        self.queue = list(symbols)
        self.after_place = then
        self.place_title = title
        self.say(f"{title}. Tagad: {self.queue[0]}")

    def apply_bot_stones(self, moves, expected, fname):
        """Pārbauda un uzliek bota atklātnes figūras. Atgriež True, ja viss kārtībā."""
        try:
            symbols = [m[2] for m in moves]
            ok = len(moves) == len(expected) and sorted(symbols) == sorted(expected)
        except Exception:
            ok = False
        if ok:
            tmp = copy_board(self.board)
            for r, c, sym in moves:
                if not valid_free(tmp, r, c):
                    ok = False
                    break
                tmp[r][c] = sym
        if not ok:
            self.bot_error(f"{fname} atgrieza nederīgas figūras: {moves!r}")
            return False
        self.board = tmp
        self.last = (moves[-1][0], moves[-1][1])
        self.redraw()
        return True

    # ------------------------------------------------------- pamatspēle
    def begin_play(self, msg):
        self.update_info()
        self.to_move = O                   # pēc atklātnes gājienu veic O
        self.phase = "play"
        self.next_turn(msg + " ")

    def next_turn(self, prefix=""):
        player = self.colors[self.to_move]
        if self.kinds[player] == BOT:
            self.say(f"{prefix}{self.names[player]} ({self.to_move}) domā...")
            self.later(self.bot_turn)
        else:
            self.say(f"{prefix}Tavs gājiens: {COLOR_NAME[self.to_move]}")

    def bot_turn(self):
        move = get_move(copy_board(self.board), self.to_move)
        try:
            r, c = move
        except Exception:
            r = c = None
        if not valid_free(self.board, r, c):
            self.bot_error(f"get_move atgrieza nederīgu gājienu: {move!r}")
            return
        self.make_move(r, c)

    def make_move(self, r, c):
        p = self.to_move
        self.board[r][c] = p
        self.last = (r, c)
        self.win_ends = five_line(self.board, r, c)
        self.redraw()
        if self.win_ends:
            self.finish(f"{self.names[self.colors[p]]} ({p}) uzvar — 5 pēc kārtas!")
        elif is_full(self.board):
            self.finish("Neizšķirts — laukums ir pilns.")
        else:
            self.to_move = O if p == X else X
            self.next_turn()

    def finish(self, msg):
        self.phase = "over"
        self.say(msg)
        self.set_actions([("Jauna spēle", self.show_menu)])

    def bot_error(self, msg):
        self.phase = "over"
        self.say("Bota kļūda")
        self.info.config(text=msg)
        self.set_actions([("Jauna spēle", self.show_menu)])

    # ------------------------------------------------------- klikšķi
    def on_click(self, event):
        c = (event.x - PAD) // CELL
        r = (event.y - PAD) // CELL
        if not (0 <= r < N and 0 <= c < N) or self.board[r][c] != EMPTY:
            return
        if self.phase == "place":
            self.board[r][c] = self.queue.pop(0)
            self.last = (r, c)
            self.redraw()
            if self.queue:
                self.say(f"{self.place_title}. Tagad: {self.queue[0]}")
            else:
                self.phase = "wait"
                self.after_place()
        elif self.phase == "play" and self.kinds[self.colors[self.to_move]] == HUMAN:
            self.make_move(r, c)

    # ------------------------------------------------------- zīmēšana
    def redraw(self):
        cv = self.canvas
        cv.delete("all")
        end = PAD + CELL * N
        for i in range(N + 1):
            x = PAD + i * CELL
            cv.create_line(x, PAD, x, end, fill=LINE_COLOR)
            cv.create_line(PAD, x, end, x, fill=LINE_COLOR)
        for i in range(N):
            mid = PAD + i * CELL + CELL // 2
            cv.create_text(mid, PAD // 2, text=str(i), fill=LINE_COLOR, font=("Segoe UI", 8))
            cv.create_text(PAD // 2, mid, text=str(i), fill=LINE_COLOR, font=("Segoe UI", 8))

        if self.last:                      # pēdējā gājiena rūtiņu iekrāso gaišāku
            r, c = self.last
            x0, y0 = PAD + c * CELL, PAD + r * CELL
            cv.create_rectangle(x0 + 1, y0 + 1, x0 + CELL - 1, y0 + CELL - 1,
                                fill="#f3dcb2", outline="#d62828", width=2)

        m = 8
        for r in range(N):
            for c in range(N):
                s = self.board[r][c]
                if s == EMPTY:
                    continue
                x0, y0 = PAD + c * CELL + m, PAD + r * CELL + m
                x1, y1 = x0 + CELL - 2 * m, y0 + CELL - 2 * m
                if s == X:
                    cv.create_line(x0, y0, x1, y1, fill=X_COLOR, width=4, capstyle="round")
                    cv.create_line(x0, y1, x1, y0, fill=X_COLOR, width=4, capstyle="round")
                else:
                    cv.create_oval(x0, y0, x1, y1, outline=O_COLOR, width=4)

        if self.win_ends:
            (r1, c1), (r2, c2) = self.win_ends
            cv.create_line(*self.center(r1, c1), *self.center(r2, c2),
                           fill="#d62828", width=4, capstyle="round")

    @staticmethod
    def center(r, c):
        return PAD + c * CELL + CELL // 2, PAD + r * CELL + CELL // 2


def main():
    root = tk.Tk()
    TicTacToeGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
