BOT_NAME = "GreedyAI 2"

BOARD_SIZE = 15


def _is_winner(board, last_r, last_c, player):
    directions = ((1, 0), (0, 1), (1, 1), (1, -1))
    for dr, dc in directions:
        count = 1
        r, c = last_r + dr, last_c + dc
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == player:
            count += 1
            r += dr
            c += dc
        r, c = last_r - dr, last_c - dc
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == player:
            count += 1
            r -= dr
            c -= dc
        if count >= 5:
            return True
    return False


def _winning_moves(board, player):
    moves = []
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if board[r][c] != "_":
                continue
            board[r][c] = player
            if _is_winner(board, r, c, player):
                moves.append((r, c))
            board[r][c] = "_"
    return moves


def _direction_score(board, r, c, player):
    opponent = "O" if player == "X" else "X"
    total = 0
    directions = ((1, 0), (0, 1), (1, 1), (1, -1))

    for dr, dc in directions:
        for symbol, multiplier in ((player, 1), (opponent, 1)):
            own = 1 if symbol == player else 0
            enemy = 1 if symbol == opponent else 0

            rr, cc = r + dr, c + dc
            forward = 0
            while 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and board[rr][cc] == symbol:
                forward += 1
                rr += dr
                cc += dc
            rr, cc = r - dr, c - dc
            backward = 0
            while 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and board[rr][cc] == symbol:
                backward += 1
                rr -= dr
                cc -= dc

            length = forward + backward
            if symbol == player:
                own += length
                if own >= 2:
                    total += own ** 5
            elif enemy:
                total += (length + 1) ** 4

    distance = abs(r - 7) + abs(c - 7)
    return total + max(0, 20 - distance)


def get_move(board, player):
    opponent = "O" if player == "X" else "X"

    winning = _winning_moves(board, player)
    if winning:
        return winning[0]

    opponent_wins = _winning_moves(board, opponent)
    if opponent_wins:
        return opponent_wins[0]

    best_move = None
    best_score = -1
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if board[r][c] != "_":
                continue
            score = _direction_score(board, r, c, player)
            if score > best_score:
                best_score = score
                best_move = (r, c)

    return best_move if best_move is not None else (7, 7)


def swap2_propose(board):
    return [(7, 6, "X"), (7, 7, "X"), (8, 7, "O")]


def swap2_respond(board):
    x_count = sum(cell == "X" for row in board for cell in row)
    o_count = sum(cell == "O" for row in board for cell in row)

    if x_count >= o_count:
        return {"action": "TAKE_O"}
    return {"action": "TAKE_X"}


def swap2_final_choice(board):
    x_count = sum(cell == "X" for row in board for cell in row)
    o_count = sum(cell == "O" for row in board for cell in row)
    return "O" if o_count >= x_count else "X"
