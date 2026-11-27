BOT_NAME = "MartinsCountBot"
_true_count_now = 0.0


def _card_value(card):
    rank = card[:-1]
    if rank in ("T", "J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)


def _hand_value(hand):
    total = 0
    aces = 0
    for card in hand:
        rank = card[:-1]
        if rank == "A":
            aces += 1
            total += 11
        elif rank in ("T", "J", "Q", "K"):
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def _is_soft(hand):
    total = 0
    aces = 0
    for card in hand:
        rank = card[:-1]
        if rank == "A":
            aces += 1
            total += 11
        elif rank in ("T", "J", "Q", "K"):
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return aces > 0


def _true_count(history, decks_remaining):
    running_count = 0
    for card in history:
        rank = card[:-1]
        if rank in ("2", "3", "4", "5", "6"):
            running_count += 1
        elif rank in ("T", "J", "Q", "K", "A"):
            running_count -= 1
    remaining = max(float(decks_remaining), 0.25)
    return running_count / remaining


def place_bet(bankroll: int, history: list[str], decks_remaining: float) -> int:
    global _true_count_now
    maximum = min(200, int(bankroll))
    if maximum < 10:
        return 10

    true_count = _true_count(history, decks_remaining)
    _true_count_now = true_count
    if true_count >= 4:
        bet = 200
    elif true_count >= 3:
        bet = 120
    elif true_count >= 2:
        bet = 80
    elif true_count >= 1:
        bet = 40
    elif true_count <= -2:
        bet = 10
    else:
        bet = 20
    return min(maximum, max(10, bet))


def _pair_action(pair_rank, dealer_value, can_split):
    if not can_split:
        return None
    if pair_rank in ("A", "8"):
        return "SPLIT"
    if pair_rank in ("T", "J", "Q", "K"):
        return "STAND"
    if pair_rank in ("2", "3", "7"):
        return "SPLIT" if dealer_value in (2, 3, 4, 5, 6, 7) else "HIT"
    if pair_rank == "6":
        return "SPLIT" if dealer_value in (2, 3, 4, 5, 6) else "HIT"
    if pair_rank == "4":
        return "SPLIT" if dealer_value in (5, 6) else "HIT"
    if pair_rank == "9":
        if dealer_value in (2, 3, 4, 5, 6, 8, 9):
            return "SPLIT"
        return "STAND"
    return None


def decide_action(
    hand: list[str],
    dealer_upcard: str,
    history: list[str],
    can_double: bool,
    can_split: bool,
) -> str:
    if not hand:
        return "STAND"

    dealer_value = _card_value(dealer_upcard)
    if len(hand) == 2 and can_split:
        first_rank = hand[0][:-1]
        second_rank = hand[1][:-1]
        pair_action = _pair_action(first_rank, dealer_value, first_rank == second_rank)
        if pair_action is not None:
            if pair_action == "SPLIT":
                return "SPLIT"
            if pair_action == "STAND":
                return "STAND"

    total = _hand_value(hand)
    soft = _is_soft(hand)

    if soft:
        if total >= 20:
            return "STAND"
        if total == 19:
            if can_double and dealer_value == 6:
                return "DOUBLE"
            return "STAND"
        if total == 18:
            if can_double and dealer_value in (2, 3, 4, 5, 6):
                return "DOUBLE"
            if dealer_value in (2, 7, 8):
                return "STAND"
            return "HIT"
        if total == 17:
            if can_double and dealer_value in (3, 4, 5, 6):
                return "DOUBLE"
            return "HIT"
        if total in (15, 16):
            if can_double and dealer_value in (4, 5, 6):
                return "DOUBLE"
            return "HIT"
        if total in (13, 14):
            if can_double and dealer_value in (5, 6):
                return "DOUBLE"
            return "HIT"

    count = _true_count_now
    if total == 12:
        if dealer_value == 2 and count >= 3:
            return "STAND"
        if dealer_value == 3 and count >= 2:
            return "STAND"
    if total == 13:
        if dealer_value == 2:
            return "STAND"
    if total == 15:
        if dealer_value == 10 and count >= 4:
            return "STAND"
    if total == 16:
        if dealer_value == 9 and count >= 5:
            return "STAND"
    if total >= 17:
        return "STAND"
    if total >= 13:
        if dealer_value in (2, 3, 4, 5, 6):
            return "STAND"
        return "HIT"
    if total == 12:
        if dealer_value in (4, 5, 6):
            return "STAND"
        return "HIT"
    if total == 11:
        if dealer_value == 11 and can_double and count >= 1:
            return "DOUBLE"
        return "DOUBLE" if can_double else "HIT"
    if total == 10:
        if can_double and dealer_value in (2, 3, 4, 5, 6, 7, 8, 9):
            return "DOUBLE"
        if can_double and dealer_value in (10, 11) and count >= 4:
            return "DOUBLE"
        return "HIT"
    if total == 9:
        if can_double and (dealer_value in (3, 4, 5, 6) or (dealer_value == 2 and count >= 1)):
            return "DOUBLE"
        return "HIT"
    return "HIT"


if __name__ == "__main__":
    assert _hand_value(["AS", "6D"]) == 17
    assert _hand_value(["AS", "AC", "9H"]) == 21
    assert place_bet(1000, [], 4.0) == 20
    assert decide_action(["AS", "6D"], "6C", [], True, False) == "DOUBLE"
