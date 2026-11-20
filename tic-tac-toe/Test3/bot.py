import random
import time

BOT_NAME = "BossAI (Iterative Negamax)"
BOARD_SIZE = 15
WIN_LENGTH = 5
EMPTY = "_"

DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))
WIN_SCORE = 10_000_000
SEARCH_TIME_LIMIT = 0.85  # Droša rezerve zem 1.0s turnīra limita

# Zobrist hash tabula ātrai stāvokļu kešošanai
_rng = random.Random(42)
ZOBRIST = {
    (r, c, p): _rng.getrandbits(64)
    for r in range(BOARD_SIZE)
    for c in range(BOARD_SIZE)
    for p in ("X", "O")
}


def _opponent(player: str) -> str:
    return "O" if player == "X" else "X"


def _compute_hash(board: list[list[str]]) -> int:
    h = 0
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            cell = board[r][c]
            if cell != EMPTY:
                h ^= ZOBRIST[(r, c, cell)]
    return h


def _candidate_moves(board: list[list[str]], radius: int = 2) -> list[tuple[int, int]]:
    candidates = set()
    has_pieces = False
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if board[r][c] != EMPTY:
                has_pieces = True
                r_min = max(0, r - radius)
                r_max = min(BOARD_SIZE, r + radius + 1)
                c_min = max(0, c - radius)
                c_max = min(BOARD_SIZE, c + radius + 1)
                for rr in range(r_min, r_max):
                    for cc in range(c_min, c_max):
                        if board[rr][cc] == EMPTY:
                            candidates.add((rr, cc))
    return list(candidates) if has_pieces else [(7, 7)]


def _is_winner(board: list[list[str]], r: int, c: int, player: str) -> bool:
    for dr, dc in DIRECTIONS:
        count = 1
        rr, cc = r + dr, c + dc
        while 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and board[rr][cc] == player:
            count += 1
            rr += dr
            cc += dc
        rr, cc = r - dr, c - dc
        while 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and board[rr][cc] == player:
            count += 1
            rr -= dr
            cc -= dc
        if count >= WIN_LENGTH:
            return True
    return False


def _score_sequence(count: int, open_ends: int, is_own: bool) -> int:
    if count >= 5:
        return WIN_SCORE
    if open_ends == 0:
        return 0
    if count == 4:
        if open_ends == 2:
            return 250_000 if is_own else 400_000
        return 25_000 if is_own else 45_000
    if count == 3:
        if open_ends == 2:
            return 8_000 if is_own else 14_000
        return 600 if is_own else 900
    if count == 2:
        return 120 if open_ends == 2 else 20
    return 5 if open_ends == 2 else 1


def _evaluate(board: list[list[str]], player: str) -> int:
    """Ātra līniju eiristika attiecībā pret aktīvo spēlētāju `player`."""
    opponent = _opponent(player)
    total = 0

    # Pārbaudām visas rindas, kolonnas un diagonāles pa segmentiem
    lines = []
    for i in range(BOARD_SIZE):
        lines.append([board[i][c] for c in range(BOARD_SIZE)])
        lines.append([board[r][i] for r in range(BOARD_SIZE)])

    for d in range(-BOARD_SIZE + 5, BOARD_SIZE - 4):
        diag1 = []
        diag2 = []
        for r in range(BOARD_SIZE):
            c1 = r - d
            c2 = BOARD_SIZE - 1 - r - d
            if 0 <= c1 < BOARD_SIZE:
                diag1.append(board[r][c1])
            if 0 <= c2 < BOARD_SIZE:
                diag2.append(board[r][c2])
        lines.append(diag1)
        lines.append(diag2)

    for line in lines:
        n = len(line)
        i = 0
        while i < n:
            cell = line[i]
            if cell == EMPTY:
                i += 1
                continue
            j = i
            while j < n and line[j] == cell:
                j += 1
            count = j - i
            open_ends = 0
            if i > 0 and line[i - 1] == EMPTY:
                open_ends += 1
            if j < n and line[j] == EMPTY:
                open_ends += 1

            pts = _score_sequence(count, open_ends, cell == player)
            total += pts if cell == player else -pts
            i = j

    return total


def _move_heuristic(board: list[list[str]], r: int, c: int, player: str) -> int:
    """Ātrs gājiena prioritātes novērtējums kārtošanai (Alpha-Beta paātrināšanai)."""
    opponent = _opponent(player)
    score = 14 - (abs(r - 7) + abs(c - 7))

    for sym, weight in ((player, 12), (opponent, 10)):
        for dr, dc in DIRECTIONS:
            count = 1
            open_ends = 0
            for step in (1, -1):
                rr, cc = r + dr * step, c + dc * step
                while 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and board[rr][cc] == sym:
                    count += 1
                    rr += dr * step
                    cc += dc * step
                if 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and board[rr][cc] == EMPTY:
                    open_ends += 1
            if count >= 5:
                score += 1_000_000 * weight
            elif count == 4:
                score += (40_000 if open_ends == 2 else 8_000) * weight
            elif count == 3:
                score += (3_000 if open_ends == 2 else 300) * weight
            elif count == 2:
                score += 80 * weight
    return score


def _negamax(
    board: list[list[str]],
    player: str,
    depth: int,
    alpha: int,
    beta: int,
    board_hash: int,
    deadline: float,
    tt: dict,
) -> int:
    if time.perf_counter() >= deadline:
        raise TimeoutError

    tt_key = (board_hash, player, depth)
    if tt_key in tt:
        return tt[tt_key]

    if depth <= 0:
        val = _evaluate(board, player)
        tt[tt_key] = val
        return val

    candidates = _candidate_moves(board, radius=2)
    if not candidates:
        return 0

    ordered = sorted(
        candidates,
        key=lambda m: _move_heuristic(board, m[0], m[1], player),
        reverse=True,
    )[:14]  # Apskatām 14 perspektīvākos zarus

    opponent = _opponent(player)
    best = -WIN_SCORE * 2

    for r, c in ordered:
        board[r][c] = player
        try:
            if _is_winner(board, r, c, player):
                val = WIN_SCORE + depth
            else:
                new_hash = board_hash ^ ZOBRIST[(r, c, player)]
                val = -_negamax(
                    board,
                    opponent,
                    depth - 1,
                    -beta,
                    -alpha,
                    new_hash,
                    deadline,
                    tt,
                )
        finally:
            board[r][c] = EMPTY

        if val > best:
            best = val
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break

    tt[tt_key] = best
    return best


def get_move(board: list[list[str]], player: str) -> tuple[int, int]:
    candidates = _candidate_moves(board, radius=2)
    if len(candidates) == 1:
        return candidates[0]

    opponent = _opponent(player)

    # 1. Tūlītēja uzvara 1 gājienā
    for r, c in candidates:
        board[r][c] = player
        win = _is_winner(board, r, c, player)
        board[r][c] = EMPTY
        if win:
            return (r, c)

    # 2. Obligāta bloķēšana pretinieka uzvarai 1 gājienā
    for r, c in candidates:
        board[r][c] = opponent
        opp_win = _is_winner(board, r, c, opponent)
        board[r][c] = EMPTY
        if opp_win:
            return (r, c)

    ordered = sorted(
        candidates,
        key=lambda m: _move_heuristic(board, m[0], m[1], player),
        reverse=True,
    )[:15]

    best_move = ordered[0]
    deadline = time.perf_counter() + SEARCH_TIME_LIMIT
    base_hash = _compute_hash(board)
    tt = {}

    # 3. Iterative Deepening (droši sasniedz 4.–5. dziļumu iekļaujoties laikā)
    for depth in range(2, 7):
        if time.perf_counter() >= deadline:
            break

        current_best_move = None
        current_best_score = -WIN_SCORE * 2
        alpha = -WIN_SCORE * 2
        beta = WIN_SCORE * 2
        completed = True

        for r, c in ordered:
            board[r][c] = player
            try:
                if _is_winner(board, r, c, player):
                    score = WIN_SCORE + depth
                else:
                    new_hash = base_hash ^ ZOBRIST[(r, c, player)]
                    score = -_negamax(
                        board,
                        opponent,
                        depth - 1,
                        -beta,
                        -alpha,
                        new_hash,
                        deadline,
                        tt,
                    )
            except TimeoutError:
                board[r][c] = EMPTY
                completed = False
                break
            finally:
                board[r][c] = EMPTY

            if score > current_best_score:
                current_best_score = score
                current_best_move = (r, c)
            if score > alpha:
                alpha = score

        if completed and current_best_move is not None:
            best_move = current_best_move
            # Pārkārtojam saknes gājienus, lai nākamajā dziļumā labākais būtu pirmais
            ordered.remove(best_move)
            ordered.insert(0, best_move)
            if current_best_score >= WIN_SCORE:
                break

    return best_move


def swap2_propose(board: list[list[str]]) -> list[tuple[int, int, str]]:
    # Līdzsvarota klasiskā Swap2 atklātne (netiešs novietojums, grūti uzreiz izmantot)
    return [(7, 7, "X"), (6, 8, "X"), (8, 9, "O")]


def swap2_respond(board: list[list[str]]) -> dict:
    # Novērtējam pozīciju ar 2 gājienu skatu uz priekšu
    x_eval = _evaluate(board, "X")
    if x_eval > 180:
        return {"action": "TAKE_X"}
    if x_eval < -120:
        return {"action": "TAKE_O"}

    # Ja pozīcija ir aptuveni vienāda, liekam 2 neitrālas figūras tuvumā centram
    candidates = _candidate_moves(board, radius=1)
    if len(candidates) >= 2:
        best_pair = None
        best_diff = float("inf")
        for i in range(min(len(candidates), 10)):
            r1, c1 = candidates[i]
            board[r1][c1] = "X"
            for j in range(min(len(candidates), 10)):
                if i == j:
                    continue
                r2, c2 = candidates[j]
                board[r2][c2] = "O"
                diff = abs(_evaluate(board, "X"))
                if diff < best_diff:
                    best_diff = diff
                    best_pair = [(r1, c1, "X"), (r2, c2, "O")]
                board[r2][c2] = EMPTY
            board[r1][c1] = EMPTY
        if best_pair:
            return {"action": "PLACE_TWO", "moves": best_pair}

    return {"action": "TAKE_X"} if x_eval >= 0 else {"action": "TAKE_O"}


def swap2_final_choice(board: list[list[str]]) -> str:
    return "X" if _evaluate(board, "X") >= 0 else "O"