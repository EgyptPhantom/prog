import random
import time
from functools import lru_cache

BOT_NAME = "GrandmasterAI"
N = 15
EMPTY, X, O = "_", "X", "O"
OTHER = {X: O, O: X}
PIDX = {X: 0, O: 1}

TIME_LIMIT = 0.85
ROOT_BEAM = 16
BEAM = 13
MAX_PLY = 32

WIN = 10 ** 9
INF = 2 * WIN

# Transpozīciju tabulas karogi
TT_EXACT, TT_ALPHA, TT_BETA = 0, 1, 2

# Figūru līmeņi
NONE, ONE, TWO, OPEN2, THREE, OPEN3, FOUR, OPEN4, FIVE = range(9)
SHAPE_SCORE = (0, 12, 75, 480, 900, 6_500, 8_000, 140_000, 10_000_000)
STEP_DOWN = {OPEN4: OPEN3, FOUR: THREE, OPEN3: OPEN2, THREE: TWO, OPEN2: ONE}

# Zobrist hash tabula
_rng = random.Random(2026)
ZOBRIST = tuple(
    tuple((_rng.getrandbits(64), _rng.getrandbits(64)) for _ in range(N))
    for _ in range(N)
)
ZOBRIST_TURN = _rng.getrandbits(64)


def _build_lines():
    lines = []
    for r in range(N):
        lines.append(tuple((r, c) for c in range(N)))
    for c in range(N):
        lines.append(tuple((r, c) for r in range(N)))
    for d in range(-(N - 5), N - 4):
        lines.append(tuple((r, r + d) for r in range(N) if 0 <= r + d < N))
    for s in range(4, 2 * N - 5):
        lines.append(tuple((r, s - r) for r in range(N) if 0 <= s - r < N))
    return tuple(lines)


LINES = _build_lines()
CELL_LINES = [[[] for _ in range(N)] for _ in range(N)]
for _lid, _cells in enumerate(LINES):
    for _pos, (_r, _c) in enumerate(_cells):
        CELL_LINES[_r][_c].append((_lid, _pos))
CELL_LINES = tuple(tuple(tuple(cl) for cl in row) for row in CELL_LINES)


def _makes_five(t: str, i: int) -> bool:
    return "xxxxx" in t[max(0, i - 4):i] + "x" + t[i + 1:i + 5]


def _trim(seg: str) -> str:
    a = seg.find("x")
    if a < 0:
        return ""
    b = seg.rfind("x")
    return seg[max(0, a - 5):b + 6]


@lru_cache(maxsize=None)
def _seg_level(seg: str) -> int:
    if len(seg) < 5 or "x" not in seg:
        return NONE
    if "xxxxx" in seg:
        return FIVE

    wins = 0
    for i, ch in enumerate(seg):
        if ch == "_" and _makes_five(seg, i):
            wins += 1
    if wins >= 2:
        return OPEN4
    if wins == 1:
        return FOUR

    best = NONE
    for i, ch in enumerate(seg):
        if ch == "_" and "x" in seg[max(0, i - 4):i + 5]:
            nxt = _seg_level(_trim(seg[:i] + "x" + seg[i + 1:]))
            down = STEP_DOWN.get(nxt, NONE)
            if down > best:
                best = down
                if best == OPEN3:
                    break
    return best


def _analyze(s: str, p: str):
    t = s.replace(p, "x").replace(OTHER[p], "o")
    n = len(t)

    score = 0
    for seg in t.split("o"):
        if len(seg) >= 5 and "x" in seg:
            score += SHAPE_SCORE[_seg_level(_trim(seg))]

    levels = [NONE] * n
    hot = []
    for i, ch in enumerate(t):
        if ch != "_":
            continue
        lo = max(0, i - 5)
        win = t[lo:min(n, i + 6)]
        ii = i - lo
        j = win.rfind("o", 0, ii)
        k = win.find("o", ii + 1)
        local = win[j + 1:k if k >= 0 else len(win)]
        ii -= j + 1
        if len(local) < 5 or "x" not in local[max(0, ii - 4):ii + 5]:
            continue
        after = _seg_level(local[:ii] + "x" + local[ii + 1:])
        if after > NONE and after > _seg_level(local):
            levels[i] = after
            if after >= THREE:
                hot.append((i, after))
    return score, tuple(levels), tuple(hot)


@lru_cache(maxsize=250_000)
def _line_info(s: str):
    return _analyze(s, X), _analyze(s, O)


class _BoardState:
    def __init__(self, board):
        self.cells = [list(row) for row in board]
        self.near = [[0] * N for _ in range(N)]
        self.stones = 0
        self.lines = []
        self.info = []
        self.score = [0, 0]
        self.hash = 0

        for cells in LINES:
            s = "".join(self.cells[r][c] for r, c in cells)
            inf = _line_info(s)
            self.lines.append(s)
            self.info.append(inf)
            self.score[0] += inf[0][0]
            self.score[1] += inf[1][0]

        for r in range(N):
            for c in range(N):
                ch = self.cells[r][c]
                if ch != EMPTY:
                    self._mark_near(r, c, 1)
                    self.stones += 1
                    self.hash ^= ZOBRIST[r][c][PIDX[ch]]

    def _mark_near(self, r: int, c: int, delta: int):
        for rr in range(max(0, r - 2), min(N, r + 3)):
            row = self.near[rr]
            for cc in range(max(0, c - 2), min(N, c + 3)):
                row[cc] += delta

    def _update_lines(self, r: int, c: int, ch: str):
        self.cells[r][c] = ch
        score = self.score
        for lid, pos in CELL_LINES[r][c]:
            s = self.lines[lid]
            ns = s[:pos] + ch + s[pos + 1:]
            old = self.info[lid]
            new = _line_info(ns)
            score[0] += new[0][0] - old[0][0]
            score[1] += new[1][0] - old[1][0]
            self.lines[lid] = ns
            self.info[lid] = new

    def place(self, r: int, c: int, p: str):
        self._update_lines(r, c, p)
        self._mark_near(r, c, 1)
        self.stones += 1
        self.hash ^= ZOBRIST[r][c][PIDX[p]]

    def undo(self, r: int, c: int, p: str):
        self._update_lines(r, c, EMPTY)
        self._mark_near(r, c, -1)
        self.stones -= 1
        self.hash ^= ZOBRIST[r][c][PIDX[p]]

    def evaluate(self, k: int) -> int:
        return self.score[k] - self.score[1 - k] + 45

    def threats(self, k: int):
        wins, strong, forks, fours, threes = set(), set(), set(), set(), set()
        four_cnt = {}
        open3_cnt = {}

        for lid, inf in enumerate(self.info):
            hot = inf[k][2]
            if not hot:
                continue
            cells = LINES[lid]
            for pos, lv in hot:
                cell = cells[pos]
                if lv == FIVE:
                    wins.add(cell)
                elif lv == OPEN4:
                    strong.add(cell)
                elif lv == FOUR:
                    fours.add(cell)
                    four_cnt[cell] = four_cnt.get(cell, 0) + 1
                elif lv == OPEN3:
                    threes.add(cell)
                    open3_cnt[cell] = open3_cnt.get(cell, 0) + 1

        for cell, cnt in four_cnt.items():
            if cnt >= 2:
                strong.add(cell)
            elif cnt == 1 and open3_cnt.get(cell, 0) >= 1:
                strong.add(cell)

        for cell, cnt in open3_cnt.items():
            if cnt >= 2:
                forks.add(cell)

        return wins, strong, forks, fours, threes

    def move_value(self, r: int, c: int, k: int) -> int:
        ko = 1 - k
        att = dfn = 0
        att_four = att_o3 = 0
        def_four = def_o3 = 0

        for lid, pos in CELL_LINES[r][c]:
            inf = self.info[lid]
            a = inf[k][1][pos]
            d = inf[ko][1][pos]
            att += SHAPE_SCORE[a]
            dfn += SHAPE_SCORE[d]
            if a == FOUR or a == OPEN4:
                att_four += 1
            elif a == OPEN3:
                att_o3 += 1
            if d == FOUR or d == OPEN4:
                def_four += 1
            elif d == OPEN3:
                def_o3 += 1

        v = att + (dfn * 9) // 10
        if att_four >= 2 or (att_four >= 1 and att_o3 >= 1):
            v += 200_000
        elif att_o3 >= 2:
            v += 85_000

        if def_four >= 2 or (def_four >= 1 and def_o3 >= 1):
            v += 160_000
        elif def_o3 >= 2:
            v += 70_000

        return v + 14 - abs(r - 7) - abs(c - 7)

    def candidates(self, k: int, limit: int) -> list[tuple[int, int]]:
        scored = []
        for r in range(N):
            row = self.cells[r]
            nr = self.near[r]
            for c in range(N):
                if row[c] == EMPTY and nr[c]:
                    scored.append((self.move_value(r, c, k), r, c))
        scored.sort(reverse=True)
        return [(r, c) for _, r, c in scored[:limit]]

    def order(self, cells, k: int) -> list[tuple[int, int]]:
        scored = [
            (self.move_value(r, c, k), r, c)
            for r, c in cells
            if self.cells[r][c] == EMPTY
        ]
        scored.sort(reverse=True)
        return [(r, c) for _, r, c in scored]


class _Timeout(Exception):
    pass


class _Engine:
    def __init__(self, state: _BoardState, deadline: float):
        self.g = state
        self.deadline = deadline
        self.nodes = 0
        self.tt = {}  # (hash, turn_bit) -> (depth, flag, score, best_move)
        self.partial_move = None

    def _tactical_filter(self, p: str):
        g = self.g
        k = PIDX[p]
        wins_p, strong_p, forks_p, fours_p, _ = g.threats(k)
        if wins_p:
            return WIN, [next(iter(wins_p))]

        wins_o, strong_o, forks_o, fours_o, threes_o = g.threats(1 - k)
        if len(wins_o) >= 2:
            return -(WIN - 1), [next(iter(wins_o))]
        if wins_o:
            return None, [next(iter(wins_o))]

        if strong_p:
            return WIN - 2, g.order(strong_p, k)

        if strong_o:
            pool = strong_o | fours_p | fours_o
            return None, g.order(pool, k)

        if forks_p and not fours_o:
            return None, g.order(forks_p | fours_p, k)

        if forks_o or threes_o:
            pool = forks_o | threes_o | fours_o | fours_p
            return None, g.order(pool, k)

        return None, None

    def negamax(self, p: str, depth: int, alpha: int, beta: int, ply: int) -> int:
        self.nodes += 1
        if (self.nodes & 31) == 0 and time.perf_counter() > self.deadline:
            raise _Timeout

        g = self.g
        k = PIDX[p]
        tt_key = (g.hash, k)
        orig_alpha = alpha

        entry = self.tt.get(tt_key)
        tt_move = None
        if entry is not None:
            e_depth, e_flag, e_score, tt_move = entry
            if e_depth >= depth:
                if e_flag == TT_EXACT:
                    return e_score
                elif e_flag == TT_ALPHA and e_score <= alpha:
                    return e_score
                elif e_flag == TT_BETA and e_score >= beta:
                    return e_score

        result, moves = self._tactical_filter(p)
        if result is not None:
            return result - ply if result > 0 else result + ply

        forced = moves is not None and len(moves) == 1
        if not forced:
            if depth <= 0 or ply >= MAX_PLY:
                return g.evaluate(k)
            if moves is None:
                moves = g.candidates(k, BEAM)

        if not moves:
            return 0

        if tt_move is not None and tt_move in moves:
            moves.remove(tt_move)
            moves.insert(0, tt_move)

        next_depth = depth if forced else depth - 1
        opp = OTHER[p]
        best_val = -INF
        best_mv = moves[0]

        for idx, (r, c) in enumerate(moves):
            g.place(r, c, p)
            if idx == 0:
                val = -self.negamax(opp, next_depth, -beta, -alpha, ply + 1)
            else:
                # LMR (Late Move Reductions): tālākos gājienus meklējam par 1 līmeni seklāk
                reduction = 1 if (idx >= 4 and next_depth >= 2 and not forced) else 0
                val = -self.negamax(opp, next_depth - reduction, -alpha - 1, -alpha, ply + 1)
                if reduction > 0 and val > alpha:
                    val = -self.negamax(opp, next_depth, -alpha - 1, -alpha, ply + 1)
                if alpha < val < beta:
                    val = -self.negamax(opp, next_depth, -beta, -alpha, ply + 1)
            g.undo(r, c, p)

            if val > best_val:
                best_val = val
                best_mv = (r, c)
                if val > alpha:
                    alpha = val
                    if alpha >= beta:
                        break

        if len(self.tt) < 300_000:
            if best_val <= orig_alpha:
                flag = TT_ALPHA
            elif best_val >= beta:
                flag = TT_BETA
            else:
                flag = TT_EXACT
            self.tt[tt_key] = (depth, flag, best_val, best_mv)

        return best_val

    def search_root(self, moves: list[tuple[int, int]], p: str, depth: int):
        alpha = -INF
        best_val = -INF
        best_mv = moves[0]
        self.partial_move = None
        opp = OTHER[p]

        for r, c in moves:
            self.g.place(r, c, p)
            val = -self.negamax(opp, depth - 1, -INF, -alpha, 1)
            self.g.undo(r, c, p)

            if val > best_val:
                best_val = val
                best_mv = (r, c)
                self.partial_move = best_mv
            if val > alpha:
                alpha = val

        return best_val, best_mv


def _fallback_empty(board) -> tuple[int, int]:
    for r in range(N):
        for c in range(N):
            if board[r][c] == EMPTY:
                return (r, c)
    return (7, 7)


def _solve(board, player: str, budget: float, max_depth: int = 22):
    deadline = time.perf_counter() + budget
    g = _BoardState(board)
    if g.stones == 0:
        return (7, 7), 0

    k = PIDX[player]
    engine = _Engine(g, deadline)
    result, moves = engine._tactical_filter(player)
    if result is not None or (moves is not None and len(moves) == 1):
        return moves[0], (result if result is not None else g.evaluate(k))

    if moves is None:
        moves = g.candidates(k, ROOT_BEAM)
    if not moves:
        return _fallback_empty(board), 0

    best_mv = moves[0]
    best_val = g.evaluate(k)

    for depth in range(1, max_depth + 1):
        try:
            val, mv = engine.search_root(moves, player, depth)
        except _Timeout:
            if engine.partial_move is not None:
                best_mv = engine.partial_move
            break

        best_mv, best_val = mv, val
        moves.remove(mv)
        moves.insert(0, mv)
        if abs(val) >= WIN - 100:
            break

    return best_mv, best_val


def get_move(board: list[list[str]], player: str) -> tuple[int, int]:
    try:
        move, _ = _solve(board, player, TIME_LIMIT)
        r, c = move
        if 0 <= r < N and 0 <= c < N and board[r][c] == EMPTY:
            return (r, c)
    except Exception:
        pass
    return _fallback_empty(board)


SWAP2_OPENINGS = (
    # 1. Klasiskā neitrālā diagonāle (Soosyrv-8 sākums)
    [(7, 7, X), (6, 8, O), (8, 9, X)],
    # 2. Asimetriskais trijstūris (Taraguchi tipa sākums)
    [(7, 7, X), (7, 8, O), (9, 6, X)],
    # 3. Plašā centra kontrole
    [(7, 7, X), (6, 6, O), (8, 9, X)],
    # 4. Zirga gājiena nobīde
    [(7, 7, X), (8, 6, O), (6, 9, X)],
    # 5. Pretdiagonāles balanss
    [(7, 7, X), (6, 7, O), (8, 9, X)],
)


def swap2_propose(board: list[list[str]]) -> list[tuple[int, int, str]]:
    opening = random.choice(SWAP2_OPENINGS)
    flip_r = random.choice((False, True))
    flip_c = random.choice((False, True))
    swap_axes = random.choice((False, True))

    result = []
    for r, c, sym in opening:
        rr = (N - 1 - r) if flip_r else r
        cc = (N - 1 - c) if flip_c else c
        if swap_axes:
            rr, cc = cc, rr
        result.append((rr, cc, sym))
    return result


def swap2_respond(board: list[list[str]]) -> dict:
    # Novērtējam pozīciju no 'O' skatpunkta (jo 'O' veic 4. gājienu)
    _, val_o = _solve(board, O, TIME_LIMIT * 0.45)
    if val_o > 110:
        return {"action": "TAKE_O"}
    if val_o < -110:
        return {"action": "TAKE_X"}

    # Ja pozīcija ir tuvu neitrālai, meklējam labāko PLACE_TWO balansu ar 2-gājienu pārbaudi
    g = _BoardState(board)
    cands = g.candidates(PIDX[O], 6)
    best_pair = None
    best_margin = abs(val_o)

    for i in range(min(len(cands), 4)):
        r1, c1 = cands[i]
        g.place(r1, c1, X)
        for j in range(min(len(cands), 4)):
            if i == j:
                continue
            r2, c2 = cands[j]
            g.place(r2, c2, O)
            _, pair_val = _solve(g.cells, O, 0.03, max_depth=3)
            margin = abs(pair_val)
            if margin < best_margin:
                best_margin = margin
                best_pair = [(r1, c1, X), (r2, c2, O)]
            g.undo(r2, c2, O)
        g.undo(r1, c1, X)

    if best_pair is not None:
        return {"action": "PLACE_TWO", "moves": best_pair}

    return {"action": "TAKE_O"} if val_o >= 0 else {"action": "TAKE_X"}


def swap2_final_choice(board: list[list[str]]) -> str:
    _, val_o = _solve(board, O, TIME_LIMIT * 0.75)
    return O if val_o >= 0 else X


if __name__ == "__main__":
    test_board = [[EMPTY] * N for _ in range(N)]
    for r, c, sym in swap2_propose(test_board):
        test_board[r][c] = sym
    t0 = time.perf_counter()
    print(BOT_NAME, "->", get_move(test_board, O), f"({time.perf_counter() - t0:.2f} s)")