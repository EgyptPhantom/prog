"""Petera_bots - turnira blackjack bots.

Spele:  katrai darbibai (HIT / STAND / DOUBLE / SPLIT) aprekina paredzamo
        vertibu (EV) pec kurpe atlikusajam kartim. Modelis nem vera sa
        turnira noteikumus: dilers apstajas uz visiem 17, dilers nepaskatas
        sleptaja karti (dilera blackjack panem ari dubultotas/sadalitas
        likmes), pec SPLIT drikst dubultot, duzus sadalot - tikai viena karts.

Likmes: no ta pasa modela aprekina sava priekslrocibu (edge) pirms katras
        partijas un liek likmi, kas velama uzvarai turnira (uzvar tas, kuram
        beigas visvairak cipu), nevis tikai labakajam videjam rezultatam.
"""
from functools import lru_cache

BOT_NAME = "Petera_bots"

MIN_BET = 10
MAX_BET = 200
DEFAULT_DECKS = 4
TOURNAMENT_ROUNDS = 100   # turnira noklusetais partiju skaits

# --- Likmju parametri (noskanoti ar simulacijam, sk. README beigas) ---
BASE_BET = 50             # likme neitralai kurpei
LOW_EDGE = -0.012         # zem sis priekslrocibas liek tikai minimumu
EDGE_GAIN = 12.0          # cik strauji likme aug lidz ar priekslrocibu
TARGET = 1.35             # merkis: sakuma cipi x TARGET
ENDGAME_ROUNDS = 20       # pedejas partijas, kuras speles uz merki

# Stavoklis starp izsaukumiem (modulis tiek ieladets vienreiz turnira laika).
_state = {"round": 0, "start": None, "last_bankroll": None, "decks": DEFAULT_DECKS}

# Dilera iznakumu indeksi: 0 = bust, 1..5 = 17..21, 6 = dabigais blackjack.
_BUST = (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------- kartis
def _value(card):
    """Karts punkti: duzis = 1 (11 skaita _add), desmitnieki = 10."""
    r = card[:-1]
    if r == "A":
        return 1
    if r in ("T", "J", "Q", "K", "10"):
        return 10
    return int(r)


def _add(total, soft, v):
    """Pievieno karti rokai. soft=True nozime, ka viens duzis skaitits ka 11."""
    total += v
    if v == 1 and total <= 11:
        total += 10
        soft = True
    if total > 21 and soft:
        total -= 10
        soft = False
    return total, soft


def _hand(values):
    total, soft = 0, False
    for v in values:
        total, soft = _add(total, soft, v)
    return total, soft


def _counts(history, decks):
    """Atlikuso kartu skaits pa vertibam [A, 2, ..., 9, 10]."""
    counts = [4 * decks] * 9 + [16 * decks]
    for card in history:
        i = _value(card) - 1
        if counts[i] > 0:
            counts[i] -= 1
    return counts


def _probs(counts):
    n = sum(counts)
    if n <= 0:
        return (1 / 13,) * 9 + (4 / 13,)
    return tuple(c / n for c in counts)


# ---------------------------------------------------------------- EV modelis
class _Model:
    """EV aprekins vienai kurpes kompozicijai un dilera atklatajai kartij."""

    def __init__(self, p, up):
        self.p = p
        cards = [(v, w) for v, w in enumerate(p, 1) if w > 0]
        self.cards = cards

        @lru_cache(maxsize=None)
        def dealer(total, soft):
            if total > 21:
                return _BUST
            if total >= 17:
                return tuple(1.0 if i == total - 16 else 0.0 for i in range(7))
            acc = [0.0] * 7
            for v, w in cards:
                for i, x in enumerate(dealer(*_add(total, soft, v))):
                    acc[i] += w * x
            return tuple(acc)

        up_total, up_soft = _add(0, False, up)
        dist = [0.0] * 7
        for v, w in cards:
            t, s = _add(up_total, up_soft, v)
            if t == 21:
                dist[6] += w
            else:
                for i, x in enumerate(dealer(t, s)):
                    dist[i] += w * x
        self.blackjack = dist[6]

        # STAND EV katrai summai: dilera bust = +1, dilera blackjack = -1.
        stand = {}
        for t in range(0, 22):
            ev = dist[0] - dist[6]
            for i in range(1, 6):
                d = 16 + i
                ev += dist[i] * ((t > d) - (t < d))
            stand[t] = ev
        self._stand = stand

        @lru_cache(maxsize=None)
        def best_hit(total, soft):
            """Labaka EV, ja drikst tikai HIT/STAND."""
            if total > 21:
                return -1.0
            s_ev = stand[total]
            if total == 21:
                return s_ev
            return max(s_ev, hit(total, soft))

        @lru_cache(maxsize=None)
        def hit(total, soft):
            return sum(w * best_hit(*_add(total, soft, v)) for v, w in cards)

        self.best_hit = best_hit
        self.hit = hit

    def stand(self, total):
        return -1.0 if total > 21 else self._stand[total]

    def double(self, total, soft):
        return 2.0 * sum(w * self.stand(_add(total, soft, v)[0]) for v, w in self.cards)

    def split(self, v):
        """Sadalisana: bez atkartotas sadalisanas, ar dubultosanu pec SPLIT;
        duzi sanem tikai vienu karti. 21 pec sadalisanas nav blackjack."""
        ev = 0.0
        for r, w in self.cards:
            t, s = _hand((v, r))
            if v == 1:
                ev += w * self.stand(t)
            elif t >= 21:
                ev += w * self.stand(t)
            else:
                ev += w * max(self.best_hit(t, s), self.double(t, s))
        return 2.0 * ev

    def actions(self, total, soft, can_double, pair):
        ev = {"STAND": self.stand(total)}
        if total < 21:
            ev["HIT"] = self.hit(total, soft)
            if can_double:
                ev["DOUBLE"] = self.double(total, soft)
            if pair is not None:
                ev["SPLIT"] = self.split(pair)
        return ev


_model_cache = {}


def _model(p, up):
    key = (p, up)
    m = _model_cache.get(key)
    if m is None:
        if len(_model_cache) > 64:
            _model_cache.clear()
        m = _model_cache[key] = _Model(p, up)
    return m


# ---------------------------------------------------------------- priekslrociba
def _edge(counts):
    """Paredzama pelna uz 1 likmes vienibu nakamaja partija ar optimalu speli.
    Pirmas tris kartis (dilera + 2 speletaja) velk bez atlikšanas."""
    n = sum(counts)
    if n < 10:
        return -0.01
    edge = 0.0
    for up in range(1, 11):
        cu = counts[up - 1]
        if not cu:
            continue
        rest = list(counts)
        rest[up - 1] -= 1
        m = _model(_probs(rest), up)
        bj = m.blackjack
        pu = cu / n
        for a in range(1, 11):
            ca = rest[a - 1]
            if not ca:
                continue
            pa = ca / (n - 1)
            for b in range(a, 11):
                cb = rest[b - 1] - (a == b)
                if cb <= 0:
                    continue
                weight = pu * pa * (cb / (n - 2)) * (1 if a == b else 2)
                t, s = _hand((a, b))
                if t == 21:
                    ev = 1.5 * (1.0 - bj)
                else:
                    ev = max(m.actions(t, s, True, a if a == b else None).values())
                edge += weight * ev
    return edge


# ---------------------------------------------------------------- likmes
def _track_round(bankroll, history, decks_remaining):
    st = _state
    last = st["last_bankroll"]
    new_tournament = (
        st["start"] is None
        or st["round"] >= TOURNAMENT_ROUNDS
        or (not history and bankroll == st["start"] and st["round"] > 0)
        or (last is not None and abs(bankroll - last) > 1000)
    )
    if new_tournament:
        st["round"] = 0
        st["start"] = bankroll
    st["round"] += 1
    st["last_bankroll"] = bankroll
    try:
        total_cards = len(history) + float(decks_remaining) * 52
        st["decks"] = max(1, int(round(total_cards / 52)))
    except (TypeError, ValueError):
        st["decks"] = DEFAULT_DECKS


def _choose_bet(bankroll, edge):
    start = _state["start"] or bankroll
    rounds_left = max(0, TOURNAMENT_ROUNDS - _state["round"])
    target = start * TARGET

    if edge < LOW_EDGE:
        bet = MIN_BET
    else:
        bet = BASE_BET + EDGE_GAIN * max(0.0, edge) * start

    if rounds_left < ENDGAME_ROUNDS:
        if bankroll >= target:
            bet = MIN_BET                     # vadiba - sargajam
        else:
            need = (target - bankroll) / max(1, rounds_left + 1)
            bet = max(bet, need * 2)          # atpaliekam - riskejam
    return bet


def place_bet(bankroll: int, history: list[str], decks_remaining: float) -> int:
    high = min(MAX_BET, int(bankroll))
    if high <= MIN_BET:
        return MIN_BET
    try:
        _track_round(bankroll, history, decks_remaining)
        edge = _edge(_counts(history, _state["decks"]))
        bet = int(_choose_bet(bankroll, edge) // 5 * 5)
    except Exception:
        bet = MIN_BET
    return max(MIN_BET, min(high, bet))


# ---------------------------------------------------------------- gajieni
def decide_action(hand: list[str], dealer_upcard: str, history: list[str],
                  can_double: bool, can_split: bool) -> str:
    try:
        values = [_value(c) for c in hand]
        total, soft = _hand(values)
        if total >= 21:
            return "STAND"
        p = _probs(_counts(history, _state["decks"]))
        m = _model(p, _value(dealer_upcard))
        pair = values[0] if (can_split and len(values) == 2 and values[0] == values[1]) else None
        ev = m.actions(total, soft, can_double and len(values) == 2, pair)
        return max(ev, key=ev.get)
    except Exception:
        try:
            return "STAND" if _hand([_value(c) for c in hand])[0] >= 17 else "HIT"
        except Exception:
            return "STAND"


if __name__ == "__main__":
    import random
    import time

    ranks = "23456789TJQKA"
    shoe = [r + s for r in ranks for s in "HDCS"] * DEFAULT_DECKS
    random.shuffle(shoe)
    seen = shoe[:60]
    t0 = time.perf_counter()
    print("likme:", place_bet(1000, seen, (208 - 60) / 52))
    print("place_bet laiks: %.1f ms" % ((time.perf_counter() - t0) * 1000))
    t0 = time.perf_counter()
    print("8,8 pret 6:", decide_action(["8H", "8S"], "6D", seen, True, True))
    print("decide_action laiks: %.1f ms" % ((time.perf_counter() - t0) * 1000))
