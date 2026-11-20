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
            if after >= THREE:  # Sekojam arī parastajiem trijniekiem kombinācijām
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
        # Neliels iniciatīvas (tempo) bonuss aktīvajam spēlētājam
        return self.score[k] - self.score[1 - k] + 45

    def threats(self, k: int):
        """
        Atgriež:
          wins   - 5 pēc kārtas (tūlītēja uzvara)
          strong - OPEN4 vai dubultais FOUR (uzvara nākamajā gājienā, ja pretiniekam nav FIVE)
          forks  - dubultais OPEN3 (3x3 dakša) vai FOUR + OPEN3 (4x3 dakša)
          fours  - parastie FOUR
          threes - parastie OPEN3
        """
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
                strong.add(cell)  # 4x3 kombinācija arī ir piespiedu uzvara!

        for cell, cnt in open3_cnt.items():
            if cnt >= 2:
                forks.add(cell)  # 3x3 dakša!

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
        # Augsta prioritāte 4x3 un 3x3 dakšām (gan uzbrukumā, gan bloķējot)
        if att_four >= 2 or (att_four >= 1 and att_o3 >= 1):
            v += 200_000
        elif att_o3 >= 2:
            v += 85_000

        if def_four >= 2 or (def_four >= 1 and def_o3 >= 1):
            v += 160_000
        elif def_o3 >= 2:
            v += 70_000

        return v + 14 - abs(r - 7) - abs(c - 7)