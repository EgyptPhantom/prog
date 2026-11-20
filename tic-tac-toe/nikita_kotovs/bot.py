"""15 × 15 piecu rindā bots ar Swap2 atklātni."""

from time import perf_counter


BOT_NAME: str = "Nikita Kotovs"

_SIZE = 15
_STRIDE = 16  # Katrā rindā ir viena tukša robežbīta vieta.
_DIRECTIONS = (1, _STRIDE, _STRIDE - 1, _STRIDE + 1)
_CELLS = tuple(1 << (r * _STRIDE + c) for r in range(_SIZE) for c in range(_SIZE))
_BOARD = sum(_CELLS)
_CENTER = 1 << (7 * _STRIDE + 7)
_WIN = 1_000_000
_THINK_TIME = 0.45
_LINE_VALUES = (0, 2, 12, 75, 700, 30_000)


def _prepare_geometry():
    """Katrai rūtiņai sagatavo piecu rūtiņu nogriežņus un atvērto trijnieku vietas."""
    lines = {cell: [] for cell in _CELLS}
    open_threes = {cell: [] for cell in _CELLS}
    center_value = {}
    for cell in _CELLS:
        row, col = _coord(cell)
        center_value[cell] = 14 - abs(row - 7) - abs(col - 7)
        for dr, dc in ((0, 1), (1, 0), (1, -1), (1, 1)):
            step = dr * _STRIDE + dc
            for length in (5, 6):
                end_r = row + (length - 1) * dr
                end_c = col + (length - 1) * dc
                if not (0 <= end_r < _SIZE and 0 <= end_c < _SIZE):
                    continue
                segment = [cell << (offset * step) for offset in range(length)]
                if length == 5:
                    mask = sum(segment)
                    for square in segment:
                        lines[square].append(mask ^ square)
                else:
                    inside = sum(segment[1:-1])
                    ends = segment[0] | segment[-1]
                    for square in segment[1:-1]:
                        open_threes[square].append((inside ^ square, ends))
    return lines, open_threes, center_value


def _coord(cell):
    return divmod(cell.bit_length() - 1, _STRIDE)


_LINES, _OPEN_THREES, _CENTRALITY = _prepare_geometry()


def _stones(board):
    x_stones = o_stones = 0
    for row, cells in enumerate(board):
        for col, symbol in enumerate(cells):
            if symbol == "X":
                x_stones |= 1 << (row * _STRIDE + col)
            elif symbol == "O":
                o_stones |= 1 << (row * _STRIDE + col)
    return x_stones, o_stones


def _bits(mask):
    while mask:
        cell = mask & -mask
        yield cell
        mask ^= cell


def _winning_cells(stones, empty):
    """Atrod piecu rūtiņu nogriežņus, kuros trūkst vienas figūras."""
    result = 0
    for step in _DIRECTIONS:
        a, b, c, d, e = (stones >> (i * step) for i in range(5))
        result |= b & c & d & e
        result |= (a & c & d & e) << step
        result |= (a & b & d & e) << (2 * step)
        result |= (a & b & c & e) << (3 * step)
        result |= (a & b & c & d) << (4 * step)
    return result & empty


def _nearby(occupied):
    adjacent = occupied
    for _ in range(2):
        horizontal = (adjacent | (adjacent << 1) | (adjacent >> 1)) & _BOARD
        adjacent = (horizontal | (horizontal << _STRIDE) | (horizontal >> _STRIDE)) & _BOARD
    return adjacent


def _rated_moves(own, enemy, candidates):
    occupied = own | enemy
    for cell in _bits(candidates):
        attack = defense = _CENTRALITY[cell]
        for line in _LINES[cell]:
            own_line, enemy_line = own & line, enemy & line
            if not enemy_line:
                attack += _LINE_VALUES[1 + own_line.bit_count()]
            if not own_line:
                defense += _LINE_VALUES[1 + enemy_line.bit_count()]
        for inside, ends in _OPEN_THREES[cell]:
            if occupied & ends:
                continue
            own_inside, enemy_inside = own & inside, enemy & inside
            if not enemy_inside and own_inside.bit_count() == 2:
                attack += 250
            if not own_inside and enemy_inside.bit_count() == 2:
                defense += 250
        yield attack, defense, cell


class _TimeLimit(Exception):
    pass


def _search(own, enemy, depth, alpha, beta, deadline, ply=0):
    if perf_counter() >= deadline:
        raise _TimeLimit

    occupied = own | enemy
    empty = _BOARD ^ occupied
    if not empty:
        return 0
    if _winning_cells(own, empty):
        return _WIN - ply
    blocks = _winning_cells(enemy, empty)
    if blocks.bit_count() > 1:
        return -_WIN + ply + 1
    if blocks:
        # Vienīgais legālais veids, kā saglabāt izredzes, ir bloķēt.
        return -_search(enemy, own | blocks, max(0, depth - 1), -beta, -alpha, deadline, ply + 1)

    candidates = (_nearby(occupied) & empty) or empty
    ratings = list(_rated_moves(own, enemy, candidates))
    if depth == 0:
        return 5 * max(attack for attack, _, _ in ratings) - 4 * max(
            defense for _, defense, _ in ratings
        )

    ratings.sort(key=lambda move: 3 * move[0] + 2 * move[1], reverse=True)
    best = -_WIN - 1
    for _, _, cell in ratings[:6]:
        score = -_search(enemy, own | cell, depth - 1, -beta, -alpha, deadline, ply + 1)
        best = max(best, score)
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def get_move(board: list[list[str]], player: str) -> tuple[int, int]:
    deadline = perf_counter() + _THINK_TIME
    x_stones, o_stones = _stones(board)
    own, enemy = (x_stones, o_stones) if player == "X" else (o_stones, x_stones)
    occupied = own | enemy
    empty = _BOARD ^ occupied
    if not empty:
        raise ValueError("Laukums ir pilns")
    if not occupied:
        return _coord(_CENTER)

    for stones in (own, enemy):
        wins = _winning_cells(stones, empty)
        if wins:
            return _coord(wins & -wins)

    candidates = (_nearby(occupied) & empty) or empty
    ratings = sorted(
        _rated_moves(own, enemy, candidates),
        key=lambda move: 3 * move[0] + 2 * move[1],
        reverse=True,
    )
    moves = [cell for _, _, cell in ratings[:10]]
    best = moves[0]
    for depth in range(1, 5):
        score = -_WIN - 1
        try:
            for cell in moves:
                value = -_search(enemy, own | cell, depth - 1, -_WIN - 1, -score, deadline, 1)
                if value > score:
                    score, next_best = value, cell
        except _TimeLimit:
            break
        best = next_best
        if abs(score) >= _WIN - 20:
            break
        moves.remove(best)
        moves.insert(0, best)
    return _coord(best)


def swap2_propose(board: list[list[str]]) -> list[tuple[int, int, str]]:
    return [(7, 7, "X"), (7, 8, "O"), (8, 9, "X")]


def _opening_value(x_stones, o_stones, deadline):
    # Abos Swap2 variantos pēc krāsu sadales nākamais spēlē O.
    return _search(o_stones, x_stones, 2, -_WIN - 1, _WIN + 1, deadline)


def swap2_respond(board: list[list[str]]) -> dict:
    deadline = perf_counter() + _THINK_TIME
    x_stones, o_stones = _stones(board)
    try:
        value = _opening_value(x_stones, o_stones, deadline)
    except _TimeLimit:
        return {"action": "TAKE_O"}
    take_color = {"action": "TAKE_O" if value >= 0 else "TAKE_X"}
    if abs(value) > 120:
        return take_color

    occupied = x_stones | o_stones
    candidates = _nearby(occupied) & (_BOARD ^ occupied)
    x_options = sorted(_rated_moves(x_stones, o_stones, candidates), reverse=True)[:4]
    o_options = sorted(_rated_moves(o_stones, x_stones, candidates), reverse=True)[:4]
    best_pair = None
    best_margin = abs(value)
    try:
        for _, _, x_cell in x_options:
            for _, _, o_cell in o_options:
                if x_cell == o_cell:
                    continue
                margin = abs(_opening_value(x_stones | x_cell, o_stones | o_cell, deadline))
                if margin < best_margin:
                    best_margin, best_pair = margin, (x_cell, o_cell)
    except _TimeLimit:
        pass
    if best_pair:
        x_cell, o_cell = best_pair
        return {"action": "PLACE_TWO", "moves": [(*_coord(x_cell), "X"), (*_coord(o_cell), "O")]}
    return take_color


def swap2_final_choice(board: list[list[str]]) -> str:
    deadline = perf_counter() + _THINK_TIME
    try:
        return "O" if _opening_value(*_stones(board), deadline) >= 0 else "X"
    except _TimeLimit:
        return "O"
