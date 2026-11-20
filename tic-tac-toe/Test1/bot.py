BOT_NAME = "GreedyAI 1"

BOARD_SIZE = 15


def _winning_moves(board, player):
    opponent = "O" if player == "X" else "X"
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


def _line_score(board, r, c, player):
    opponent = "O" if player == "X" else "X"
    score = 0
    directions = ((1, 0), (0, 1), (1, 1), (1, -1))

    for dr, dc in directions:
        own = 1
        enemy = 0
        open_ends = 0

        rr, cc = r + dr, c + dc
        if 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE:
            if board[rr][cc] == player:
                own += 1
                rr += dr
                cc += dc
                while 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and board[rr][cc] == player:
                    own += 1
                    rr += dr
                    cc += dc
            if 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and board[rr][cc] == "_":
                open_ends += 1

        rr, cc = r - dr, c - dc
        if 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE:
            if board[rr][cc] == player:
                own += 1
                rr -= dr
                cc -= dc
                while 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and board[rr][cc] == player:
                    own += 1
                    rr -= dr
                    cc -= dc
            if 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and board[rr][cc] == "_":
                open_ends += 1

        rr, cc = r + dr, c + dc
        while 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and board[rr][cc] == opponent:
            enemy += 1
            rr += dr
            cc += dc
        rr, cc = r - dr, c - dc
        while 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and board[rr][cc] == opponent:
            enemy += 1
            rr -= dr
            cc -= dc

        if own >= 2:
            score += (own ** 4) + open_ends * 20
        if enemy:
            score += (enemy ** 4) // 2

    distance = abs(r - 7) + abs(c - 7)
    return score + max(0, 15 - distance)


def get_move(board, player):
    winning = _winning_moves(board, player)
    if winning:
        return winning[0]

    opponent = "O" if player == "X" else "X"
    opponent_wins = _winning_moves(board, opponent)
    if opponent_wins:
        return opponent_wins[0]

    best_move = None
    best_score = -1
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if board[r][c] != "_":
                continue
            score = _line_score(board, r, c, player)
            if score > best_score:
                best_score = score
                best_move = (r, c)

    return best_move if best_move is not None else (7, 7)


def swap2_propose(board):
    return [(7, 7, "X"), (7, 8, "X"), (8, 7, "O")]


def swap2_respond(board):
    x_positions = [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE) if board[r][c] == "X"]
    o_positions = [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE) if board[r][c] == "O"]

    x_near_center = sum(abs(r - 7) + abs(c - 7) for r, c in x_positions)
    o_near_center = sum(abs(r - 7) + abs(c - 7) for r, c in o_positions)
    if x_near_center <= o_near_center:
        return {"action": "TAKE_X"}
    return {"action": "TAKE_O"}


def swap2_final_choice(board):
    x_count = sum(cell == "X" for row in board for cell in row)
    o_count = sum(cell == "O" for row in board for cell in row)
    return "X" if x_count >= o_count else "O"
