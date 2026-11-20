"""
5-rindu Tic-Tac-Toe (Gomoku) bots ar Swap2 atklātni.
Autors: Kristers Kalniņš

Kā bots domā
------------
1. Figūras līnijās. Laukumā ir 72 līnijas (rindas, kolonnas, diagonāles), kurās
   ietilpst 5 pēc kārtas. Katru līniju glabā kā virkni, piem. "__XX_O____".
   Katrai virknei (ar kešu) aprēķina, kādas figūras tajā ir un kādu figūru
   radītu akmens katrā brīvajā rūtiņā. Gājiens maina tikai 4 līnijas.
2. Piespiedu uzvaras meklēšana: virkne ar četriniekiem (VCF) un ar četriniekiem
   un atvērtiem trijniekiem (VCT). Ar to bots atrod savas uzvaras un izmet
   gājienus, pēc kuriem tāda uzvara būtu pretiniekam.
3. Alfa-beta meklēšana ar iteratīvo padziļināšanu un transpozīciju tabulu.

Noteikumi (../../RULES.md): nav input(), importējot nekas nepalaižas, `board`
netiek mainīts, laiks < 1.0 s, strādā ar Python 3.8+.
"""

import random
import time
from functools import lru_cache

BOT_NAME = "Kristers Kalnins"   # bez garumzīmēm, lai nesalūzt Windows konsolē

N = 15
NN = N * N
EMPTY, X, O = "_", "X", "O"
OTHER = {X: O, O: X}
KIDX = {X: 0, O: 1}

TIME_BUDGET = 0.80       # sekundes vienam gājienam (limits 1.0 s)
ROOT_BEAM = 20           # kandidāti saknē
BEAM = 10                # kandidāti dziļāk kokā
VCF_DEPTH = 14           # četrinieku virknes garums
VCT_DEPTH = 6            # draudu virknes garums
LEAF_VCF_DEPTH = 5       # īsa VCF pārbaude koka lapās
MAX_PLY = 40
WIN = 10 ** 8
INF = 10 ** 9

# Figūru līmeņi no vājākās līdz stiprākajai
NONE, ONE, TWO, OPEN2, THREE, OPEN3, FOUR, OPEN4, FIVE = range(9)
DOWN = (NONE, NONE, ONE, ONE, TWO, OPEN2, THREE, OPEN3, FOUR)   # līmenis pirms 1 akmens
SHAPE = (0, 10, 50, 200, 250, 2500, 3000, 50_000, 5_000_000)     # novērtējumam
MOVE_ATT = (0, 2, 12, 60, 70, 900, 1200, 30_000, 1_000_000)     # gājienu kārtošanai
MOVE_DEF = (0, 1, 8, 45, 50, 700, 800, 20_000, 500_000)


# --- ģeometrija -----------------------------------------------------------
def _build_lines():
    lines = [tuple(r * N + c for c in range(N)) for r in range(N)]
    lines += [tuple(r * N + c for r in range(N)) for c in range(N)]
    for d in range(-(N - 5), N - 4):                 # c - r = d
        lines.append(tuple(r * N + r + d for r in range(N) if 0 <= r + d < N))
    for s in range(4, 2 * N - 5):                    # r + c = s
        lines.append(tuple(r * N + s - r for r in range(N) if 0 <= s - r < N))
    return tuple(lines)


LINES = _build_lines()
CELL_LINES = [[] for _ in range(NN)]                 # rūtiņa -> [(līnija, pozīcija)]
for _lid, _cells in enumerate(LINES):
    for _pos, _i in enumerate(_cells):
        CELL_LINES[_i].append((_lid, _pos))
NEAR = [[rr * N + cc                                 # 5x5 apkārtne kandidātiem
         for rr in range(max(0, i // N - 2), min(N, i // N + 3))
         for cc in range(max(0, i % N - 2), min(N, i % N + 3)) if rr * N + cc != i]
        for i in range(NN)]
CENTER_BONUS = [14 - abs(i // N - 7) - abs(i % N - 7) for i in range(NN)]
_rng = random.Random(20251120)                       # fiksēts => deterministisks
ZOBRIST = [[_rng.getrandbits(64) for _ in range(NN)] for _ in range(2)]
SIDE_KEY = (_rng.getrandbits(64), _rng.getrandbits(64))


# --- figūras vienā līnijā ("x" savs, "_" tukšs, "o" pretinieks vai mala) ---
def _trim(seg):
    a = seg.find("x")
    return "" if a < 0 else seg[max(0, a - 5):seg.rfind("x") + 6]


@lru_cache(maxsize=None)
def _level(seg):
    """Stiprākā figūra segmentā, kurā ir tikai 'x' un '_' (gali bloķēti)."""
    if len(seg) < 5 or "x" not in seg:
        return NONE
    if "xxxxx" in seg:
        return FIVE
    wins = sum(1 for i, ch in enumerate(seg)
               if ch == "_" and "xxxxx" in seg[max(0, i - 4):i] + "x" + seg[i + 1:i + 5])
    if wins:
        return OPEN4 if wins >= 2 else FOUR
    best = NONE
    for i, ch in enumerate(seg):
        if ch == "_" and "x" in seg[max(0, i - 4):i + 5]:
            best = max(best, DOWN[_level(_trim(seg[:i] + "x" + seg[i + 1:]))])
            if best == OPEN3:
                break
    return best


def _analyze(t):
    """(vērtība, līmeņi katrai rūtiņai, karstās rūtiņas ar līmeni >= OPEN3)."""
    score = sum(SHAPE[_level(_trim(seg))] for seg in t.split("o") if len(seg) >= 5)
    levels = [NONE] * len(t)
    hot = []
    for i, ch in enumerate(t):
        if ch != "_":
            continue
        lo = max(0, i - 5)
        w = t[lo:i + 6]
        ii = i - lo
        j = w.rfind("o", 0, ii)
        k = w.find("o", ii + 1)
        loc = w[j + 1:k if k >= 0 else len(w)]
        ii -= j + 1
        if len(loc) < 5 or "x" not in loc[max(0, ii - 4):ii + 5]:
            continue
        after = _level(loc[:ii] + "x" + loc[ii + 1:])
        if after > _level(loc):
            levels[i] = after
            if after >= OPEN3:
                hot.append((i, after))
    return score, tuple(levels), tuple(hot)


@lru_cache(maxsize=100_000)
def _line_info(s):
    """(analīze X, analīze O) līnijas virknei ar simboliem _ X O."""
    return (_analyze(s.replace("X", "x").replace("O", "o")),
            _analyze(s.replace("X", "o").replace("O", "x")))


# --- spēles stāvoklis (vienmēr laukuma KOPIJA) ----------------------------
class _Game:
    def __init__(self, board):
        self.cells = [ch if ch in (X, O) else EMPTY for row in board for ch in row[:N]]
        self.lines = ["".join(self.cells[i] for i in cl) for cl in LINES]
        self.info = [_line_info(s) for s in self.lines]
        self.hotlines = {lid for lid, inf in enumerate(self.info) if inf[0][2] or inf[1][2]}
        self.score = [sum(inf[0][0] for inf in self.info), sum(inf[1][0] for inf in self.info)]
        self.near = [0] * NN
        self.hash = 0
        self.stones = 0
        for i, ch in enumerate(self.cells):
            if ch != EMPTY:
                self.stones += 1
                self.hash ^= ZOBRIST[KIDX[ch]][i]
                for j in NEAR[i]:
                    self.near[j] += 1

    def _set(self, i, ch, p):
        self.cells[i] = ch
        self.hash ^= ZOBRIST[KIDX[p]][i]
        for lid, pos in CELL_LINES[i]:
            s = self.lines[lid]
            s = self.lines[lid] = s[:pos] + ch + s[pos + 1:]
            old, new = self.info[lid], _line_info(s)
            self.info[lid] = new
            self.score[0] += new[0][0] - old[0][0]
            self.score[1] += new[1][0] - old[1][0]
            if new[0][2] or new[1][2]:
                self.hotlines.add(lid)
            else:
                self.hotlines.discard(lid)

    def place(self, i, p):
        self._set(i, p, p)
        self.stones += 1
        for j in NEAR[i]:
            self.near[j] += 1

    def undo(self, i):
        self._set(i, EMPTY, self.cells[i])
        self.stones -= 1
        for j in NEAR[i]:
            self.near[j] -= 1

    def threats(self, k):
        """Spēlētāja k rūtiņas: (piecinieks, atvērts/dubults 4, četrinieks, atvērts 3)."""
        wins, strong, fours, threes = set(), set(), set(), set()
        for lid in self.hotlines:
            cl = LINES[lid]
            for pos, lv in self.info[lid][k][2]:
                i = cl[pos]
                if lv == FIVE:
                    wins.add(i)
                elif lv == OPEN4:
                    strong.add(i)
                elif lv == FOUR:
                    if i in fours:
                        strong.add(i)            # divi četrinieki ar vienu akmeni
                    fours.add(i)
                else:
                    threes.add(i)
        return wins, strong, fours, threes

    def evaluate(self, k):
        return self.score[k] - self.score[1 - k]

    def move_value(self, i, k):
        v = a_hot = d_hot = 0
        for lid, pos in CELL_LINES[i]:
            inf = self.info[lid]
            a, d = inf[k][1][pos], inf[1 - k][1][pos]
            v += MOVE_ATT[a] + MOVE_DEF[d]
            a_hot += a >= OPEN3
            d_hot += d >= OPEN3
        return (v + CENTER_BONUS[i] + (25_000 if a_hot >= 2 else 0)
                + (15_000 if d_hot >= 2 else 0))          # dubulti draudi

    def order(self, cells, k):
        return sorted((i for i in cells if self.cells[i] == EMPTY),
                      key=lambda i: (self.move_value(i, k), i), reverse=True)

    def candidates(self, k, limit):
        return self.order((i for i in range(NN) if self.near[i]), k)[:limit]


# --- meklēšana --------------------------------------------------------------
class _Timeout(Exception):
    pass


_TT = {}          # transpozīciju tabula: hash -> (dziļums, vērtība, karogs, gājiens)
_FAIL = {}        # (hash, threes) -> dziļums, kurā piespiedu uzvara netika atrasta
_INFO = {}        # pēdējā gājiena paskaidrojums (to rāda gui.py)


class _Searcher:
    def __init__(self, game, deadline):
        self.g = game
        self.deadline = deadline
        self.nodes = 0
        self.out_of_time = False

    def forced_win(self, p, depth, threes):
        """
        Pirmais gājiens piespiedu uzvarai spēlētājam p vai None.
        threes=False: tikai četrinieki (VCF), True: arī atvērti trijnieki (VCT).
        """
        self.nodes += 1
        if not self.nodes & 31 and time.perf_counter() > self.deadline:
            self.out_of_time = True
        if self.out_of_time:
            return None
        g = self.g
        k = KIDX[p]
        key = (g.hash ^ SIDE_KEY[k], threes)
        if _FAIL.get(key, -1) >= depth:
            return None
        wins_p, strong_p, fours_p, threes_p = g.threats(k)
        if wins_p:
            return min(wins_p)
        wins_o, strong_o, fours_o, _ = g.threats(1 - k)
        if wins_o:
            if len(wins_o) > 1:
                return None
            c = next(iter(wins_o))               # jābloķē, un bloks pats ir draudi
            if c in strong_p:
                return c
            if c not in fours_p and not (threes and not strong_o and c in threes_p):
                return None
            moves = [c]
        elif strong_p:
            return min(strong_p)
        elif threes and not strong_o:
            moves = g.order(fours_p | threes_p, k)
        else:
            moves = g.order(fours_p, k)          # pret atvērtu 3 der tikai 4
        if depth <= 0:
            return None
        o = OTHER[p]
        for m in moves:
            g.place(m, p)
            five = g.threats(k)[0]
            if len(five) >= 2:
                g.undo(m)
                return m
            if five:
                defenses = five
            else:                                # atvērts trijnieks: visas aizsardzības
                strong_a = g.threats(k)[1]
                if not strong_a:
                    g.undo(m)
                    continue
                _, strong_d, fours_d, _ = g.threats(1 - k)
                defenses = strong_a | strong_d | fours_d | {     # + 4-nieki m līnijās
                    LINES[lid][q] for lid, _ in CELL_LINES[m]
                    for q, lv in g.info[lid][k][2] if lv >= FOUR}
            lost = True
            for d in defenses:
                g.place(d, o)
                r = self.forced_win(p, depth - 1, threes)
                g.undo(d)
                if r is None:
                    lost = False
                    break
            g.undo(m)
            if self.out_of_time:
                return None
            if lost:
                return m
        _FAIL[key] = depth
        return None

    def search(self, p, depth, alpha, beta, ply):
        self.nodes += 1
        if not self.nodes & 31 and time.perf_counter() > self.deadline:
            raise _Timeout
        g = self.g
        k = KIDX[p]
        wins_p, strong_p, fours_p, _ = g.threats(k)
        if wins_p:
            return WIN - ply
        wins_o, strong_o, fours_o, _ = g.threats(1 - k)
        if len(wins_o) >= 2:
            return -(WIN - ply - 1)
        if strong_p and not wins_o:
            return WIN - ply - 2
        if ply >= MAX_PLY:
            return g.evaluate(k)

        key = g.hash ^ SIDE_KEY[k]
        e_depth, e_val, e_flag, tt_move = _TT.get(key, (-1, 0, 0, None))
        if e_depth >= depth and (e_flag == 0 or (e_flag == 1 and e_val >= beta)
                                 or (e_flag == 2 and e_val <= alpha)):
            return e_val

        child = depth - 1
        if wins_o:
            moves = list(wins_o)                 # jābloķē, dziļumu nesamazinām
            child = depth
        elif depth <= 0:
            if fours_p:                          # lapā: vai ir īsa četrinieku uzvara?
                if self.forced_win(p, LEAF_VCF_DEPTH, False) is not None:
                    return WIN - 1000
                if self.out_of_time:
                    raise _Timeout
            return g.evaluate(k)
        elif strong_o:                           # pretiniekam atvērts 3
            moves = g.order(strong_o | fours_o | fours_p, k)
        else:
            moves = g.candidates(k, BEAM)
        if not moves:
            return 0
        if tt_move in moves:
            moves.remove(tt_move)
            moves.insert(0, tt_move)

        alpha0 = alpha
        best, best_m = -INF, moves[0]
        for m in moves:
            g.place(m, p)
            v = -self.search(OTHER[p], child, -beta, -alpha, ply + 1)
            g.undo(m)
            if v > best:
                best, best_m = v, m
                alpha = max(alpha, v)
                if alpha >= beta:
                    break
        flag = 2 if best <= alpha0 else (1 if best >= beta else 0)   # 0 precīzs, 1 >=, 2 <=
        _TT[key] = (depth, best, flag, best_m)
        return best


def _forced(g, p, threes, deadline):
    """Piespiedu uzvaras pirmais gājiens spēlētājam p (VCT vai VCF) vai None."""
    return _Searcher(g, deadline).forced_win(p, VCT_DEPTH if threes else VCF_DEPTH, threes)


# --- gājiena izvēle -----------------------------------------------------------
def _think(board, player, budget=TIME_BUDGET):
    """Atgriež (rūtiņas indekss, novērtējums); paskaidrojums nonāk _INFO."""
    start = time.perf_counter()
    _INFO.clear()
    if len(_TT) > 300_000:                       # ponytail: vienkārši iztīra, nevis LRU
        _TT.clear()
    if len(_FAIL) > 300_000:
        _FAIL.clear()

    def done(move, value, why):
        _INFO.update(why=why, value=value, time=time.perf_counter() - start)
        return move, value

    g = _Game(board)
    if g.stones == 0:
        return done(7 * N + 7, 0, "Tukšs laukums: sāk centrā")
    k = KIDX[player]
    o = OTHER[player]
    wins_p, strong_p, fours_p, _ = g.threats(k)
    if wins_p:
        return done(min(wins_p), WIN, "Uzvara: 5 pēc kārtas")
    wins_o, strong_o, fours_o, _ = g.threats(1 - k)
    if wins_o:
        why = "Bloķē pretinieka četrinieku" if len(wins_o) == 1 else \
              "Pretiniekam ir divi četrinieki: zaudējums"
        return done(min(wins_o), g.evaluate(k) if len(wins_o) == 1 else -WIN, why)
    if strong_p:
        return done(g.order(strong_p, k)[0], WIN,
                    "Atvērts vai dubults četrinieks: uzvara nākamajā gājienā")

    # 1) Vai mums ir piespiedu uzvara?
    m = _forced(g, player, False, start + budget * 0.10)
    if m is None and not strong_o:
        m = _forced(g, player, True, start + budget * 0.20)
    if m is not None:
        return done(m, WIN, "Piespiedu uzvara: draudu virkne (četrinieki un trijnieki)")

    # 2) Kandidāti, izņemot tos, pēc kuriem pretiniekam ir piespiedu uzvara
    moves = (g.order(strong_o | fours_o | fours_p, k) if strong_o
             else g.candidates(k, ROOT_BEAM))
    if not moves:
        return done(next((i for i in range(NN) if g.cells[i] == EMPTY), 0), 0, "Nav kandidātu")
    for threes, frac in ((False, 0.30), (True, 0.45)):
        s = _Searcher(g, start + budget * frac)
        safe = []
        for n, mv in enumerate(moves):
            g.place(mv, player)
            lost = s.forced_win(o, VCT_DEPTH if threes else VCF_DEPTH, threes) is not None
            g.undo(mv)
            if s.out_of_time:
                safe += moves[n:]                # laiks beidzies: pārējos nepārbaudām
                break
            if not lost:
                safe.append(mv)
        moves = safe or moves                    # ponytail: ja zaudē viss, spēlē labāko
    prefix = "Aizsardzība pret atvērtu trijnieku. " if strong_o else ""
    if len(moves) == 1:
        return done(moves[0], g.evaluate(k), prefix + "Tikai viens drošs gājiens")

    # 3) Alfa-beta ar iteratīvo padziļināšanu
    s = _Searcher(g, start + budget)
    best_m, best_v, depth = moves[0], g.evaluate(k), 0
    try:
        while depth < 30 and abs(best_v) < WIN - 1000:
            depth += 1
            alpha, it_m = -INF, None
            for mv in moves:
                g.place(mv, player)
                v = -s.search(o, depth - 1, -INF, -alpha, 1)
                g.undo(mv)
                if v > alpha:
                    alpha, it_m = v, mv
                    best_m, best_v = mv, v       # 1. gājiens ir iepriekšējais labākais
            moves.remove(it_m)
            moves.insert(0, it_m)
    except _Timeout:
        depth -= 1
    return done(best_m, best_v, prefix + "Alfa-beta meklēšana, dziļums %d (%d mezgli)"
                % (depth, s.nodes))


# --- obligātās funkcijas ------------------------------------------------------
def get_move(board, player):
    """Atgriež (rinda, kolonna) brīvai rūtiņai, kurā bots liek savu simbolu."""
    try:
        r, c = divmod(_think(board, player)[0], N)
        if board[r][c] == EMPTY:
            return (r, c)
    except Exception:
        pass
    for r in range(N):                           # drošības tīkls: vienmēr derīgs gājiens
        for c in range(N):
            if board[r][c] == EMPTY:
                return (r, c)
    return (7, 7)


def _o_is_better(board):
    try:
        return _think(board, O, 0.7)[1] >= 0     # pēc atklātnes gājiens ir O
    except Exception:
        return True


def swap2_propose(board):
    """
    Swap2 1. solis. O centrā, X abās pusēs pa diagonāli. Izskatās, ka O ir
    nobloķējis X, tāpēc pretinieki parasti ņem O, bet X ar diviem akmeņiem
    un brīvām līnijām apkārt ir stiprāks (testos pret Peteri 4 no 4).
    """
    return [(6, 6, X), (7, 7, O), (8, 8, X)]


def swap2_respond(board):
    """Swap2 2. solis: ņemam krāsu, kura pēc meklēšanas ir izdevīgāka."""
    return {"action": "TAKE_O" if _o_is_better(board) else "TAKE_X"}


def swap2_final_choice(board):
    """Swap2 3. solis (pēc PLACE_TWO): izvēlamies izdevīgāko krāsu."""
    return O if _o_is_better(board) else X


if __name__ == "__main__":
    # Pašpārbaude: bots redz uzvaru, bloķē četrinieku un nemaina `board`.
    b = [[EMPTY] * N for _ in range(N)]
    for c in range(4):
        b[7][c + 3] = X
    snapshot = [row[:] for row in b]
    assert get_move(b, X) in ((7, 2), (7, 7)), "neredz uzvaru"
    assert get_move(b, O) in ((7, 2), (7, 7)), "nebloķē četrinieku"
    assert b == snapshot, "board tika mainīts"
    t0 = time.perf_counter()
    demo = [[EMPTY] * N for _ in range(N)]
    for r, c, sym in swap2_propose(demo):
        demo[r][c] = sym
    print(BOT_NAME, "->", get_move(demo, O), "(%.2f s)" % (time.perf_counter() - t0), "OK")
