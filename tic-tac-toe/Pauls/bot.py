"""Pauls' Gomoku bot for the 15x15 Swap2 tournament."""

BOT_NAME = "paulsbot"

BOARD_SIZE = 15
WIN_LEN = 5
EMPTY = "_"
WIN_SCORE = 1_000_000
LINE_SCORES = {1: 3, 2: 24, 3: 320, 4: 40_000}
DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))


def _opponent(player: str) -> str:
    return "O" if player == "X" else "X"


def _candidate_moves(board: list[list[str]]) -> list[tuple[int, int]]:
    occupied = [
        (row, col)
        for row in range(BOARD_SIZE)
        for col in range(BOARD_SIZE)
        if board[row][col] != EMPTY
    ]
    if not occupied:
        return [(BOARD_SIZE // 2, BOARD_SIZE // 2)]

    candidates = set()
    for row, col in occupied:
        for row_offset in range(-2, 3):
            for col_offset in range(-2, 3):
                candidate_row = row + row_offset
                candidate_col = col + col_offset
                if (
                    0 <= candidate_row < BOARD_SIZE
                    and 0 <= candidate_col < BOARD_SIZE
                    and board[candidate_row][candidate_col] == EMPTY
                ):
                    candidates.add((candidate_row, candidate_col))
    return sorted(candidates)


def _is_winning_move(board: list[list[str]], row: int, col: int, player: str) -> bool:
    for row_step, col_step in DIRECTIONS:
        count = 1
        for direction in (1, -1):
            current_row = row + row_step * direction
            current_col = col + col_step * direction
            while (
                0 <= current_row < BOARD_SIZE
                and 0 <= current_col < BOARD_SIZE
                and board[current_row][current_col] == player
            ):
                count += 1
                current_row += row_step * direction
                current_col += col_step * direction
        if count >= WIN_LEN:
            return True
    return False


def _winning_moves(board: list[list[str]], player: str) -> list[tuple[int, int]]:
    return [
        (row, col)
        for row, col in _candidate_moves(board)
        if _is_winning_move(board, row, col, player)
    ]


def _line_score(board: list[list[str]], row: int, col: int, player: str) -> int:
    total = 0
    for row_step, col_step in DIRECTIONS:
        length = 1
        open_ends = 0
        for direction in (1, -1):
            current_row = row + row_step * direction
            current_col = col + col_step * direction
            while (
                0 <= current_row < BOARD_SIZE
                and 0 <= current_col < BOARD_SIZE
                and board[current_row][current_col] == player
            ):
                length += 1
                current_row += row_step * direction
                current_col += col_step * direction
            if (
                0 <= current_row < BOARD_SIZE
                and 0 <= current_col < BOARD_SIZE
                and board[current_row][current_col] == EMPTY
            ):
                open_ends += 1

        if length >= WIN_LEN:
            return WIN_SCORE
        score = LINE_SCORES.get(length, 0)
        if open_ends == 2:
            total += score * 2
        elif open_ends == 1:
            total += score
        else:
            total += score // 3
    return total


def _move_score(board: list[list[str]], row: int, col: int, player: str) -> int:
    opponent = _opponent(player)
    attack = _line_score(board, row, col, player)
    defense = _line_score(board, row, col, opponent)
    center_bonus = max(0, BOARD_SIZE - abs(row - 7) - abs(col - 7))
    return attack + int(defense * 1.15) + center_bonus


def _best_position_score(board: list[list[str]], player: str) -> int:
    moves = _candidate_moves(board)
    if not moves:
        return 0
    return max(_line_score(board, row, col, player) for row, col in moves)


def _best_move(board: list[list[str]], player: str, candidates: list[tuple[int, int]]) -> tuple[int, int]:
    return max(
        candidates,
        key=lambda move: (
            _move_score(board, move[0], move[1], player),
            -abs(move[0] - 7) - abs(move[1] - 7),
        ),
    )


def get_move(board: list[list[str]], player: str) -> tuple[int, int]:
    """Win immediately, prevent an immediate loss, then build the best line."""
    moves = _candidate_moves(board)
    if not moves:
        return (7, 7)

    winning = [move for move in moves if _is_winning_move(board, move[0], move[1], player)]
    if winning:
        return _best_move(board, player, winning)

    opponent_wins = [
        move for move in moves
        if _is_winning_move(board, move[0], move[1], _opponent(player))
    ]
    if opponent_wins:
        return _best_move(board, player, opponent_wins)

    return _best_move(board, player, moves)


def swap2_propose(board: list[list[str]]) -> list[tuple[int, int, str]]:
    """Offer a compact, central opening without changing the supplied board."""
    center = BOARD_SIZE // 2
    return [
        (center, center, "X"),
        (center, center + 1, "X"),
        (center + 1, center, "O"),
    ]


def swap2_respond(board: list[list[str]]) -> dict:
    """Choose the color with the stronger follow-up, favoring O's first move."""
    x_value = _best_position_score(board, "X")
    o_value = _best_position_score(board, "O")
    return {"action": "TAKE_O" if o_value * 1.15 >= x_value else "TAKE_X"}


def swap2_final_choice(board: list[list[str]]) -> str:
    """Select the more promising color after the opponent places two stones."""
    x_value = _best_position_score(board, "X")
    o_value = _best_position_score(board, "O")
    return "O" if o_value * 1.15 >= x_value else "X"
