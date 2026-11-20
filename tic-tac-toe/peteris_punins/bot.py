"""
5-rindu Tic-Tac-Toe (Gomoku) bots ar Swap2 atklātni.

Darbības princips
-----------------
1. Laukums tiek sadalīts 88 "līnijās" (rindas, kolonnas un abu virzienu
   diagonāles, kuru garums ir vismaz 5). Katru līniju glabā kā virkni,
   piem. "__XX_O_________".
2. Katrai līnijai (ar kešu) aprēķina:
     * novērtējumu katram spēlētājam (cik bīstamas figūras tajā ir:
       atvērts četrinieks, trijnieks utt.);
     * katrai brīvajai rūtiņai — kādu figūru spēlētājs izveidotu,
       ieliekot tur savu simbolu (piecinieku, četrinieku, trijnieku ...).
3. Gājienu izvēlas ar alfa-beta (negamax) meklēšanu ar iteratīvo
   padziļināšanu, līdz beidzas laika budžets (< 1 s).
   Taktiskie noteikumi katrā mezglā:
     * ja vari uzvarēt ar vienu gājienu — uzvari;
     * ja pretinieks var uzvarēt ar vienu gājienu — bloķē;
     * ja vari izveidot atvērtu četrinieku (vai dubulto četrinieku) —
       tā ir garantēta uzvara;
     * ja pretiniekam ir atvērts trijnieks — apskata tikai aizsardzības
       gājienus un savus četriniekus.

Modulis neizmanto input() un importējot neko nepalaiž.
Ieejas `board` netiek mainīts — vienmēr tiek veidota kopija.
"""

import time
from functools import lru_cache

BOT_NAME = "Peteris Punins"   # bez garumzīmēm, lai nesalūzt Windows konsolē

N = 15
EMPTY, X, O = "_", "X", "O"
OTHER = {X: O, O: X}
PIDX = {X: 0, O: 1}          # spēlētāja indekss līniju informācijā

TIME_LIMIT = 0.70            # sekundes vienam gājienam (noteikumos max 1.0, atstājam rezervi)
ROOT_BEAM = 14               # cik kandidātu apskatīt saknē
BEAM = 9                     # cik kandidātu apskatīt dziļāk kokā
MAX_PLY = 30

WIN = 10 ** 9
INF = 2 * WIN

# ---------------------------------------------------------------------------
# Figūru līmeņi (no vājākās līdz stiprākajai)
# ---------------------------------------------------------------------------
NONE, ONE, TWO, OPEN2, THREE, OPEN3, FOUR, OPEN4, FIVE = range(9)

# Figūras vērtība novērtējuma funkcijā (indekss = līmenis)
SHAPE_SCORE = (0, 10, 60, 400, 700, 5_000, 6_000, 100_000, 10_000_000)

# Ja, pieliekot vienu akmeni, var iegūt līmeni L, tad pašreizējais ir STEP_DOWN[L]
STEP_DOWN = {OPEN4: OPEN3, FOUR: THREE, OPEN3: OPEN2, THREE: TWO, OPEN2: ONE}


# ---------------------------------------------------------------------------
# Laukuma ģeometrija: visas līnijas, kurās var ietilpt 5 pēc kārtas
# ---------------------------------------------------------------------------
def _build_lines():
    lines = []
    for r in range(N):                                   # rindas
        lines.append(tuple((r, c) for c in range(N)))
    for c in range(N):                                   # kolonnas
        lines.append(tuple((r, c) for r in range(N)))
    for d in range(-(N - 5), N - 4):                     # diagonāles: c - r = d
        lines.append(tuple((r, r + d) for r in range(N) if 0 <= r + d < N))
    for s in range(4, 2 * N - 5):                        # pretdiagonāles: r + c = s
        lines.append(tuple((r, s - r) for r in range(N) if 0 <= s - r < N))
    return tuple(lines)


LINES = _build_lines()

# Katrai rūtiņai: saraksts ar (līnijas_id, pozīcija_līnijā)
CELL_LINES = [[[] for _ in range(N)] for _ in range(N)]
for _lid, _cells in enumerate(LINES):
    for _pos, (_r, _c) in enumerate(_cells):
        CELL_LINES[_r][_c].append((_lid, _pos))
CELL_LINES = tuple(tuple(tuple(cl) for cl in row) for row in CELL_LINES)


# ---------------------------------------------------------------------------
# Figūru atpazīšana vienā līnijā
# Šeit virknes ir no viena spēlētāja skatpunkta:
#   "x" = savs akmens, "_" = tukšs, "o" = pretinieks / mala (bloķēts)
# ---------------------------------------------------------------------------
def _makes_five(t, i):
    """Vai, ieliekot 'x' pozīcijā i, rodas 5 pēc kārtas?"""
    return "xxxxx" in t[max(0, i - 4):i] + "x" + t[i + 1:i + 5]


def _trim(seg):
    """Nogriež liekās tukšās rūtiņas segmenta galos (lai kešs strādātu labāk)."""
    a = seg.find("x")
    if a < 0:
        return ""
    b = seg.rfind("x")
    return seg[max(0, a - 5):b + 6]


@lru_cache(maxsize=None)
def _seg_level(seg):
    """
    Stiprākās figūras līmenis segmentā, kurā ir tikai 'x' un '_'
    (segmenta gali uzskatāmi par bloķētiem).

    Definīcija ir rekursīva:
      FIVE  — jau ir 5 pēc kārtas
      OPEN4 — ir >= 2 rūtiņas, kas dod piecinieku (nevar nobloķēt)
      FOUR  — ir tieši 1 rūtiņa, kas dod piecinieku
      OPEN3 — ar vienu gājienu var izveidot OPEN4
      THREE — ar vienu gājienu var izveidot FOUR
      OPEN2 — ar vienu gājienu var izveidot OPEN3, utt.
    """
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
                if best == OPEN3:        # augstāks līmenis šeit nav iespējams
                    break
    return best


def _analyze(s, p):
    """
    Analizē līniju `s` spēlētājam `p`.
    Atgriež (novērtējums, līmeņi, karstās_pozīcijas):
      * novērtējums — visu figūru summa šajā līnijā;
      * līmeņi[i]   — kādu figūru p izveidotu, ieliekot akmeni pozīcijā i
                      (0, ja nekas būtisks nerodas);
      * karstās     — (pozīcija, līmenis) pāri, kur līmenis >= OPEN3.
    """
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
        # Lokālais logs ap i (figūra, kurā ietilpst i, ir robežās i±5)
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
            if after >= OPEN3:
                hot.append((i, after))
    return score, tuple(levels), tuple(hot)


@lru_cache(maxsize=200_000)
def _line_info(s):
    """Līnijas analīze abiem spēlētājiem: (info_X, info_O)."""
    return _analyze(s, X), _analyze(s, O)


# ---------------------------------------------------------------------------
# Spēles stāvoklis meklēšanai (darbojas ar laukuma KOPIJU)
# ---------------------------------------------------------------------------
class _Game:
    def __init__(self, board):
        self.cells = [list(row) for row in board]        # kopija!
        self.near = [[0] * N for _ in range(N)]          # kaimiņu skaits 5x5 apkārtnē
        self.stones = 0
        self.lines = []
        self.info = []
        self.score = [0, 0]
        for cells in LINES:
            s = "".join(self.cells[r][c] for r, c in cells)
            inf = _line_info(s)
            self.lines.append(s)
            self.info.append(inf)
            self.score[0] += inf[0][0]
            self.score[1] += inf[1][0]
        for r in range(N):
            for c in range(N):
                if self.cells[r][c] != EMPTY:
                    self._mark_near(r, c, 1)
                    self.stones += 1

    # --- gājiena izdarīšana / atsaukšana ---
    def _mark_near(self, r, c, d):
        for rr in range(max(0, r - 2), min(N, r + 3)):
            row = self.near[rr]
            for cc in range(max(0, c - 2), min(N, c + 3)):
                row[cc] += d

    def _set(self, r, c, ch):
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

    def place(self, r, c, p):
        self._set(r, c, p)
        self._mark_near(r, c, 1)
        self.stones += 1

    def undo(self, r, c):
        self._set(r, c, EMPTY)
        self._mark_near(r, c, -1)
        self.stones -= 1

    # --- analīze ---
    def evaluate(self, k):
        """Pozīcijas novērtējums no spēlētāja k (0=X, 1=O) skatpunkta."""
        return self.score[k] - self.score[1 - k]

    def threats(self, k):
        """
        Spēlētāja k draudi:
          wins   — rūtiņas, kas uzreiz dod piecinieku;
          strong — rūtiņas, kas dod atvērtu vai dubultu četrinieku (= uzvara);
          fours  — rūtiņas, kas dod parastu četrinieku;
          threes — rūtiņas, kas dod atvērtu trijnieku.
        """
        wins, strong, fours, threes = set(), set(), set(), set()
        four_count = {}
        for lid, inf in enumerate(self.info):
            hot = inf[k][2]
            if hot:
                cells = LINES[lid]
                for pos, lv in hot:
                    cell = cells[pos]
                    if lv == FIVE:
                        wins.add(cell)
                    elif lv == OPEN4:
                        strong.add(cell)
                    elif lv == FOUR:
                        fours.add(cell)
                        four_count[cell] = four_count.get(cell, 0) + 1
                    else:
                        threes.add(cell)
        for cell, cnt in four_count.items():
            if cnt >= 2:                       # dubultais četrinieks
                strong.add(cell)
        return wins, strong, fours, threes

    def move_value(self, r, c, k):
        """Heiristiska gājiena vērtība (uzbrukums + aizsardzība) kārtošanai."""
        ko = 1 - k
        att = dfn = 0
        att_hot = def_hot = 0
        for lid, pos in CELL_LINES[r][c]:
            inf = self.info[lid]
            a = inf[k][1][pos]
            d = inf[ko][1][pos]
            att += SHAPE_SCORE[a]
            dfn += SHAPE_SCORE[d]
            if a >= OPEN3:
                att_hot += 1
            if d >= OPEN3:
                def_hot += 1
        v = att + dfn * 4 // 5
        if att_hot >= 2:                        # piem. četrinieks + trijnieks
            v += 50_000
        if def_hot >= 2:
            v += 30_000
        return v + 14 - abs(r - 7) - abs(c - 7)  # neliela priekšroka centram

    def candidates(self, k, limit):
        """Labākie brīvie gājieni pie esošajiem akmeņiem, sakārtoti."""
        scored = []
        for r in range(N):
            row = self.cells[r]
            nr = self.near[r]
            for c in range(N):
                if row[c] == EMPTY and nr[c]:
                    scored.append((self.move_value(r, c, k), r, c))
        scored.sort(reverse=True)
        return [(r, c) for _, r, c in scored[:limit]]

    def order(self, cells, k):
        """Sakārto doto rūtiņu kopu pēc heiristiskās vērtības."""
        scored = [(self.move_value(r, c, k), r, c)
                  for r, c in cells if self.cells[r][c] == EMPTY]
        scored.sort(reverse=True)
        return [(r, c) for _, r, c in scored]


# ---------------------------------------------------------------------------
# Meklēšana
# ---------------------------------------------------------------------------
class _Timeout(Exception):
    pass


class _Searcher:
    def __init__(self, game, deadline):
        self.g = game
        self.deadline = deadline
        self.nodes = 0
        self.partial = None        # labākais gājiens nepabeigtajā iterācijā

    def _forced_moves(self, p):
        """
        Taktiskā analīze mezglā spēlētājam p (kuram ir gājiens).
        Atgriež (rezultāts, gājieni):
          rezultāts != None — pozīcijas vērtība ir zināma bez meklēšanas;
          gājieni — saraksts ar gājieniem, ko vērts apskatīt
                    (None nozīmē "parastie kandidāti").
        Rezultāta vērtības ir relatīvas: WIN = uzvara, -WIN = zaudējums.
        """
        g = self.g
        k = PIDX[p]
        wins_p, strong_p, fours_p, _ = g.threats(k)
        if wins_p:
            return WIN, [next(iter(wins_p))]
        wins_o, strong_o, fours_o, _ = g.threats(1 - k)
        if len(wins_o) >= 2:
            return -(WIN - 1), [next(iter(wins_o))]
        if wins_o:
            return None, [next(iter(wins_o))]             # jābloķē
        if strong_p:
            return WIN - 2, g.order(strong_p, k)
        if strong_o:
            # Pretiniekam ir atvērts trijnieks: aizsargājamies vai uzbrūkam ar četriniekiem
            pool = strong_o | fours_o | fours_p
            return None, g.order(pool, k)
        return None, None

    def negamax(self, p, depth, alpha, beta, ply):
        self.nodes += 1
        if not self.nodes & 15 and time.perf_counter() > self.deadline:
            raise _Timeout

        g = self.g
        result, moves = self._forced_moves(p)
        if result is not None:
            return result - ply if result > 0 else result + ply
        forced = moves is not None and len(moves) == 1
        if not forced:
            if depth <= 0 or ply >= MAX_PLY:
                return g.evaluate(PIDX[p])
            if moves is None:
                moves = g.candidates(PIDX[p], BEAM)
        if not moves:
            return 0                                      # laukums pilns — neizšķirts

        # Piespiedu gājienam dziļumu nesamazinām (pagarinājums)
        next_depth = depth if forced else depth - 1
        o = OTHER[p]
        best = -INF
        for r, c in moves:
            g.place(r, c, p)
            v = -self.negamax(o, next_depth, -beta, -alpha, ply + 1)
            g.undo(r, c)
            if v > best:
                best = v
                if v > alpha:
                    alpha = v
                    if alpha >= beta:
                        break
        return best

    def root(self, moves, p, depth):
        alpha = -INF
        best_v, best_mv = -INF, None
        self.partial = None
        o = OTHER[p]
        for r, c in moves:
            self.g.place(r, c, p)
            v = -self.negamax(o, depth - 1, -INF, -alpha, 1)
            self.g.undo(r, c)
            if v > best_v:
                best_v, best_mv = v, (r, c)
                self.partial = best_mv
            if v > alpha:
                alpha = v
        return best_v, best_mv


def _any_empty(board):
    for r in range(N):
        for c in range(N):
            if board[r][c] == EMPTY:
                return (r, c)
    return (N // 2, N // 2)


def _think(board, player, time_limit=TIME_LIMIT):
    """
    Galvenā domāšanas funkcija.
    Atgriež (gājiens, novērtējums no `player` skatpunkta).
    """
    deadline = time.perf_counter() + time_limit
    g = _Game(board)
    if g.stones == 0:
        return (N // 2, N // 2), 0

    k = PIDX[player]
    s = _Searcher(g, deadline)
    result, moves = s._forced_moves(player)
    if result is not None or (moves is not None and len(moves) == 1):
        return moves[0], (result if result is not None else g.evaluate(k))
    if moves is None:
        moves = g.candidates(k, ROOT_BEAM)
    if not moves:
        return _any_empty(board), 0

    best_mv, best_v = moves[0], g.evaluate(k)
    depth = 1
    while depth <= 20:
        try:
            v, mv = s.root(moves, player, depth)
        except _Timeout:
            if s.partial is not None:
                best_mv = s.partial
            break
        best_mv, best_v = mv, v
        moves.remove(mv)
        moves.insert(0, mv)                    # nākamajā iterācijā pirmais
        if abs(v) >= WIN - 100:                # uzvara vai zaudējums ir atrasts
            break
        depth += 1
    return best_mv, best_v


# ---------------------------------------------------------------------------
# Obligātās funkcijas
# ---------------------------------------------------------------------------
def get_move(board, player):
    """Atgriež (rinda, kolonna) brīvai rūtiņai, kurā bots liek savu simbolu."""
    try:
        move, _ = _think(board, player)
        r, c = move
        if 0 <= r < N and 0 <= c < N and board[r][c] == EMPTY:
            return (r, c)
    except Exception:
        pass
    return _any_empty(board)       # drošības tīkls — vienmēr derīgs gājiens


def _side_value(board, to_move="O", time_limit=TIME_LIMIT):
    """Pozīcijas vērtība no `to_move` skatpunkta (pēc atklātnes gājiens ir O)."""
    try:
        _, v = _think(board, to_move, time_limit)
        return v
    except Exception:
        return 0


def swap2_propose(board):
    """Swap2 1. solis: divi X un viens O uz tukša laukuma."""
    return [(7, 7, X), (8, 8, O), (6, 9, X)]


def swap2_respond(board):
    """
    Swap2 2. solis: izvēlamies krāsu, kura pēc meklēšanas ir izdevīgāka.
    Pēc atklātnes nākamo gājienu veic O.
    """
    v = _side_value(board, O)
    return {"action": "TAKE_O"} if v >= 0 else {"action": "TAKE_X"}


def swap2_final_choice(board):
    """Swap2 3. solis (pēc PLACE_TWO): izvēlamies izdevīgāko krāsu."""
    v = _side_value(board, O)
    return O if v >= 0 else X


if __name__ == "__main__":
    # Ātra pašpārbaude: viens gājiens uz laukuma ar trīs akmeņiem
    demo = [[EMPTY] * N for _ in range(N)]
    for r, c, sym in swap2_propose(demo):
        demo[r][c] = sym
    t0 = time.perf_counter()
    print(BOT_NAME, "->", get_move(demo, O), f"({time.perf_counter() - t0:.2f} s)")
