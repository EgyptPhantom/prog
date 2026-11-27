"""Knight_bot: tactical 15x15 Gomoku with Swap2 and local opponent learning."""

import json
import os
import random
import tempfile
import time
import warnings
from functools import lru_cache
from pathlib import Path
from typing import TypeAlias


BOARD_SIZE = 15
WIN_LENGTH = 5
EMPTY = "_"
SYMBOLS = ("X", "O")
DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))
BOT_NAME: str = "Knight_bot"

Board: TypeAlias = list[list[str]]
Move: TypeAlias = tuple[int, int]
OpeningMove: TypeAlias = tuple[int, int, str]
TableEntry: TypeAlias = tuple[int, int, int, Move | None]

_LINE_VALUES = (0, 1, 8, 70, 1_000, 100_000)
_MATE_SCORE = 1_000_000_000
_ROOT_LIMIT = 10
_SEARCH_LIMIT = 5
_THINK_TIME = 0.84
_MAX_PLY = 30
_LEARNING_PATH = Path(__file__).with_name("Knight_bot_learning.json")
_LEARNED_PATTERNS: dict[str, int] = {}
_PATTERN_WEIGHTS: dict[str, float] = {}
_GAME_PATTERNS: set[str] = set()
_RESULTS = {"wins": 0, "losses": 0, "draws": 0}
_OPENING_RESULTS: dict[str, dict[str, int]] = {}
_RESPONSE_RESULTS: dict[str, dict[str, dict[str, int]]] = {}
_LEARNING_LOADED = False
_EXPECTED_BOARD: Board | None = None
_CURRENT_OPENING_KEY: str | None = None
_CURRENT_OPENING_ACTION: str | None = None
_CURRENT_OPENING_ROLE: str | None = None

_ZOBRIST_RANDOM = random.Random(0x4B4E4947)
_ZOBRIST = tuple(
    tuple(tuple(_ZOBRIST_RANDOM.getrandbits(64) for _ in SYMBOLS) for _ in range(BOARD_SIZE))
    for _ in range(BOARD_SIZE)
)
_ZOBRIST_SIDE = {symbol: _ZOBRIST_RANDOM.getrandbits(64) for symbol in SYMBOLS}


class _SearchTimeout(Exception):
    pass


def _load_learning(force: bool = False) -> None:
    global _LEARNING_LOADED
    if _LEARNING_LOADED and not force:
        return
    _LEARNING_LOADED = True
    _LEARNED_PATTERNS.clear()
    _PATTERN_WEIGHTS.clear()
    _RESULTS.update(wins=0, losses=0, draws=0)
    _OPENING_RESULTS.clear()
    _RESPONSE_RESULTS.clear()
    try:
        data = json.loads(_LEARNING_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    except (OSError, ValueError) as error:
        warnings.warn(f"Knight_bot could not read its learning data: {error}", RuntimeWarning)
        return

    if not isinstance(data, dict) or data.get("version") not in (1, 2, 3):
        warnings.warn("Knight_bot ignored invalid learning data.", RuntimeWarning)
        return
    moves = data.get("relative_moves")
    if not isinstance(moves, dict):
        warnings.warn("Knight_bot ignored invalid learned move patterns.", RuntimeWarning)
        return
    for key, count in moves.items():
        try:
            row_step, col_step = (int(value) for value in key.split(","))
        except (AttributeError, ValueError):
            continue
        if (
            max(abs(row_step), abs(col_step)) in (1, 2)
            and type(count) is int
            and count > 0
        ):
            key = f"{row_step},{col_step}"
            _LEARNED_PATTERNS[key] = min(count, 100_000)
            _PATTERN_WEIGHTS[key] = 1.0

    weights = data.get("pattern_weights", {})
    if isinstance(weights, dict):
        for key, weight in weights.items():
            if (
                key in _LEARNED_PATTERNS
                and isinstance(weight, (int, float))
                and 0.25 <= weight <= 4.0
            ):
                _PATTERN_WEIGHTS[key] = float(weight)

    results = data.get("results", {})
    if isinstance(results, dict):
        for result in _RESULTS:
            count = results.get(result)
            if type(count) is int and count >= 0:
                _RESULTS[result] = count
    opening_results = data.get("opening_results", {})
    if isinstance(opening_results, dict):
        for key, counts in opening_results.items():
            if isinstance(counts, dict):
                _OPENING_RESULTS[key] = {
                    result: counts.get(result, 0)
                    for result in _RESULTS
                    if type(counts.get(result, 0)) is int and counts.get(result, 0) >= 0
                }
    response_results = data.get("response_results", {})
    if isinstance(response_results, dict):
        for key, actions in response_results.items():
            if not isinstance(actions, dict):
                continue
            _RESPONSE_RESULTS[key] = {}
            for action, counts in actions.items():
                if action not in ("TAKE_X", "TAKE_O", "PLACE_TWO") or not isinstance(counts, dict):
                    continue
                _RESPONSE_RESULTS[key][action] = {
                    result: counts.get(result, 0)
                    for result in _RESULTS
                    if type(counts.get(result, 0)) is int and counts.get(result, 0) >= 0
                }


def _save_learning() -> None:
    data = {
        "version": 3,
        "relative_moves": _LEARNED_PATTERNS,
        "pattern_weights": _PATTERN_WEIGHTS,
        "results": _RESULTS,
        "opening_results": _OPENING_RESULTS,
        "response_results": _RESPONSE_RESULTS,
    }
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(_LEARNING_PATH.parent),
            prefix=f".{_LEARNING_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(data, temporary_file, sort_keys=True)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, _LEARNING_PATH)
    except OSError as error:
        warnings.warn(f"Knight_bot could not save its learning data: {error}", RuntimeWarning)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as error:
                warnings.warn(
                    f"Knight_bot could not remove temporary learning data: {error}",
                    RuntimeWarning,
                )


def _record_opponent_move(board: Board, player: str) -> None:
    global _EXPECTED_BOARD
    previous = _EXPECTED_BOARD
    _EXPECTED_BOARD = None
    if previous is None:
        return

    previous_count = sum(cell != EMPTY for row in previous for cell in row)
    current_count = sum(cell != EMPTY for row in board for cell in row)
    if current_count != previous_count + 1:
        return

    opponent = _opponent(player)
    added = []
    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            if previous[row][col] == board[row][col]:
                continue
            if previous[row][col] == EMPTY and board[row][col] == opponent:
                added.append((row, col))
            else:
                return
    if len(added) != 1:
        return

    row, col = added[0]
    prior_opponent_stones = [
        (r, c)
        for r in range(BOARD_SIZE)
        for c in range(BOARD_SIZE)
        if previous[r][c] == opponent
    ]
    if not prior_opponent_stones:
        return

    nearest = min(
        prior_opponent_stones,
        key=lambda cell: max(abs(row - cell[0]), abs(col - cell[1])),
    )
    row_step, col_step = row - nearest[0], col - nearest[1]
    if max(abs(row_step), abs(col_step)) not in (1, 2):
        return

    _load_learning()
    key = f"{row_step},{col_step}"
    _LEARNED_PATTERNS[key] = min(_LEARNED_PATTERNS.get(key, 0) + 1, 100_000)
    _PATTERN_WEIGHTS.setdefault(key, 1.0)
    _GAME_PATTERNS.add(key)
    _save_learning()


def _learning_targets(board: Board, player: str) -> dict[Move, int]:
    _load_learning()
    if not _LEARNED_PATTERNS:
        return {}

    opponent = _opponent(player)
    patterns = sorted(
        _LEARNED_PATTERNS.items(),
        key=lambda item: item[1] * _PATTERN_WEIGHTS.get(item[0], 1.0),
        reverse=True,
    )[:16]
    targets: dict[Move, int] = {}
    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            if board[row][col] != opponent:
                continue
            for pattern, count in patterns:
                row_step, col_step = (int(value) for value in pattern.split(","))
                target = (row + row_step, col + col_step)
                target_row, target_col = target
                if (
                    0 <= target_row < BOARD_SIZE
                    and 0 <= target_col < BOARD_SIZE
                    and board[target_row][target_col] == EMPTY
                ):
                    weight = _PATTERN_WEIGHTS.get(pattern, 1.0)
                    bonus = min(90, int(count * weight * 9))
                    targets[target] = max(targets.get(target, 0), bonus)
    return targets


def record_result(result: str) -> None:
    """Update persisted opponent-pattern weights after a completed game."""
    global _CURRENT_OPENING_ACTION, _CURRENT_OPENING_KEY, _CURRENT_OPENING_ROLE
    global _EXPECTED_BOARD
    _load_learning(force=True)
    result_key = {"win": "wins", "loss": "losses", "draw": "draws"}.get(result)
    if result_key is None:
        raise ValueError("result must be 'win', 'loss', or 'draw'")

    _RESULTS[result_key] += 1
    for pattern in _GAME_PATTERNS:
        weight = _PATTERN_WEIGHTS.get(pattern, 1.0)
        if result == "loss":
            weight = min(4.0, weight * 1.15)
        elif result == "win":
            weight = max(0.25, weight * 0.98)
        _PATTERN_WEIGHTS[pattern] = round(weight, 4)

    if _CURRENT_OPENING_KEY is not None and _CURRENT_OPENING_ROLE == "propose":
        counts = _OPENING_RESULTS.setdefault(
            _CURRENT_OPENING_KEY,
            {"wins": 0, "losses": 0, "draws": 0},
        )
        counts[result_key] += 1
    elif (
        _CURRENT_OPENING_KEY is not None
        and _CURRENT_OPENING_ROLE == "respond"
        and _CURRENT_OPENING_ACTION is not None
    ):
        action_counts = _RESPONSE_RESULTS.setdefault(
            _CURRENT_OPENING_KEY,
            {},
        ).setdefault(
            _CURRENT_OPENING_ACTION,
            {"wins": 0, "losses": 0, "draws": 0},
        )
        action_counts[result_key] += 1
    _GAME_PATTERNS.clear()
    _EXPECTED_BOARD = None
    _CURRENT_OPENING_KEY = None
    _CURRENT_OPENING_ACTION = None
    _CURRENT_OPENING_ROLE = None
    _save_learning()


def _opponent(player: str) -> str:
    return "O" if player == "X" else "X"


def _candidate_moves(board: Board) -> list[Move]:
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
                r = row + row_offset
                c = col + col_offset
                if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == EMPTY:
                    candidates.add((r, c))
    return sorted(candidates)


def _would_win(board: Board, row: int, col: int, player: str) -> bool:
    for row_step, col_step in DIRECTIONS:
        count = 1
        for direction in (1, -1):
            r = row + row_step * direction
            c = col + col_step * direction
            while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == player:
                count += 1
                r += row_step * direction
                c += col_step * direction
        if count >= WIN_LENGTH:
            return True
    return False


def _position_hash(board: Board) -> int:
    key = 0
    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            symbol = board[row][col]
            if symbol in SYMBOLS:
                key ^= _ZOBRIST[row][col][SYMBOLS.index(symbol)]
    return key


def _open_three_directions(board: Board, row: int, col: int, player: str) -> int:
    open_threes = 0
    for row_step, col_step in DIRECTIONS:
        count = 1
        open_ends = 0
        for direction in (1, -1):
            r = row + row_step * direction
            c = col + col_step * direction
            while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == player:
                count += 1
                r += row_step * direction
                c += col_step * direction
            if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == EMPTY:
                open_ends += 1
        if count >= 3 and open_ends == 2:
            open_threes += 1
    return open_threes


def _winning_moves(
    board: Board,
    player: str,
    deadline: float | None = None,
    candidates: list[Move] | None = None,
) -> list[Move]:
    wins = []
    for row, col in _candidate_moves(board) if candidates is None else candidates:
        if deadline is not None and time.perf_counter() >= deadline:
            raise _SearchTimeout
        if _would_win(board, row, col, player):
            wins.append((row, col))
    return wins


def _threat_moves(
    board: Board,
    player: str,
    candidates: list[Move],
    deadline: float,
) -> tuple[list[Move], list[Move]]:
    """Find VCF continuations and VCT open-three or fork candidates."""
    forks = []
    forcing = []
    for row, col in candidates[:12]:
        if time.perf_counter() >= deadline:
            raise _SearchTimeout
        board[row][col] = player
        try:
            wins = _winning_moves(board, player, deadline)
            open_threes = _open_three_directions(board, row, col, player)
            if len(wins) >= 2:
                forks.append((row, col))
            elif wins or open_threes:
                forcing.append((row, col))
        finally:
            board[row][col] = EMPTY
    return forks, forcing


@lru_cache(maxsize=250_000)
def _direction_window_score(line: str) -> int:
    best = 0
    for start in range(1, WIN_LENGTH + 1):
        segment = line[start : start + WIN_LENGTH]
        if "o" in segment:
            continue
        open_ends = int(line[start - 1] == "_") + int(
            line[start + WIN_LENGTH] == "_"
        )
        line_score = _LINE_VALUES[segment.count("x")]
        if open_ends == 2:
            line_score *= 2
        elif open_ends == 0:
            line_score //= 2
        best = max(best, line_score)
    return best


def _window_score(board: Board, row: int, col: int, player: str) -> int:
    total = 0
    for row_step, col_step in DIRECTIONS:
        line = []
        for offset in range(-WIN_LENGTH, WIN_LENGTH + 1):
            r = row + offset * row_step
            c = col + offset * col_step
            if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
                line.append("o")
            elif offset == 0 or board[r][c] == player:
                line.append("x")
            elif board[r][c] == EMPTY:
                line.append("_")
            else:
                line.append("o")
        total += _direction_window_score("".join(line))
    return total


def _move_score(
    board: Board,
    row: int,
    col: int,
    player: str,
    learned_targets: dict[Move, int] | None = None,
) -> int:
    attack = _window_score(board, row, col, player)
    defense = _window_score(board, row, col, _opponent(player))
    center_bonus = max(0, 14 - abs(row - 7) - abs(col - 7))
    learned_bonus = 0 if learned_targets is None else learned_targets.get((row, col), 0)
    return attack + int(defense * 1.1) + center_bonus + learned_bonus


def _best_score(
    board: Board,
    player: str,
    candidates: list[Move] | None = None,
) -> int:
    moves = _candidate_moves(board) if candidates is None else candidates
    if not moves:
        return 0
    return max(_move_score(board, row, col, player) for row, col in moves)


def _ranked_moves(
    board: Board,
    player: str,
    limit: int,
    learned_targets: dict[Move, int] | None = None,
    candidates: list[Move] | None = None,
) -> list[Move]:
    moves = _candidate_moves(board) if candidates is None else candidates
    return sorted(
        moves,
        key=lambda move: (
            _move_score(board, move[0], move[1], player, learned_targets),
            -abs(move[0] - 7) - abs(move[1] - 7),
        ),
        reverse=True,
    )[:limit]


def _position_value(
    board: Board,
    player: str,
    learned_targets: dict[Move, int],
) -> int:
    moves = _candidate_moves(board)
    if not moves:
        return 0
    own_best = max(
        _window_score(board, row, col, player) + learned_targets.get((row, col), 0)
        for row, col in moves
    )
    other_best = max(
        _window_score(board, row, col, _opponent(player))
        for row, col in moves
    )
    return own_best - int(other_best * 1.05)


def _negamax(
    board: Board,
    player: str,
    depth: int,
    alpha: int,
    beta: int,
    deadline: float,
    learned_targets: dict[Move, int],
    position_hash: int,
    table: dict[int, TableEntry],
    ply: int = 0,
) -> int:
    if time.perf_counter() >= deadline:
        raise _SearchTimeout

    original_alpha = alpha
    original_beta = beta
    table_key = position_hash ^ _ZOBRIST_SIDE[player]
    cached = table.get(table_key)
    table_move = None
    if cached is not None:
        cached_depth, cached_value, bound, table_move = cached
        if cached_depth >= depth:
            if bound == 0:
                return cached_value
            if bound < 0:
                beta = min(beta, cached_value)
            else:
                alpha = max(alpha, cached_value)
            if alpha >= beta:
                return cached_value

    moves = _candidate_moves(board)
    if not moves:
        return 0

    own_wins = _winning_moves(board, player, deadline, moves)
    if own_wins:
        return _MATE_SCORE - ply

    opponent = _opponent(player)
    opponent_wins = _winning_moves(board, opponent, deadline, moves)
    if len(opponent_wins) > 1:
        return -_MATE_SCORE + ply + 1

    forced = bool(opponent_wins)
    if ply >= _MAX_PLY and not forced:
        return _position_value(board, player, learned_targets)
    if forced:
        ranked = opponent_wins
        next_depth = depth
    elif depth <= 0:
        ranked = _ranked_moves(
            board, player, _SEARCH_LIMIT, learned_targets, moves
        )
        forks, forcing = _threat_moves(board, player, ranked, deadline)
        if forks:
            return _MATE_SCORE - ply - 1
        if not forcing or ply >= 16:
            return _position_value(board, player, learned_targets)
        ranked = forcing
        next_depth = 0
    else:
        ranked = _ranked_moves(
            board, player, _SEARCH_LIMIT, learned_targets, moves
        )
        if table_move in ranked:
            ranked.remove(table_move)
            ranked.insert(0, table_move)
        next_depth = depth - 1
    if not ranked:
        return 0

    best = -_MATE_SCORE
    best_move = None
    for index, (row, col) in enumerate(ranked):
        if time.perf_counter() >= deadline:
            raise _SearchTimeout
        board[row][col] = player
        try:
            cell_index = SYMBOLS.index(player)
            next_hash = position_hash ^ _ZOBRIST[row][col][cell_index]
            if index == 0:
                value = -_negamax(
                    board, opponent, next_depth, -beta, -alpha,
                    deadline, learned_targets, next_hash, table, ply + 1,
                )
            else:
                reduction = int(index >= 3 and next_depth >= 2 and not forced)
                value = -_negamax(
                    board, opponent, next_depth - reduction, -alpha - 1, -alpha,
                    deadline, learned_targets, next_hash, table, ply + 1,
                )
                if reduction and value > alpha:
                    value = -_negamax(
                        board, opponent, next_depth, -alpha - 1, -alpha,
                        deadline, learned_targets, next_hash, table, ply + 1,
                    )
                if alpha < value < beta:
                    value = -_negamax(
                        board, opponent, next_depth, -beta, -alpha,
                        deadline, learned_targets, next_hash, table, ply + 1,
                    )
        finally:
            board[row][col] = EMPTY
        if value > best:
            best = value
            best_move = (row, col)
        alpha = max(alpha, value)
        if alpha >= beta:
            break

    if abs(best) < _MATE_SCORE - 1_000:
        bound = -1 if best <= original_alpha else 1 if best >= original_beta else 0
        if len(table) >= 50_000:
            table.clear()
        table[table_key] = (depth, best, bound, best_move)
    return best


def _search_root(
    board: Board,
    player: str,
    moves: list[Move],
    depth: int,
    deadline: float,
    learned_targets: dict[Move, int],
    position_hash: int,
    table: dict[int, TableEntry],
) -> tuple[Move, int]:
    best_move = moves[0]
    best_value = -_MATE_SCORE
    alpha = -_MATE_SCORE
    opponent = _opponent(player)
    for index, (row, col) in enumerate(moves):
        if time.perf_counter() >= deadline:
            raise _SearchTimeout
        board[row][col] = player
        try:
            cell_index = SYMBOLS.index(player)
            next_hash = position_hash ^ _ZOBRIST[row][col][cell_index]
            if index == 0:
                value = -_negamax(
                    board, opponent, depth - 1, -_MATE_SCORE, -alpha,
                    deadline, learned_targets, next_hash, table, 1,
                )
            else:
                value = -_negamax(
                    board, opponent, depth - 1, -alpha - 1, -alpha,
                    deadline, learned_targets, next_hash, table, 1,
                )
                if alpha < value < _MATE_SCORE:
                    value = -_negamax(
                        board, opponent, depth - 1, -_MATE_SCORE, -alpha,
                        deadline, learned_targets, next_hash, table, 1,
                    )
        finally:
            board[row][col] = EMPTY
        if value > best_value:
            best_value = value
            best_move = (row, col)
        alpha = max(alpha, value)
    return best_move, best_value


def _opening_search_value(board: Board, player: str, time_budget: float) -> int:
    deadline = time.perf_counter() + time_budget
    learned_targets = _learning_targets(board, player)
    ranked = _ranked_moves(board, player, _ROOT_LIMIT, learned_targets)
    if not ranked:
        return 0

    best_value = _position_value(board, player, learned_targets)
    position_hash = _position_hash(board)
    table: dict[int, TableEntry] = {}
    for depth in range(1, 21):
        try:
            best_move, best_value = _search_root(
                board,
                player,
                ranked,
                depth,
                deadline,
                learned_targets,
                position_hash,
                table,
            )
        except _SearchTimeout:
            break
        ranked.remove(best_move)
        ranked.insert(0, best_move)
        if abs(best_value) >= _MATE_SCORE - 1_000:
            break
    return best_value


def get_move(board: Board, player: str) -> Move:
    """Search tactics first, then use bounded iterative deepening for the best move."""
    global _EXPECTED_BOARD
    if player not in SYMBOLS:
        raise ValueError("player must be 'X' or 'O'")

    _load_learning(force=True)
    _record_opponent_move(board, player)
    moves = _candidate_moves(board)
    if not moves:
        raise ValueError("No free cells remain")

    winning = [move for move in moves if _would_win(board, move[0], move[1], player)]
    if winning:
        chosen = max(winning, key=lambda move: _move_score(board, *move, player))
    else:
        opponent_wins = [
            move for move in moves
            if _would_win(board, move[0], move[1], _opponent(player))
        ]
        if len(opponent_wins) == 1:
            chosen = opponent_wins[0]
        else:
            learned_targets = _learning_targets(board, player)
            ranked = _ranked_moves(board, player, _ROOT_LIMIT, learned_targets, moves)
            chosen = ranked[0]
            deadline = time.perf_counter() + _THINK_TIME
            position_hash = _position_hash(board)
            table: dict[int, TableEntry] = {}
            for depth in range(1, 21):
                try:
                    chosen, _ = _search_root(
                        board,
                        player,
                        ranked,
                        depth,
                        deadline,
                        learned_targets,
                        position_hash,
                        table,
                    )
                    ranked.remove(chosen)
                    ranked.insert(0, chosen)
                except _SearchTimeout:
                    break

    _EXPECTED_BOARD = [row[:] for row in board]
    _EXPECTED_BOARD[chosen[0]][chosen[1]] = player
    return chosen


def swap2_propose(board: Board) -> list[OpeningMove]:
    """Choose a balanced centrally located opening from a small opening book."""
    global _CURRENT_OPENING_ACTION, _CURRENT_OPENING_KEY, _CURRENT_OPENING_ROLE
    _load_learning(force=True)
    opening_book = (
        ((7, 7, "X"), (7, 8, "X"), (8, 7, "O")),
        ((7, 7, "X"), (8, 8, "X"), (7, 8, "O")),
        ((7, 7, "X"), (8, 7, "X"), (6, 8, "O")),
        ((7, 6, "X"), (7, 8, "X"), (8, 7, "O")),
        ((6, 6, "X"), (8, 8, "X"), (7, 7, "O")),
    )
    best_opening = None
    best_key = None
    best_value = None
    for opening in opening_book:
        candidate = [row[:] for row in board]
        if any(candidate[row][col] != EMPTY for row, col, _ in opening):
            continue
        for row, col, symbol in opening:
            candidate[row][col] = symbol
        search_value = _opening_search_value(candidate, "O", 0.10)
        opening_key = _opening_key(candidate)
        counts = _OPENING_RESULTS.get(opening_key)
        rate, games = _result_rate(counts) if counts else (0.5, 0)
        learned_adjustment = 300 * (rate - 0.5) if games >= 3 else 0
        value = (abs(search_value) - learned_adjustment,)
        if best_value is None or value < best_value:
            best_value = value
            best_opening = opening
            best_key = opening_key

    chosen = best_opening or opening_book[0]
    if best_key is None:
        candidate = [row[:] for row in board]
        for row, col, symbol in chosen:
            candidate[row][col] = symbol
        best_key = _opening_key(candidate)
    _CURRENT_OPENING_KEY = best_key
    _CURRENT_OPENING_ACTION = None
    _CURRENT_OPENING_ROLE = "propose"
    return list(chosen)


def _opening_balance(board: Board) -> int:
    candidates = _candidate_moves(board)
    if not candidates:
        return 0
    best = {
        player: max(
            _window_score(board, row, col, player)
            for row, col in candidates
        )
        for player in SYMBOLS
    }
    return best["O"] - best["X"]


def _opening_key(board: Board) -> str:
    center = BOARD_SIZE // 2
    transformed = []
    for transform in (
        lambda r, c: (r, c),
        lambda r, c: (r, -c),
        lambda r, c: (-r, c),
        lambda r, c: (-r, -c),
        lambda r, c: (c, r),
        lambda r, c: (c, -r),
        lambda r, c: (-c, r),
        lambda r, c: (-c, -r),
    ):
        parts = []
        for symbol in SYMBOLS:
            points = sorted(
                transform(row - center, col - center)
                for row in range(BOARD_SIZE)
                for col in range(BOARD_SIZE)
                if board[row][col] == symbol
            )
            parts.append(
                symbol + ":" + ";".join(f"{row},{col}" for row, col in points)
            )
        transformed.append("|".join(parts))
    return min(transformed)


def _result_rate(counts: dict[str, int]) -> tuple[float, int]:
    wins = counts.get("wins", 0)
    draws = counts.get("draws", 0)
    games = wins + counts.get("losses", 0) + draws
    return (wins + draws * 0.5 + 1) / (games + 2), games


def swap2_respond(board: Board) -> dict:
    """Choose a color, or add two stones when they substantially balance the opening."""
    global _CURRENT_OPENING_ACTION, _CURRENT_OPENING_KEY, _CURRENT_OPENING_ROLE
    _load_learning(force=True)
    opening_key = _opening_key(board)
    _CURRENT_OPENING_KEY = opening_key
    _CURRENT_OPENING_ROLE = "respond"

    balance = _opening_balance(board)
    search_value = _opening_search_value(board, "O", 0.68)
    take_action = {
        "action": "TAKE_O" if search_value >= 0 else "TAKE_X"
    }

    x_options = _ranked_moves(board, "X", 5)
    o_options = _ranked_moves(board, "O", 5)
    best_pair = None
    best_gap = abs(balance)

    for x_move in x_options:
        for o_move in o_options:
            if x_move == o_move:
                continue
            next_board = [row[:] for row in board]
            next_board[x_move[0]][x_move[1]] = "X"
            next_board[o_move[0]][o_move[1]] = "O"
            next_balance = _opening_balance(next_board)
            gap = abs(next_balance)
            if gap < best_gap:
                best_gap = gap
                best_pair = (x_move, o_move)

    action = take_action["action"]
    if best_pair is not None and abs(balance) >= 100 and best_gap <= abs(balance) * 0.6:
        action = "PLACE_TWO"

    action_results = _RESPONSE_RESULTS.get(opening_key, {})
    learned_actions = []
    for candidate_action, counts in action_results.items():
        rate, games = _result_rate(counts)
        if games >= 3 and (candidate_action != "PLACE_TWO" or best_pair is not None):
            learned_actions.append((rate, games, candidate_action))
    if learned_actions:
        learned_actions.sort(reverse=True)
        rate, _, learned_action = learned_actions[0]
        current_counts = action_results.get(action)
        current_rate = _result_rate(current_counts)[0] if current_counts else 0.5
        if rate >= 0.65 and rate > current_rate + 0.05:
            action = learned_action

    _CURRENT_OPENING_ACTION = action
    if action == "PLACE_TWO" and best_pair is not None:
        x_move, o_move = best_pair
        return {
            "action": "PLACE_TWO",
            "moves": [(x_move[0], x_move[1], "X"), (o_move[0], o_move[1], "O")],
        }
    return {"action": action}


def swap2_final_choice(board: Board) -> str:
    """Choose the color with the stronger estimated position."""
    _load_learning(force=True)
    return "O" if _opening_search_value(board, "O", 0.68) >= 0 else "X"