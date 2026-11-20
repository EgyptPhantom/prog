"""
Turnīra tiesnesis 5-rindu Tic-Tac-Toe botiem (noteikumi: ../RULES.md).

Palaiž botus vienu pret otru ar Swap2 atklātni un pārbauda noteikumus:
  * atgriezto vērtību formātu un gājienu derīgumu;
  * laika limitu (1.0 s uz izsaukumu);
  * vai bots nemaina padoto `board` sarakstu.
Noteikumu pārkāpums = zaudējums.

Lietošana:
  python arena.py                                  # peteris_punins pret Test1 un Test2
  python arena.py A/bot.py B/bot.py -n 10          # konkrēti boti, 10 spēles
  python arena.py A/bot.py B/bot.py -n 1 --show    # parāda gala laukumu
"""

import argparse
import copy
import importlib.util
import os
import sys
import time

N = 15
EMPTY = "_"
TIME_LIMIT = 1.0
HERE = os.path.dirname(os.path.abspath(__file__))


class Violation(Exception):
    """Bots pārkāpa noteikumus."""


def load_bot(path):
    path = os.path.abspath(path)
    name = "bot_" + str(abs(hash(path)))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PATH = path
    return module


def bot_label(bot):
    return getattr(bot, "BOT_NAME", os.path.basename(os.path.dirname(bot.PATH)))


class Stats:
    def __init__(self):
        self.max_time = 0.0
        self.total_time = 0.0
        self.calls = 0


def call(bot, fname, board, stats, *args):
    """Izsauc bota funkciju ar laukuma kopiju, mēra laiku, pārbauda modificēšanu."""
    arg = copy.deepcopy(board)
    t0 = time.perf_counter()
    try:
        result = getattr(bot, fname)(arg, *args)
    except Exception as e:
        raise Violation(f"{fname} izmeta kļūdu: {e!r}")
    dt = time.perf_counter() - t0
    s = stats[bot.PATH]
    s.max_time = max(s.max_time, dt)
    s.total_time += dt
    s.calls += 1
    if arg != board:
        raise Violation(f"{fname} modificēja board")
    if dt > TIME_LIMIT:
        raise Violation(f"{fname} domāja {dt:.2f} s (> {TIME_LIMIT} s)")
    return result


def check_cell(board, r, c, what):
    if not (isinstance(r, int) and isinstance(c, int)):
        raise Violation(f"{what}: koordinātām jābūt int, nevis {r!r}, {c!r}")
    if not (0 <= r < N and 0 <= c < N):
        raise Violation(f"{what}: koordinātas ārpus laukuma {(r, c)}")
    if board[r][c] != EMPTY:
        raise Violation(f"{what}: rūtiņa {(r, c)} nav brīva")


def is_five(board, r, c):
    p = board[r][c]
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        cnt = 1
        for sgn in (1, -1):
            rr, cc = r + sgn * dr, c + sgn * dc
            while 0 <= rr < N and 0 <= cc < N and board[rr][cc] == p:
                cnt += 1
                rr += sgn * dr
                cc += sgn * dc
        if cnt >= 5:
            return True
    return False


def play_game(first, second, stats, show=False):
    """
    Viena spēle. `first` ir 1. spēlētājs (sāk Swap2).
    Atgriež (uzvarētājs vai None, iemesls, gājienu skaits).
    """
    board = [[EMPTY] * N for _ in range(N)]
    current = first
    try:
        # --- Swap2 1. solis ---
        current = first
        prop = call(first, "swap2_propose", board, stats)
        if not isinstance(prop, (list, tuple)) or len(prop) != 3:
            raise Violation("swap2_propose: jāatgriež 3 elementi")
        if sorted(m[2] for m in prop) != ["O", "X", "X"]:
            raise Violation("swap2_propose: jābūt diviem X un vienam O")
        for r, c, sym in prop:
            check_cell(board, r, c, "swap2_propose")
            board[r][c] = sym

        # --- Swap2 2. solis ---
        current = second
        resp = call(second, "swap2_respond", board, stats)
        action = resp.get("action") if isinstance(resp, dict) else None
        if action == "TAKE_X":
            colors = {"X": second, "O": first}
        elif action == "TAKE_O":
            colors = {"X": first, "O": second}
        elif action == "PLACE_TWO":
            moves = resp.get("moves")
            if not isinstance(moves, (list, tuple)) or len(moves) != 2 \
                    or [m[2] for m in moves] != ["X", "O"]:
                raise Violation("PLACE_TWO: jābūt [(r, c, 'X'), (r, c, 'O')]")
            for r, c, sym in moves:
                check_cell(board, r, c, "PLACE_TWO")
                board[r][c] = sym
            # --- Swap2 3. solis ---
            current = first
            choice = call(first, "swap2_final_choice", board, stats)
            if choice == "X":
                colors = {"X": first, "O": second}
            elif choice == "O":
                colors = {"X": second, "O": first}
            else:
                raise Violation(f"swap2_final_choice: nederīga izvēle {choice!r}")
        else:
            raise Violation(f"swap2_respond: nederīga atbilde {resp!r}")

        # --- Pamatspēle: nākamo gājienu veic O ---
        to_move = "O"
        moves_made = 0
        while True:
            current = colors[to_move]
            mv = call(current, "get_move", board, stats, to_move)
            if not isinstance(mv, tuple) or len(mv) != 2:
                raise Violation(f"get_move: jāatgriež (rinda, kolonna), nevis {mv!r}")
            r, c = mv
            check_cell(board, r, c, "get_move")
            board[r][c] = to_move
            moves_made += 1
            if is_five(board, r, c):
                if show:
                    print_board(board, (r, c))
                return current, f"5 pēc kārtas ({to_move})", moves_made
            if all(cell != EMPTY for row in board for cell in row):
                return None, "neizšķirts", moves_made
            to_move = "X" if to_move == "O" else "O"
    except Violation as v:
        winner = second if current is first else first
        return winner, f"{bot_label(current)} pārkāpums: {v}", 0


def print_board(board, last=None):
    print("    " + " ".join(f"{c:x}" for c in range(N)))
    for r in range(N):
        row = []
        for c in range(N):
            ch = board[r][c]
            row.append("." if ch == EMPTY else ch.lower() if (r, c) != last else ch)
        print(f"{r:2x}  " + " ".join(row))


def match(path_a, path_b, games, show=False):
    a, b = load_bot(path_a), load_bot(path_b)
    stats = {a.PATH: Stats(), b.PATH: Stats()}
    score = {a.PATH: 0, b.PATH: 0, None: 0}
    print(f"\n=== {bot_label(a)}  pret  {bot_label(b)}  ({games} spēles) ===")
    for i in range(games):
        first, second = (a, b) if i % 2 == 0 else (b, a)
        winner, reason, n = play_game(first, second, stats, show)
        score[winner.PATH if winner else None] += 1
        w = bot_label(winner) if winner else "-"
        print(f"  {i + 1:2}. sāk {bot_label(first):<18} uzvar: {w:<18} {reason}, {n} gāj.")
    for bot in (a, b):
        s = stats[bot.PATH]
        avg = s.total_time / s.calls if s.calls else 0
        print(f"  {bot_label(bot):<18} uzvaras: {score[bot.PATH]:2}   "
              f"max laiks: {s.max_time:.3f} s   vid.: {avg:.3f} s")
    print(f"  neizšķirti: {score[None]}")
    return score[a.PATH], score[b.PATH], score[None]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")    # latviešu burti Windows konsolē
    except Exception:
        pass
    ap =argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bots", nargs="*", help="bot.py ceļi (2 gab.)")
    ap.add_argument("-n", "--games", type=int, default=4)
    ap.add_argument("--show", action="store_true", help="parādīt gala laukumu")
    args = ap.parse_args()

    if len(args.bots) == 2:
        match(args.bots[0], args.bots[1], args.games, args.show)
    else:
        mine = os.path.join(HERE, "peteris_punins", "bot.py")
        for opp in ("Test1", "Test2"):
            match(mine, os.path.join(HERE, opp, "bot.py"), args.games, args.show)


if __name__ == "__main__":
    main()
