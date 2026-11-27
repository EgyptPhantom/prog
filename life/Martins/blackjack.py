"""MartinsCountBot v3 - adaptīvs Hi-Lo skaitītājs.

* Sākuma bankroll tiek nolasīts automātiski (pirmais place_bet izsaukums).
* Likmju skala, "pārsvars / atpalikšana" sliekšņi un limiti ir relatīvi pret sākuma bankroll.
* Kavu skaits netiek pieņemts - true count rēķina no `decks_remaining`.
* Basic strategy (S17) + Illustrious 18 novirzes.

Tikai standarta bibliotēka, importējot nekas netiek aprēķināts.
"""

BOT_NAME = "MartinsCountBot"

# ---------------------------------------------------------------- konstantes
TOTAL_ROUNDS = 100        # raundu skaits vienā spēlē (vienīgais, ko bots nevar uzzināt pats)
MIN_BET = 10
MAX_BET = 200

TOP_FRAC = 0.25           # lielākā likme = 25% no sākuma bankroll, ierobežota ar [TOP_MIN, MAX_BET]
TOP_MIN = 20
RAMP_UNITS = [0.0, 0.0, 0.2, 0.4, 0.7, 1.0]   # daļa no TOP pie TC <1, 1, 2, 3, 4, 5+; 0 -> MIN_BET
FRAC = 0.12               # neitrālā režīmā likme <= 12% no pašreizējā bankroll

TARGET = 0.35             # aptuvenā līdera peļņa (daļa no starta); sasniedzot to, sargājam
LEAD_SMALL = 0.10         # priekšā tempam par 10% tuvu beigām -> sargājam
BEHIND_GAP = 0.10         # atpaliekam no tempa par 10% -> sākam riskēt
CHASE_MULT = 2.0          # maksimālais likmes reizinātājs atpalikšanā
CHASE_FLOOR_LATE = 0.25   # daļa no TOP, pēdējos 30 raundos
CHASE_FLOOR_END = 0.40    # daļa no TOP, pēdējos 10 raundos
END_N = 5                 # beigu spurts pēdējos N raundos (0 = izslēgts)
END_DIV = 0.5             # jo mazāks, jo agresīvāks spurts
CHASE_FRAC = 0.12         # chase režīmā likme <= 12% no bankroll

_state = {"calls": 0, "start": None, "decks": 4.0, "hist_len": 0}


# ---------------------------------------------------------------- palīgfunkcijas
def _rank(card):
    r = card[:-1]
    return "T" if r == "10" else r


def _val(card):
    r = _rank(card)
    if r == "A":
        return 11
    if r in ("T", "J", "Q", "K"):
        return 10
    return int(r)


def _hand_info(hand):
    """Atgriež (summa, vai_soft)."""
    total = 0
    aces = 0
    for c in hand:
        v = _val(c)
        total += v
        if v == 11:
            aces += 1
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0


def _running_count(history):
    rc = 0
    for c in history:
        v = _val(c)
        if v <= 6:
            rc += 1
        elif v >= 10:      # 10, J, Q, K, A (A = 11)
            rc -= 1
    return rc


def _true_count(history, decks_remaining):
    d = max(float(decks_remaining), 0.5)
    return _running_count(history) / d


# ---------------------------------------------------------------- likmes
def _ramp_bet(tc, top):
    i = int(tc) if tc >= 1 else 0
    u = RAMP_UNITS[min(i, len(RAMP_UNITS) - 1)]
    return max(MIN_BET, u * top)


def place_bet(bankroll: int, history: list[str], decks_remaining: float) -> int:
    try:
        bankroll = int(bankroll)

        # jauns turnīrs -> atjaunojam sākuma bankroll un raundu skaitītāju.
        # Pazīmes: (1) pirmais izsaukums, (2) tīra kurpe un bankroll pēkšņi atšķiras vairāk,
        # nekā iespējams vienā raundā (turnīrs sākts no jauna), (3) nospēlēti TOTAL_ROUNDS raundi.
        idx = _state["calls"]
        last_bk = _state.get("last_bk")
        jumped = (
            last_bk is not None
            and not history
            and abs(bankroll - last_bk) > 6 * _state.get("last_bet", MIN_BET) + 10
        )
        if _state["start"] is None or jumped or (idx > 0 and idx % TOTAL_ROUNDS == 0):
            _state["start"] = max(bankroll, 1)
            if jumped:
                idx = 0
        _state["calls"] = idx + 1
        _state["last_bk"] = bankroll
        _state["decks"] = float(decks_remaining)
        _state["hist_len"] = len(history)

        start = _state["start"]
        cap = min(MAX_BET, bankroll)
        if cap < MIN_BET:
            return MIN_BET

        rounds_left = TOTAL_ROUNDS - (idx % TOTAL_ROUNDS)
        top = min(MAX_BET, max(TOP_MIN, start * TOP_FRAC))
        tc = _true_count(history, decks_remaining)
        bet = float(_ramp_bet(tc, top))
        profit = (bankroll - start) / float(start)

        # Bots neredz citu botu čipus, tāpēc "līdera" līmeni modelējam ar mērķa peļņu TARGET
        # (cik % no starta parasti vajag, lai būtu pirmajā vietā) un lineāru tempu uz to.
        played = idx % TOTAL_ROUNDS
        expected = TARGET * played / float(TOTAL_ROUNDS)
        gap = profit - expected

        if profit >= TARGET:
            # esam līdera līmenī - sargājam
            bet *= 0.5
            if tc < 2:
                bet = MIN_BET
            if rounds_left <= 15:
                bet = MIN_BET if tc < 3 else min(bet, 0.5 * top)
        elif gap >= LEAD_SMALL and rounds_left <= 12:
            bet = min(bet, 0.4 * top)
        elif gap <= -BEHIND_GAP:
            # atpaliekam no līdera tempa - riskējam vairāk, jo tālāk atpaliekam
            urgency = min(1.0, -gap / 0.3)
            bet *= 1.0 + (CHASE_MULT - 1.0) * urgency
            if rounds_left <= 30:
                bet = max(bet, CHASE_FLOOR_LATE * top * urgency)
            if rounds_left <= 10:
                bet = max(bet, CHASE_FLOOR_END * top * urgency)
            bet = min(bet, max(MIN_BET, bankroll * CHASE_FRAC))
        else:
            bet = min(bet, max(MIN_BET, bankroll * FRAC))

        # beigu spurts: pēdējos END_N raundos, ja neesam sasnieguši līdera līmeni, liekam
        # tik, cik vajag, lai pietrūkstošo peļņu panāktu atlikušajos raundos
        if END_N > 0 and rounds_left <= END_N and profit < TARGET:
            need = (TARGET - profit) * start
            bet = max(bet, min(top, need / max(1.0, rounds_left * END_DIV)))

        final = int(max(MIN_BET, min(cap, round(bet))))
        _state["last_bet"] = final
        return final
    except Exception:
        return MIN_BET


# ---------------------------------------------------------------- spēles lēmumi
def _split_action(v, hand, up, tc):
    if v == 11 or v == 8:
        return "SPLIT"
    if v == 10:
        if _rank(hand[0]) == _rank(hand[1]):
            if (up == 5 and tc >= 5) or (up == 6 and tc >= 4):
                return "SPLIT"
        return None
    if v == 9:
        return "SPLIT" if up in (2, 3, 4, 5, 6, 8, 9) else None
    if v == 7:
        return "SPLIT" if 2 <= up <= 7 else None
    if v == 6:
        return "SPLIT" if 2 <= up <= 6 else None
    if v in (2, 3):
        return "SPLIT" if 4 <= up <= 7 else None
    return None


def _soft_action(total, up, tc, can_double):
    if total >= 21:
        return "STAND"
    if total == 20:
        if can_double and ((up == 5 and tc >= 5) or (up == 6 and tc >= 4)):
            return "DOUBLE"
        return "STAND"
    if total == 19:
        if can_double and ((up == 6 and tc >= 1) or (up == 5 and tc >= 3)):
            return "DOUBLE"
        return "STAND"
    if total == 18:
        if 3 <= up <= 6:
            return "DOUBLE" if can_double else "STAND"
        if up in (2, 7, 8):
            return "STAND"
        return "HIT"
    if total == 17:
        if can_double and (3 <= up <= 6 or (up == 2 and tc >= 1)):
            return "DOUBLE"
        return "HIT"
    if total in (15, 16):
        if can_double and 4 <= up <= 6:
            return "DOUBLE"
        return "HIT"
    if total in (13, 14):
        if can_double and 5 <= up <= 6:
            return "DOUBLE"
        return "HIT"
    return "HIT"


def _hard_action(t, up, tc, can_double):
    if t >= 17:
        return "STAND"
    if t >= 13:
        if t == 16 and up == 10 and tc >= 0:
            return "STAND"
        if t == 16 and up == 9 and tc >= 4:
            return "STAND"
        if t == 15 and up == 10 and tc >= 4:
            return "STAND"
        if t == 13 and up == 2:
            return "STAND" if tc >= -1 else "HIT"
        if t == 13 and up == 3:
            return "STAND" if tc >= -2 else "HIT"
        return "STAND" if up <= 6 else "HIT"
    if t == 12:
        if up == 2:
            return "STAND" if tc >= 3 else "HIT"
        if up == 3:
            return "STAND" if tc >= 2 else "HIT"
        if up == 4:
            return "STAND" if tc >= 0 else "HIT"
        if up == 5:
            return "STAND" if tc >= -2 else "HIT"
        if up == 6:
            return "STAND" if tc >= -1 else "HIT"
        return "HIT"
    if t == 11:
        if can_double and (up <= 10 or tc >= 1):
            return "DOUBLE"
        return "HIT"
    if t == 10:
        if can_double and (2 <= up <= 9 or (up == 10 and tc >= 4) or (up == 11 and tc >= 3)):
            return "DOUBLE"
        return "HIT"
    if t == 9:
        if can_double and (3 <= up <= 6 or (up == 2 and tc >= 1) or (up == 7 and tc >= 3)):
            return "DOUBLE"
        return "HIT"
    if t == 8:
        if can_double and up == 6 and tc >= 2:
            return "DOUBLE"
        return "HIT"
    return "HIT"


def decide_action(
    hand: list[str],
    dealer_upcard: str,
    history: list[str],
    can_double: bool,
    can_split: bool,
) -> str:
    try:
        if not hand:
            return "STAND"
        up = _val(dealer_upcard)

        # atlikušās kavas = vērtība no place_bet mīnus kopš tā laika izdalītās kārtis
        dealt_since = max(0, len(history) - _state["hist_len"])
        decks_est = _state["decks"] - dealt_since / 52.0
        tc = _true_count(history, decks_est)

        total, soft = _hand_info(hand)
        if total >= 21:
            return "STAND"

        if len(hand) == 2 and can_split and _val(hand[0]) == _val(hand[1]):
            a = _split_action(_val(hand[0]), hand, up, tc)
            if a == "SPLIT":
                return "SPLIT"

        if soft:
            act = _soft_action(total, up, tc, can_double)
        else:
            act = _hard_action(total, up, tc, can_double)

        if act == "DOUBLE" and not can_double:
            act = "HIT"
        return act
    except Exception:
        return "STAND"


if __name__ == "__main__":
    assert _hand_info(["AS", "6D"]) == (17, True)
    assert _hand_info(["AS", "AC", "9H"]) == (21, True)
    assert place_bet(1000, [], 4.0) == 10
    assert decide_action(["AS", "6D"], "6C", [], True, False) == "DOUBLE"
    assert decide_action(["8S", "8D"], "TC", [], True, True) == "SPLIT"
    assert decide_action(["TS", "6D"], "TC", [], False, False) == "STAND"
    print("OK")
