import copy
import glob
import importlib.util
import re
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from tkinter import ttk

# === KONFIGURĀCIJA ===
BOARD_SIZE = 15
WIN_LEN = 5
MOVE_TIMEOUT = 1.0  # Sekundes vienam gājienam / Swap2 lēmumam
BOTS_PATTERN = "tic-tac-toe/*/bot.py"
STUDENT_BOTS_PATTERN = "studenti/*/bot.py"


def create_board() -> list[list[str]]:
    return [["_" for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]


def is_valid_coord(r: int, c: int) -> bool:
    return isinstance(r, int) and isinstance(c, int) and 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE


def check_winner(board: list[list[str]], last_r: int, last_c: int, player: str) -> bool:
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    for dr, dc in directions:
        count = 1
        r, c = last_r + dr, last_c + dc
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == player:
            count += 1
            r += dr
            c += dc

        r, c = last_r - dr, last_c - dc
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == player:
            count += 1
            r -= dr
            c -= dc

        if count >= WIN_LEN:
            return True
    return False


def load_bots(pattern: str) -> list[dict]:
    """Noskenē tic-tac-toe/<studenta_vards>/bot.py un ielādē derīgos botus."""
    bots = []
    required_funcs = ["get_move", "swap2_propose", "swap2_respond", "swap2_final_choice"]

    for file_str in sorted(glob.glob(pattern)):
        path = Path(file_str)
        student_folder = path.parent.name
        try:
            spec = importlib.util.spec_from_file_location(f"bot_{student_folder}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            missing = [f for f in required_funcs if not hasattr(module, f)]
            if missing:
                print(f"[IZLAISTS] {file_str} — trūkst funkciju: {', '.join(missing)}")
                continue

            bots.append({
                "id": student_folder,
                "name": getattr(module, "BOT_NAME", student_folder),
                "get_move": module.get_move,
                "swap2_propose": module.swap2_propose,
                "swap2_respond": module.swap2_respond,
                "swap2_final_choice": module.swap2_final_choice,
                "record_result": getattr(module, "record_result", None),
            })
        except Exception as e:
            print(f"[IELĀDES KĻŪDA] {file_str}: {e}")

    return bots


def run_with_timeout(func, *args):
    """Izsauc bota funkciju ar dziļajām argumentu kopijām un laika limitu."""
    safe_args = [copy.deepcopy(a) for a in args]
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *safe_args)
        return future.result(timeout=MOVE_TIMEOUT)


def validate_moves_list(board: list[list[str]], moves, expected_symbols: list[str]) -> bool:
    """Pārbauda Swap2 gājienu sarakstu (garums, simboli, koordinātu brīvība un unikalitāte)."""
    if not isinstance(moves, (list, tuple)) or len(moves) != len(expected_symbols):
        return False

    seen_coords = set()
    symbols = []
    for item in moves:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            return False
        r, c, sym = item
        if not is_valid_coord(r, c) or board[r][c] != "_" or (r, c) in seen_coords:
            return False
        seen_coords.add((r, c))
        symbols.append(sym)

    return sorted(symbols) == sorted(expected_symbols)


def play_match(p1: dict, p2: dict, on_board=None) -> tuple[str, str]:
    """
    Izspēlē vienu pilnu partiju (Swap2 atklātne + pamatspēle).
    p1 = 1. spēlētājs (izliek pirmās 3 figūras), p2 = 2. spēlētājs.
    Atgriež: (uzvarētāja_id vai 'DRAW', apraksts)
    """
    board = create_board()

    def finish(winner_id: str, reason: str) -> tuple[str, str]:
        for participant in (p1, p2):
            callback = participant.get("record_result")
            if callable(callback):
                outcome = "draw" if winner_id == "DRAW" else (
                    "win" if participant["id"] == winner_id else "loss"
                )
                callback(outcome)
        return winner_id, reason

    # === 1. SOLIS: Swap2 — 1. spēlētājs uzliek 2x 'X' un 1x 'O' ===
    try:
        opening_moves = run_with_timeout(p1["swap2_propose"], board)
    except TimeoutError:
        return finish(p2["id"], f"{p1['name']} pārsniedza laiku (swap2_propose)")
    except Exception as e:
        return finish(p2["id"], f"{p1['name']} kļūda swap2_propose: {e}")

    if not validate_moves_list(board, opening_moves, ["X", "X", "O"]):
        return finish(p2["id"], f"{p1['name']} nelegāls sākuma izvietojums: {opening_moves}")

    for r, c, sym in opening_moves:
        board[r][c] = sym
    if on_board:
        on_board(copy.deepcopy(board))

    # === 2. SOLIS: Swap2 — 2. spēlētājs izvēlas darbību ===
    try:
        response = run_with_timeout(p2["swap2_respond"], board)
    except TimeoutError:
        return finish(p1["id"], f"{p2['name']} pārsniedza laiku (swap2_respond)")
    except Exception as e:
        return finish(p1["id"], f"{p2['name']} kļūda swap2_respond: {e}")

    if not isinstance(response, dict) or "action" not in response:
        return finish(p1["id"], f"{p2['name']} atgrieza nederīgu Swap2 atbildi")

    action = response["action"]
    bot_x = None
    bot_o = None

    if action == "TAKE_O":
        bot_x, bot_o = p1, p2
    elif action == "TAKE_X":
        bot_x, bot_o = p2, p1
    elif action == "PLACE_TWO":
        extra_moves = response.get("moves")
        if not validate_moves_list(board, extra_moves, ["X", "O"]):
            return finish(p1["id"], f"{p2['name']} nelegāli papildgājieni (PLACE_TWO)")
        for r, c, sym in extra_moves:
            board[r][c] = sym
        if on_board:
            on_board(copy.deepcopy(board))

        # === 3. SOLIS: 1. spēlētājs izvēlas galīgo krāsu ===
        try:
            final_sym = run_with_timeout(p1["swap2_final_choice"], board)
        except TimeoutError:
            return finish(p2["id"], f"{p1['name']} pārsniedza laiku (swap2_final_choice)")
        except Exception as e:
            return finish(p2["id"], f"{p1['name']} kļūda swap2_final_choice: {e}")

        if final_sym == "X":
            bot_x, bot_o = p1, p2
        elif final_sym == "O":
            bot_x, bot_o = p2, p1
        else:
            return finish(p2["id"], f"{p1['name']} nederīga krāsas izvēle: {final_sym}")
    else:
        return finish(p1["id"], f"{p2['name']} nezināma Swap2 darbība: {action}")

    # === 4. SOLIS: Pamatspēli sāk 'O' (4. vai 6. gājiens). ===
    placed_count = sum(cell != "_" for row in board for cell in row)
    turn_order = [("O", bot_o), ("X", bot_x)]

    for step in range(BOARD_SIZE * BOARD_SIZE - placed_count):
        symbol, current_bot = turn_order[step % 2]
        opponent_bot = turn_order[(step + 1) % 2][1]

        try:
            move = run_with_timeout(current_bot["get_move"], board, symbol)
        except TimeoutError:
            return finish(opponent_bot["id"], f"{current_bot['name']} pārsniedza laiku ({MOVE_TIMEOUT}s)")
        except Exception as e:
            return finish(opponent_bot["id"], f"{current_bot['name']} kļūda kodā: {e}")

        if not isinstance(move, (tuple, list)) or len(move) != 2:
            return finish(opponent_bot["id"], f"{current_bot['name']} nederīgs gājiena formāts: {move}")

        r, c = move
        if not is_valid_coord(r, c) or board[r][c] != "_":
            return finish(opponent_bot["id"], f"{current_bot['name']} nelegāls gājiens: {(r, c)}")

        board[r][c] = symbol
        total_moves = placed_count + step + 1
        if on_board:
            on_board(copy.deepcopy(board))

        if check_winner(board, r, c, symbol):
            return finish(current_bot["id"], f"5 rindā ({symbol}, {total_moves}. gājienā)")

    return finish("DRAW", "Laukums pilns (neizšķirts)")


def print_standings(stats: dict, title: str = "PAŠREIZĒJĀ TABULA"):
    ranking = sorted(stats.values(), key=lambda x: (x["pts"], x["w"], -x["err"]), reverse=True)
    print(f"\n--- {title} ---")
    print(f"{'Vieta':<6} {'Dalībnieks / Bots':<30} {'Pkt':<6} {'Spēles':<7} {'U':<4} {'N':<4} {'Z':<4} {'Tech.Z'}")
    print("-" * 74)
    for pos, row in enumerate(ranking, start=1):
        games = row["w"] + row["d"] + row["l"]
        print(
            f"{pos:<6} {row['label'][:29]:<30} {row['pts']:<6.1f} "
            f"{games:<7} {row['w']:<4} {row['d']:<4} {row['l']:<4} {row['err']}"
        )
    print("-" * 74 + "\n")


def run_tournament():
    bots_by_id = {
        bot["id"]: bot
        for pattern in (BOTS_PATTERN, STUDENT_BOTS_PATTERN)
        for bot in load_bots(pattern)
    }
    bots = list(bots_by_id.values())
    n = len(bots)

    if n < 2:
        print(f"Atrasti tikai {n} derīgi boti. Turnīram vajag vismaz 2.")
        return

    print("=" * 74)
    print(f"ATRASKTI {n} DALĪBNIEKI:")
    for b in bots:
        print(f"  • {b['id']} -> {b['name']}")
    print("=" * 74)

    stats = {
        b["id"]: {
            "label": f"{b['name']} ({b['id']})",
            "pts": 0.0,
            "w": 0,
            "d": 0,
            "l": 0,
            "err": 0,
        }
        for b in bots
    }

    # Katrs ar katru izspēlē 2 spēles (mainoties lomām: P1 un P2 Swap2 atklātnē)
    total_matches = n * (n - 1)
    match_num = 0

    for i in range(n):
        for j in range(n):
            if i == j:
                continue

            match_num += 1
            p1 = bots[i]
            p2 = bots[j]

            print(f"[{match_num}/{total_matches}] Spēlē: {p1['name']} (P1) vs {p2['name']} (P2) ... ", end="", flush=True)
            t_start = time.time()
            winner_id, reason = play_match(p1, p2)
            elapsed = time.time() - t_start

            if winner_id == "DRAW":
                print(f"NEIZŠĶIRTS ({elapsed:.1f}s) — {reason}")
                stats[p1["id"]]["pts"] += 0.5
                stats[p2["id"]]["pts"] += 0.5
                stats[p1["id"]]["d"] += 1
                stats[p2["id"]]["d"] += 1
            else:
                loser_id = p2["id"] if winner_id == p1["id"] else p1["id"]
                winner_name = stats[winner_id]["label"]
                print(f"UZVARA: {winner_name} ({elapsed:.1f}s) — {reason}")

                stats[winner_id]["pts"] += 1.0
                stats[winner_id]["w"] += 1
                stats[loser_id]["l"] += 1

                if "5 rindā" not in reason:
                    stats[loser_id]["err"] += 1

            # Parāda aktuālo līderu tabulu pēc katras partijas
            print_standings(stats, title=f"STĀVOKLIS PĒC {match_num}. PARTIJAS")
            time.sleep(0.4)  # Neliela pauze, lai ekrānā var izsekot gaitai

    print_standings(stats, title="TURNĪRA GALA REZULTĀTI")


class TournamentGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Gomoku turnīra vadība")
        self.root.geometry("1280x760")
        self.root.configure(bg="#eef1f5")

        self.bots = load_bots(BOTS_PATTERN)
        self.running = False
        self.stats = {}
        self.archive = []
        self.recent_boards = []
        self.recent_results = []
        self.current_board = create_board()

        self._build_layout()

    def _build_layout(self):
        top = tk.Frame(self.root, bg="#eef1f5", pady=8)
        top.pack(fill="x")

        tk.Label(top, text="Turnīra interfeiss", font=("Segoe UI", 18, "bold"),
                 bg="#eef1f5").pack(side="left", padx=12)
        tk.Button(top, text="Sākt turnīru", command=self.start,
                  bg="#2f6fed", fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=12).pack(side="left")
        tk.Button(top, text="Apturēt", command=self.stop,
                  bg="#7b8794", fg="white", relief="flat", padx=12).pack(side="left", padx=6)

        tk.Label(top, text="Spēles pārī:", bg="#eef1f5").pack(side="left", padx=(20, 4))
        self.games_var = tk.IntVar(value=2)
        tk.Spinbox(top, from_=1, to=20, textvariable=self.games_var, width=4).pack(side="left")

        tk.Label(top, text="Gājiena pauze:", bg="#eef1f5").pack(side="left", padx=(12, 4))
        self.delay_var = tk.DoubleVar(value=0.15)
        tk.Spinbox(top, from_=0.0, to=2.0, increment=0.05,
                   textvariable=self.delay_var, width=5).pack(side="left")
        tk.Label(top, text="sek.", bg="#eef1f5").pack(side="left", padx=4)

        body = tk.Frame(self.root, bg="#eef1f5")
        body.pack(fill="both", expand=True, padx=10)

        left = tk.Frame(body, bg="white", width=220)
        left.pack(side="left", fill="y", padx=(0, 8))
        tk.Label(left, text="Dalībnieki", font=("Segoe UI", 12, "bold"),
                 bg="white").pack(anchor="w", padx=10, pady=(8, 4))
        self.participant_list = tk.Listbox(left, font=("Segoe UI", 10), relief="flat")
        self.participant_list.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for bot in self.bots:
            self.participant_list.insert("end", f"{bot['name']} ({bot['id']})")

        center = tk.Frame(body, bg="#eef1f5")
        center.pack(side="left", fill="both", expand=True)
        self.status_var = tk.StringVar(value="Gaidām turnīra sākumu")
        tk.Label(center, textvariable=self.status_var, font=("Segoe UI", 11, "bold"),
                 bg="#eef1f5").pack(pady=(0, 6))

        self.board_canvas = tk.Canvas(center, width=510, height=510,
                                      bg="#d9aa63", highlightthickness=1,
                                      highlightbackground="#7b5a32")
        self.board_canvas.pack()
        self.draw_board(create_board())

        right = tk.Frame(body, bg="white", width=330)
        right.pack(side="right", fill="y")
        standings_tab = tk.Frame(right, bg="white")
        standings_tab.pack(fill="both", expand=True)
        tk.Label(standings_tab, text="Turnīra tabula", font=("Segoe UI", 11, "bold"),
                 bg="white").pack(anchor="w", padx=4, pady=(6, 2))

        columns = ("vieta", "bots", "pkt", "s", "u", "n", "z")
        self.standings = ttk.Treeview(standings_tab, columns=columns,
                                      show="headings", height=8)
        headings = ("V.", "Dalībnieks", "Pkt", "S", "U", "N", "Z")
        widths = (38, 150, 48, 38, 38, 38, 38)
        for column, heading, width in zip(columns, headings, widths):
            self.standings.heading(column, text=heading)
            self.standings.column(column, width=width, anchor="center")
        self.standings.pack(fill="both", expand=False, padx=4, pady=(0, 4))

        archive_tab = tk.Frame(right, bg="white")
        archive_tab.pack(fill="both", expand=True)
        tk.Label(archive_tab, text="Spēļu arhīvs", font=("Segoe UI", 11, "bold"),
                 bg="white").pack(anchor="w", padx=4, pady=(6, 2))

        self.archive_list = tk.Listbox(archive_tab, font=("Segoe UI", 9),
                                       relief="flat")
        self.archive_list.pack(fill="both", expand=True, padx=4, pady=4)

        bottom = tk.Frame(self.root, bg="#eef1f5")
        bottom.pack(fill="x", padx=10, pady=8)
        tk.Label(bottom, text="Spēļu vēsture", font=("Segoe UI", 11, "bold"),
                 bg="#eef1f5").pack(anchor="w")
        self.recent_frame = tk.Frame(bottom, bg="#eef1f5")
        self.recent_frame.pack(fill="x")
        self.root.bind("<Configure>", self._on_window_resize)

    def _on_window_resize(self, event):
        if event.widget != self.root:
            return
        if hasattr(self, "_resize_job"):
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(150, self.draw_recent)

    def draw_board(self, board):
        canvas = self.board_canvas
        canvas.delete("all")
        size = 510
        margin = 15
        cell = (size - 2 * margin) / BOARD_SIZE

        for i in range(BOARD_SIZE + 1):
            pos = margin + i * cell
            canvas.create_line(pos, margin, pos, size - margin, fill="#8d663b")
            canvas.create_line(margin, pos, size - margin, pos, fill="#8d663b")

        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                value = board[r][c]
                if value == "_":
                    continue
                cx = margin + (c + 0.5) * cell
                cy = margin + (r + 0.5) * cell
                color = "#b51f1f" if value == "X" else "#1f5fb5"
                font_size = max(7, int(cell * 0.58))
                canvas.create_text(cx, cy, text=value, fill=color,
                                   font=("Segoe UI", font_size, "bold"))

    def draw_recent(self):
        for widget in self.recent_frame.winfo_children():
            widget.destroy()

        available_width = max(300, self.root.winfo_width() - 30)
        max_cards = max(1, available_width // 230)
        recent = self.recent_boards[-max_cards:]
        if not recent:
            return

        card_size = min(220, max(150, available_width // len(recent) - 10))

        for board, title in recent:
            frame = tk.Frame(self.recent_frame, bg="white", bd=1, relief="solid")
            frame.pack(side="left", fill="both", expand=True, padx=5)
            canvas = tk.Canvas(frame, width=card_size, height=card_size,
                               bg="#d9aa63", highlightthickness=0)
            canvas.pack()
            margin = 5
            size = card_size
            cell = (size - 2 * margin) / BOARD_SIZE
            for i in range(BOARD_SIZE + 1):
                pos = margin + i * cell
                canvas.create_line(pos, margin, pos, size - margin, fill="#8d663b", width=1)
                canvas.create_line(margin, pos, size - margin, pos, fill="#8d663b", width=1)
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    value = board[r][c]
                    if value != "_":
                        cx = margin + (c + 0.5) * cell
                        cy = margin + (r + 0.5) * cell
                        color = "#b51f1f" if value == "X" else "#1f5fb5"
                        font_size = max(4, int(cell * 0.58))
                        canvas.create_text(cx, cy, text=value, fill=color,
                                           font=("Segoe UI", font_size, "bold"))
            tk.Label(frame, text=title, bg="white", font=("Segoe UI", 8)).pack()

    def start(self):
        if self.running:
            return
        if len(self.bots) < 2:
            self.status_var.set("Turnīram nepieciešami vismaz 2 boti")
            return

        self.running = True
        self.archive.clear()
        self.archive_list.delete(0, "end")
        self.recent_boards.clear()
        self.recent_results.clear()
        self.draw_recent()
        self.stats = {
            bot["id"]: {
                "label": f"{bot['name']} ({bot['id']})",
                "pts": 0.0, "w": 0, "d": 0, "l": 0, "err": 0
            }
            for bot in self.bots
        }
        self.refresh_standings()
        threading.Thread(target=self.run_thread, daemon=True).start()

    def stop(self):
        self.running = False
        self.status_var.set("Turnīra apturēšana...")

    def board_callback(self, board):
        self.current_board = copy.deepcopy(board)
        self.root.after(0, lambda: self.draw_board(board))
        delay = max(0.0, float(self.delay_var.get()))
        time.sleep(delay)

    def run_thread(self):
        games_per_pair = max(1, int(self.games_var.get()))
        total_matches = len(self.bots) * (len(self.bots) - 1) * games_per_pair
        match_num = 0

        for i in range(len(self.bots)):
            for j in range(len(self.bots)):
                if i == j:
                    continue
                for game in range(games_per_pair):
                    if not self.running:
                        self.root.after(0, lambda: self.status_var.set("Turnīrs apturēts"))
                        return

                    match_num += 1
                    p1 = self.bots[i] if game % 2 == 0 else self.bots[j]
                    p2 = self.bots[j] if game % 2 == 0 else self.bots[i]
                    self.current_board = create_board()
                    self.root.after(0, lambda: self.draw_board(create_board()))
                    self.root.after(0, lambda p1=p1, p2=p2, n=match_num:
                                    self.status_var.set(
                                        f"{n}/{total_matches}: {p1['name']} vs {p2['name']}"))

                    winner_id, reason = play_match(p1, p2, self.board_callback)
                    if winner_id == "DRAW":
                        self.stats[p1["id"]]["pts"] += 0.5
                        self.stats[p2["id"]]["pts"] += 0.5
                        self.stats[p1["id"]]["d"] += 1
                        self.stats[p2["id"]]["d"] += 1
                        score = "1/2-1/2"
                        move_match = re.search(r"(\d+)\. gājienā", reason)
                        end_info = f"; {move_match.group(1)}. gājiens" if move_match else ""
                    else:
                        loser_id = p2["id"] if winner_id == p1["id"] else p1["id"]
                        self.stats[winner_id]["pts"] += 1.0
                        self.stats[winner_id]["w"] += 1
                        self.stats[loser_id]["l"] += 1
                        if "5 rindā" not in reason:
                            self.stats[loser_id]["err"] += 1
                        score = "1:0" if winner_id == p1["id"] else "0:1"
                        move_match = re.search(r"(\d+)\. gājienā", reason)
                        end_info = f"; {move_match.group(1)}. gājiens" if move_match else ""

                    archive_text = (
                        f"{match_num}. {p1['name']} vs {p2['name']} — "
                        f"{score}{end_info}"
                    )
                    self.archive.append(archive_text)
                    final_board = copy.deepcopy(self.current_board)
                    self.recent_boards.append((final_board, f"{match_num}. {p1['name']} – {p2['name']}"))
                    self.root.after(0, lambda text=archive_text:
                                    self.archive_list.insert("end", text))
                    self.root.after(0, lambda: self.archive_list.see("end"))
                    self.root.after(0, self.refresh_standings)
                    self.root.after(0, self.draw_recent)

        self.running = False
        self.root.after(0, lambda: self.status_var.set("Turnīrs pabeigts"))
        self.root.after(0, self.refresh_standings)

    def refresh_standings(self):
        for item in self.standings.get_children():
            self.standings.delete(item)
        ranking = sorted(self.stats.values(),
                         key=lambda x: (x["pts"], x["w"], -x["err"]),
                         reverse=True)
        for place, row in enumerate(ranking, start=1):
            games = row["w"] + row["d"] + row["l"]
            self.standings.insert("", "end", values=(
                place, row["label"], f"{row['pts']:.1f}",
                games, row["w"], row["d"], row["l"]
            ))


if __name__ == "__main__":
    root = tk.Tk()
    app = TournamentGUI(root)
    root.mainloop()