"""Blackjack turnīra bots, kas izmanto pamata stratēģiju un Hi-Lo skaitīšanu."""

BOT_NAME = "ErvinsHiLo"

_HI_LO_VALUES = {
    "2": 1,
    "3": 1,
    "4": 1,
    "5": 1,
    "6": 1,
    "7": 0,
    "8": 0,
    "9": 0,
    "T": -1,
    "J": -1,
    "Q": -1,
    "K": -1,
    "A": -1,
}


def _running_count(history: list[str]) -> int:
    return sum(_HI_LO_VALUES.get(card[:-1], 0) for card in history)


def _true_count(history: list[str], decks_remaining: float) -> float:
    decks = max(0.25, decks_remaining)
    return _running_count(history) / decks


def _hand_value(hand: list[str]) -> tuple[int, bool]:
    total = 0
    aces = 0
    for card in hand:
        rank = card[:-1]
        if rank == "A":
            total += 11
            aces += 1
        elif rank in {"T", "J", "Q", "K"}:
            total += 10
        else:
            total += int(rank)

    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0


def _dealer_value(card: str) -> int:
    rank = card[:-1]
    if rank == "A":
        return 11
    if rank in {"T", "J", "Q", "K"}:
        return 10
    return int(rank)


def place_bet(bankroll: int, history: list[str], decks_remaining: float) -> int:
    """Raise the wager when the remaining shoe is favorable."""
    max_bet = min(200, bankroll)
    true_count = _true_count(history, decks_remaining)
    if true_count < 1:
        desired_bet = 10
    elif true_count < 2:
        desired_bet = 20
    elif true_count < 3:
        desired_bet = 40
    elif true_count < 4:
        desired_bet = 80
    else:
        desired_bet = 200
    return max(10, min(max_bet, desired_bet))


def decide_action(
    hand: list[str],
    dealer_upcard: str,
    history: list[str],
    can_double: bool,
    can_split: bool,
) -> str:
    """Choose an action using basic strategy with a few Hi-Lo deviations."""
    dealer = _dealer_value(dealer_upcard)
    total, soft = _hand_value(hand)
    true_count = _true_count(history, max(0.25, 4 - len(history) / 52))

    if len(hand) == 2 and can_split:
        first_rank, second_rank = hand[0][:-1], hand[1][:-1]
        if first_rank == second_rank:
            pair_value = _hand_value([hand[0]])[0]
            if pair_value in {11, 8}:
                return "SPLIT"
            if pair_value == 9 and dealer in {2, 3, 4, 5, 6, 8, 9}:
                return "SPLIT"
            if pair_value == 7 and 2 <= dealer <= 7:
                return "SPLIT"
            if pair_value == 6 and 2 <= dealer <= 6:
                return "SPLIT"
            if pair_value == 4 and dealer in {5, 6}:
                return "SPLIT"
            if pair_value in {2, 3} and 2 <= dealer <= 7:
                return "SPLIT"

    if not soft:
        if total == 16 and dealer == 10 and true_count >= 0:
            return "STAND"
        if total == 15 and dealer == 10 and true_count >= 4:
            return "STAND"
        if total == 12 and dealer == 3 and true_count >= 2:
            return "STAND"
        if total == 12 and dealer == 2 and true_count >= 3:
            return "STAND"
        if total == 10 and dealer == 10 and true_count >= 4 and can_double:
            return "DOUBLE"
        if total == 9 and dealer == 2 and true_count >= 1 and can_double:
            return "DOUBLE"

        if total <= 8:
            return "HIT"
        if total == 9:
            if 3 <= dealer <= 6 and can_double:
                return "DOUBLE"
            return "HIT"
        if total == 10:
            if 2 <= dealer <= 9 and can_double:
                return "DOUBLE"
            return "HIT"
        if total == 11:
            return "DOUBLE" if can_double else "HIT"
        if total == 12:
            return "STAND" if 4 <= dealer <= 6 else "HIT"
        if 13 <= total <= 16:
            return "STAND" if 2 <= dealer <= 6 else "HIT"
        return "STAND"

    if total >= 19:
        return "STAND"
    if total == 18:
        if 3 <= dealer <= 6:
            return "DOUBLE" if can_double else "STAND"
        return "STAND" if dealer in {2, 7, 8} else "HIT"
    if total == 17:
        return "DOUBLE" if 3 <= dealer <= 6 and can_double else "HIT"
    if total in {15, 16}:
        return "DOUBLE" if 4 <= dealer <= 6 and can_double else "HIT"
    if total in {13, 14}:
        return "DOUBLE" if 5 <= dealer <= 6 and can_double else "HIT"
    return "DOUBLE" if 5 <= dealer <= 6 and can_double else "HIT"
