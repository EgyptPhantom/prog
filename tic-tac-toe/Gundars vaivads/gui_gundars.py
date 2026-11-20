"""Play 15x15 Gomoku against Knight_bot using the Swap2 opening."""

import copy
import time
import tkinter as tk

import Gundars as bot


BOARD_SIZE = 15
EMPTY = "_"
SYMBOLS = ("X", "O")
MOVE_TIMEOUT = 1.0
DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))

COLORS = {
    "background": "#0A0F1D",
    "panel": "#121A2B",
    "panel_light": "#19243A",
    "panel_border": "#25324A",
    "text": "#F2F5FC",
    "muted": "#8996B0",
    "accent": "#8CF2D2",
    "gold": "#F2C879",
    "board_edge": "#745D3E",
    "board_light": "#E5D2A9",
    "board_dark": "#DEC99E",
    "board_line": "#B39A6E",
    "x": "#172033",
    "x_light": "#34445F",
    "o": "#F5F1E8",
}


def create_board() -> list[list[str]]:
    return [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]


def winning_line(board: list[list[str]], row: int, col: int) -> list[tuple[int, int]] | None:
    symbol = board[row][col]
    if symbol not in SYMBOLS:
        return None
    for row_step, col_step in DIRECTIONS:
        line = [(row, col)]
        for direction in (1, -1):
            r = row + row_step * direction
            c = col + col_step * direction
            while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == symbol:
                line.append((r, c))
                r += row_step * direction
                c += col_step * direction
        if len(line) >= 5:
            return line
    return None


class Match:
    """Swap2 game state and bot interface validation, independent of Tkinter."""

    def __init__(self, human_first: bool = True):
        self.board = create_board()
        self.players = {
            "P1": "human" if human_first else "bot",
            "P2": "bot" if human_first else "human",
        }
        self.phase = "opening"
        self.opening_symbols = ("X", "X", "O")
        self.opening_index = 0
        self.extra_symbols = ("X", "O")
        self.extra_index = 0
        self.colors: dict[str, str] = {}
        self.current_symbol: str | None = None
        self.winner: str | None = None
        self.result: str | None = None
        self.last_move: tuple[int, int] | None = None
        self.winning_cells: list[tuple[int, int]] | None = None
        self.move_count = 0

    @property
    def current_actor(self) -> str | None:
        if self.phase == "opening":
            player_id = "P1"
        elif self.phase in ("response", "place_two"):
            player_id = "P2"
        elif self.phase == "final_choice":
            player_id = "P1"
        elif self.phase == "play":
            return self.players[self.colors[self.current_symbol]]
        else:
            return None
        return self.players[player_id]

    @property
    def expected_symbol(self) -> str | None:
        if self.phase == "opening":
            return self.opening_symbols[self.opening_index]
        if self.phase == "place_two":
            return self.extra_symbols[self.extra_index]
        if self.phase == "play":
            return self.current_symbol
        return None

    @property
    def expected_player_id(self) -> str | None:
        if self.phase in ("opening", "final_choice"):
            return "P1"
        if self.phase in ("response", "place_two"):
            return "P2"
        if self.phase == "play":
            return self.colors[self.current_symbol]
        return None

    def human_place(self, row: int, col: int) -> None:
        if self.current_actor != "human" or self.phase not in ("opening", "place_two", "play"):
            raise ValueError("This is not a human placement turn.")
        if type(row) is not int or type(col) is not int or not (
            0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE
        ):
            raise ValueError("Choose a cell on the board.")
        if self.board[row][col] != EMPTY:
            raise ValueError("That cell is already occupied.")

        symbol = self.expected_symbol
        self._place(row, col, symbol)
        if self.phase == "opening":
            self.opening_index += 1
            if self.opening_index == len(self.opening_symbols):
                self.phase = "response"
        elif self.phase == "place_two":
            self.extra_index += 1
            if self.extra_index == len(self.extra_symbols):
                self.phase = "final_choice"
        else:
            self._finish_turn(row, col, symbol)

    def human_respond(self, action: str) -> None:
        if self.current_actor != "human" or self.phase != "response":
            raise ValueError("It is not time to choose a Swap2 response.")
        if action not in ("TAKE_X", "TAKE_O", "PLACE_TWO"):
            raise ValueError("Choose TAKE_X, TAKE_O, or PLACE_TWO.")
        self._apply_response({"action": action})

    def human_choose_color(self, symbol: str) -> None:
        if self.current_actor != "human" or self.phase != "final_choice":
            raise ValueError("It is not time to choose a color.")
        self._apply_final_choice(symbol)

    def perform_bot_action(self) -> None:
        if self.current_actor != "bot":
            raise ValueError("It is not the bot's turn.")

        player_id = self.expected_player_id
        board_copy = copy.deepcopy(self.board)
        original_board = copy.deepcopy(board_copy)
        started = time.perf_counter()
        if self.phase == "opening":
            result = bot.swap2_propose(board_copy)
        elif self.phase == "response":
            result = bot.swap2_respond(board_copy)
        elif self.phase == "final_choice":
            result = bot.swap2_final_choice(board_copy)
        else:
            result = bot.get_move(board_copy, self.current_symbol)
        elapsed = time.perf_counter() - started

        if board_copy != original_board:
            raise ValueError(f"{bot.BOT_NAME} modified the board passed to it.")
        if elapsed > MOVE_TIMEOUT:
            raise TimeoutError(
                f"{bot.BOT_NAME} took {elapsed:.2f}s; the limit is {MOVE_TIMEOUT:.1f}s."
            )

        if self.phase == "opening":
            moves = self._validate_moves(result, self.opening_symbols)
            self._apply_moves(moves)
            self.phase = "response"
        elif self.phase == "response":
            if not isinstance(result, dict) or result.get("action") not in (
                "TAKE_X", "TAKE_O", "PLACE_TWO"
            ):
                raise ValueError(f"{bot.BOT_NAME} returned an invalid Swap2 response.")
            if result["action"] == "PLACE_TWO":
                moves = self._validate_moves(result.get("moves"), self.extra_symbols)
                self._apply_moves(moves)
                self.phase = "final_choice"
            else:
                self._apply_response(result)
        elif self.phase == "final_choice":
            self._apply_final_choice(result)
        else:
            row, col = self._validate_move(result)
            self._place(row, col, self.current_symbol)
            self._finish_turn(row, col, self.current_symbol)

    def _place(self, row: int, col: int, symbol: str) -> None:
        self.board[row][col] = symbol
        self.last_move = (row, col)
        self.move_count += 1

    def _validate_move(self, move) -> tuple[int, int]:
        if not isinstance(move, (tuple, list)) or len(move) != 2:
            raise ValueError(f"{bot.BOT_NAME} returned an invalid move format.")
        row, col = move
        if type(row) is not int or type(col) is not int or not (
            0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE
        ):
            raise ValueError(f"{bot.BOT_NAME} returned coordinates outside the board.")
        if self.board[row][col] != EMPTY:
            raise ValueError(f"{bot.BOT_NAME} selected an occupied cell.")
        return row, col

    def _validate_moves(self, moves, expected_symbols: tuple[str, ...]):
        if not isinstance(moves, (list, tuple)) or len(moves) != len(expected_symbols):
            raise ValueError(f"{bot.BOT_NAME} returned the wrong number of opening moves.")
        validated = []
        seen = set()
        symbols = []
        for move in moves:
            if not isinstance(move, (list, tuple)) or len(move) != 3:
                raise ValueError(f"{bot.BOT_NAME} returned an invalid opening move.")
            row, col, symbol = move
            if type(row) is not int or type(col) is not int or not (
                0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE
            ):
                raise ValueError(f"{bot.BOT_NAME} returned opening coordinates outside the board.")
            if (
                symbol not in SYMBOLS
                or self.board[row][col] != EMPTY
                or (row, col) in seen
            ):
                raise ValueError(f"{bot.BOT_NAME} returned an occupied or invalid opening cell.")
            seen.add((row, col))
            symbols.append(symbol)
            validated.append((row, col, symbol))
        symbols_match = (
            tuple(symbols) == expected_symbols
            if expected_symbols == self.extra_symbols
            else sorted(symbols) == sorted(expected_symbols)
        )
        if not symbols_match:
            raise ValueError(f"{bot.BOT_NAME} returned the wrong opening symbols.")
        return validated

    def _apply_moves(self, moves) -> None:
        for row, col, symbol in moves:
            self._place(row, col, symbol)

    def _apply_response(self, response: dict) -> None:
        action = response["action"]
        if action == "PLACE_TWO":
            self.phase = "place_two"
        elif action == "TAKE_O":
            self._set_colors({"X": "P1", "O": "P2"})
        elif action == "TAKE_X":
            self._set_colors({"X": "P2", "O": "P1"})
        else:
            raise ValueError("Choose TAKE_X, TAKE_O, or PLACE_TWO.")

    def _apply_final_choice(self, symbol: str) -> None:
        if symbol not in SYMBOLS:
            raise ValueError("Choose X or O.")
        other_symbol = "O" if symbol == "X" else "X"
        self._set_colors({symbol: "P1", other_symbol: "P2"})

    def _set_colors(self, colors: dict[str, str]) -> None:
        self.colors = colors
        self.current_symbol = "O"
        self.phase = "play"

    def _finish_turn(self, row: int, col: int, symbol: str) -> None:
        line = winning_line(self.board, row, col)
        if line:
            self.winner = self.colors[symbol]
            self.winning_cells = line
            self.result = "win"
            self.phase = "finished"
            bot.record_result(
                "win" if self.players[self.winner] == "bot" else "loss"
            )
        elif all(cell != EMPTY for board_row in self.board for cell in board_row):
            self.result = "draw"
            self.phase = "finished"
            bot.record_result("draw")
        else:
            self.current_symbol = "X" if symbol == "O" else "O"


class GameApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Five in a Row | Swap2 | Knight_bot")
        root.geometry("1000x820")
        root.minsize(850, 700)
        root.configure(bg=COLORS["background"])

        self.match: Match | None = None
        self.bot_pending = False
        self.bot_job = None
        self.bot_error: str | None = None
        self.board_geometry: tuple[float, float, float] | None = None
        self.hover_cell: tuple[int, int] | None = None
        self.human_first = True

        self._build_layout()
        self._draw_board()

    def _build_layout(self) -> None:
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        header = tk.Frame(self.root, bg=COLORS["background"], padx=22, pady=14)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        logo = tk.Canvas(
            header,
            width=44,
            height=44,
            bg=COLORS["background"],
            highlightthickness=0,
        )
        logo.create_oval(3, 3, 41, 41, fill=COLORS["accent"], outline="")
        logo.create_text(22, 21, text="5", fill=COLORS["background"],
                         font=("Segoe UI", 22, "bold"))
        logo.pack(side="left", padx=(0, 12))

        title_block = tk.Frame(header, bg=COLORS["background"])
        title_block.pack(side="left", fill="y")
        tk.Label(
            title_block,
            text="KNIGHT_BOT  /  ARENA",
            font=("Segoe UI", 16, "bold"),
            bg=COLORS["background"],
            fg=COLORS["text"],
        ).pack(anchor="w")
        tk.Label(
            title_block,
            text="GOMOKU  ·  15 × 15  ·  SWAP2",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["background"],
            fg=COLORS["muted"],
        ).pack(anchor="w", pady=(2, 0))
        self._button(
            header,
            "↻  RESET GAME",
            self.reset_match,
            accent=True,
        ).pack(side="right")

        content = tk.Frame(self.root, bg=COLORS["background"], padx=16, pady=8)
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        board_frame = tk.Frame(
            content,
            bg=COLORS["panel"],
            padx=12,
            pady=12,
            highlightthickness=1,
            highlightbackground=COLORS["panel_border"],
        )
        board_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        board_frame.grid_rowconfigure(0, weight=1)
        board_frame.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            board_frame,
            bg=COLORS["board_edge"],
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self._draw_board())
        self.canvas.bind("<Button-1>", self._on_board_click)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Leave>", self._on_mouse_leave)

        sidebar = tk.Frame(
            content,
            bg=COLORS["panel"],
            width=255,
            padx=16,
            pady=16,
            highlightthickness=1,
            highlightbackground=COLORS["panel_border"],
        )
        sidebar.grid(row=0, column=1, sticky="ns")
        sidebar.grid_propagate(False)

        tk.Label(
            sidebar,
            text="GAME STATUS",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["panel"],
            fg=COLORS["muted"],
        ).pack(anchor="w")
        self.status_label = tk.Label(
            sidebar,
            text="Choose who starts",
            font=("Segoe UI", 17, "bold"),
            bg=COLORS["panel"],
            fg=COLORS["text"],
            wraplength=220,
            justify="left",
            anchor="w",
        )
        self.status_label.pack(fill="x", pady=(8, 4))
        self.hint_label = tk.Label(
            sidebar,
            text="Swap2 opening: P1 places X, X, O. O takes the first regular turn.",
            font=("Segoe UI", 9),
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            wraplength=220,
            justify="left",
            anchor="w",
        )
        self.hint_label.pack(fill="x", pady=(0, 16))

        self.players_label = tk.Label(
            sidebar,
            text="You  ·  Knight_bot",
            font=("Segoe UI", 10, "bold"),
            bg=COLORS["panel_light"],
            fg=COLORS["text"],
            padx=10,
            pady=10,
            justify="left",
            anchor="w",
        )
        self.players_label.pack(fill="x", pady=(0, 16))

        score_card = tk.Frame(sidebar, bg=COLORS["panel_light"], padx=10, pady=9)
        score_card.pack(fill="x", pady=(0, 16))
        tk.Label(
            score_card,
            text="STONES ON BOARD",
            font=("Segoe UI", 7, "bold"),
            bg=COLORS["panel_light"],
            fg=COLORS["muted"],
        ).pack(anchor="w")
        score_row = tk.Frame(score_card, bg=COLORS["panel_light"])
        score_row.pack(fill="x", pady=(5, 0))
        self.x_count_label = tk.Label(
            score_row,
            text="X   0",
            font=("Segoe UI", 11, "bold"),
            bg=COLORS["panel_light"],
            fg=COLORS["accent"],
        )
        self.x_count_label.pack(side="left")
        self.o_count_label = tk.Label(
            score_row,
            text="O   0",
            font=("Segoe UI", 11, "bold"),
            bg=COLORS["panel_light"],
            fg=COLORS["text"],
        )
        self.o_count_label.pack(side="right")

        tk.Label(
            sidebar,
            text="START A GAME",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["panel"],
            fg=COLORS["muted"],
        ).pack(anchor="w", pady=(0, 6))
        self._button(sidebar, "You start", lambda: self.start_match(True)).pack(fill="x", pady=3)
        self._button(sidebar, "Knight_bot starts", lambda: self.start_match(False)).pack(fill="x", pady=3)

        self.actions_label = tk.Label(
            sidebar,
            text="Swap2 choice",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["panel"],
            fg=COLORS["muted"],
        )
        self.actions_label.pack(anchor="w", pady=(16, 6))
        self.action_area = tk.Frame(sidebar, bg=COLORS["panel"])
        self._button(
            self.action_area,
            "Take X",
            lambda: self._human_respond("TAKE_X"),
        ).pack(fill="x", pady=3)
        self._button(
            self.action_area,
            "Take O",
            lambda: self._human_respond("TAKE_O"),
        ).pack(fill="x", pady=3)
        self._button(
            self.action_area,
            "Place two stones",
            lambda: self._human_respond("PLACE_TWO"),
        ).pack(fill="x", pady=3)

        self.color_area = tk.Frame(sidebar, bg=COLORS["panel"])
        self._button(
            self.color_area,
            "Continue as X",
            lambda: self._human_choose("X"),
        ).pack(fill="x", pady=3)
        self._button(
            self.color_area,
            "Continue as O",
            lambda: self._human_choose("O"),
        ).pack(fill="x", pady=3)
        self.action_area.pack_forget()
        self.color_area.pack_forget()

        footer = tk.Label(
            self.root,
            text="Five or more in a row wins  ·  Full board with no winner is a draw",
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["background"],
            fg=COLORS["muted"],
            pady=8,
        )
        footer.grid(row=2, column=0, sticky="ew")

    @staticmethod
    def _button(parent, text: str, command, accent: bool = False):
        background = COLORS["accent"] if accent else COLORS["panel_light"]
        foreground = COLORS["background"] if accent else COLORS["text"]
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=("Segoe UI", 9, "bold"),
            bg=background,
            fg=foreground,
            activebackground=COLORS["accent"],
            activeforeground=COLORS["background"],
            relief="flat",
            bd=0,
            padx=10,
            pady=9,
            cursor="hand2",
        )

    def start_match(self, human_first: bool) -> None:
        if self.bot_job is not None:
            self.root.after_cancel(self.bot_job)
            self.bot_job = None
        self.match = Match(human_first)
        self.human_first = human_first
        self.bot_pending = False
        self.bot_error = None
        self.hover_cell = None
        self._refresh()

    def reset_match(self) -> None:
        self.start_match(self.human_first)

    def _human_respond(self, action: str) -> None:
        if self.match is None:
            return
        try:
            self.match.human_respond(action)
        except ValueError as error:
            self.hint_label.configure(text=str(error), fg=COLORS["accent"])
            return
        self._refresh()

    def _human_choose(self, symbol: str) -> None:
        if self.match is None:
            return
        try:
            self.match.human_choose_color(symbol)
        except ValueError as error:
            self.hint_label.configure(text=str(error), fg=COLORS["accent"])
            return
        self._refresh()

    def _on_board_click(self, event) -> None:
        if self.match is None or self.match.current_actor != "human":
            return
        if self.match.phase not in ("opening", "place_two", "play"):
            return
        cell = self._cell_at(event.x, event.y)
        if cell is None:
            return
        try:
            self.match.human_place(*cell)
        except ValueError as error:
            self.hint_label.configure(text=str(error), fg=COLORS["accent"])
            return
        self._refresh()

    def _refresh(self) -> None:
        match = self.match
        if match is None:
            return
        self._update_status()
        self._update_actions()
        self._draw_board()

        if (
            match.current_actor == "bot"
            and not self.bot_pending
            and self.bot_error is None
        ):
            self.bot_pending = True
            self.bot_job = self.root.after(100, self._perform_bot_action)

    def _update_status(self) -> None:
        match = self.match
        if match is None:
            return

        if self.bot_error:
            self.status_label.configure(text="Bot error", fg="#FF9A9A")
            self.hint_label.configure(text=self.bot_error, fg="#FF9A9A")
            return
        if match.phase == "finished":
            if match.result == "draw":
                self.status_label.configure(text="Draw", fg=COLORS["accent"])
                self.hint_label.configure(text="The board is full; neither player made five in a row.")
            else:
                winner_name = self._player_name(match.winner)
                self.status_label.configure(text=f"{winner_name} wins!", fg=COLORS["accent"])
                self.hint_label.configure(text="Five or more stones in a row.")
            return

        actor = "Your" if match.current_actor == "human" else "Knight_bot's"
        if match.phase == "opening":
            title = f"{actor} opening"
            hint = f"Place {match.expected_symbol}. Opening move {match.opening_index + 1} of 3."
        elif match.phase == "response":
            title = f"{actor} choice"
            hint = "Take X, take O, or place one extra X and one extra O."
        elif match.phase == "place_two":
            title = f"{actor} places two"
            hint = f"Place {match.expected_symbol}. Extra stone {match.extra_index + 1} of 2."
        elif match.phase == "final_choice":
            title = f"{actor} color choice"
            hint = "Choose X or O for the rest of the game."
        else:
            title = f"{actor} turn"
            hint = f"Place {match.current_symbol}. O plays first after Swap2."

        self.status_label.configure(text=title, fg=COLORS["text"])
        self.hint_label.configure(text=hint, fg=COLORS["muted"])

    def _update_actions(self) -> None:
        match = self.match
        if match is None:
            self.action_area.pack_forget()
            self.color_area.pack_forget()
            return
        x_count = sum(cell == "X" for row in match.board for cell in row)
        o_count = sum(cell == "O" for row in match.board for cell in row)
        self.x_count_label.configure(text=f"X   {x_count:03}")
        self.o_count_label.configure(text=f"O   {o_count:03}")

        if match.phase == "response" and match.current_actor == "human":
            self.color_area.pack_forget()
            self.action_area.pack(fill="x")
        elif match.phase == "final_choice" and match.current_actor == "human":
            self.action_area.pack_forget()
            self.color_area.pack(fill="x")
        else:
            self.action_area.pack_forget()
            self.color_area.pack_forget()

        if match.colors:
            x_owner = self._player_name(match.colors["X"])
            o_owner = self._player_name(match.colors["O"])
            self.players_label.configure(text=f"X  ·  {x_owner}\nO  ·  {o_owner}")
        else:
            p1 = self._player_name("P1")
            p2 = self._player_name("P2")
            self.players_label.configure(text=f"P1  ·  {p1}\nP2  ·  {p2}")

    def _perform_bot_action(self) -> None:
        self.bot_job = None
        self.bot_pending = False
        if self.match is None or self.match.current_actor != "bot":
            return
        try:
            self.match.perform_bot_action()
        except Exception as error:
            self.bot_error = f"{type(error).__name__}: {error}"
        self._refresh()

    def _player_name(self, player_id: str | None) -> str:
        if self.match is None or player_id is None:
            return "—"
        return "You" if self.match.players[player_id] == "human" else bot.BOT_NAME

    def _draw_board(self) -> None:
        canvas = self.canvas
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        size = min(width, height) - 64
        if size < 80:
            return
        canvas.delete("all")

        left = (width - size) / 2
        top = (height - size) / 2
        padding = size * 0.055
        step = (size - 2 * padding) / BOARD_SIZE
        first_x = left + padding
        first_y = top + padding
        self.board_geometry = (first_x, first_y, step)

        board_right = first_x + step * BOARD_SIZE
        board_bottom = first_y + step * BOARD_SIZE
        canvas.create_rectangle(
            first_x - 12,
            first_y - 12,
            board_right + 12,
            board_bottom + 12,
            fill="#342A1F",
            outline="#927650",
            width=2,
        )
        canvas.create_rectangle(
            first_x - 7,
            first_y - 7,
            board_right + 7,
            board_bottom + 7,
            fill=COLORS["board_edge"],
            outline="#C3A979",
            width=1,
        )

        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                x1 = first_x + col * step
                y1 = first_y + row * step
                x2 = x1 + step
                y2 = y1 + step
                fill = COLORS["board_light"] if (row + col) % 2 == 0 else COLORS["board_dark"]
                canvas.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=fill,
                    outline=COLORS["board_line"],
                    width=1,
                )
                canvas.create_line(
                    x1 + 2,
                    y1 + 2,
                    x2 - 2,
                    y1 + 2,
                    fill="#F0E2C3",
                    width=1,
                )

        for index in range(BOARD_SIZE):
            center_x = first_x + (index + 0.5) * step
            center_y = first_y + (index + 0.5) * step
            canvas.create_text(
                center_x,
                first_y - padding * 0.52,
                text=f"{index:02}",
                fill=COLORS["gold"],
                font=("Segoe UI", 7, "bold"),
            )
            canvas.create_text(
                first_x - padding * 0.52,
                center_y,
                text=f"{index:02}",
                fill=COLORS["gold"],
                font=("Segoe UI", 7, "bold"),
            )

        if (
            self.hover_cell is not None
            and self.match is not None
            and self.match.current_actor == "human"
            and self.match.phase in ("opening", "place_two", "play")
        ):
            row, col = self.hover_cell
            x1 = first_x + col * step
            y1 = first_y + row * step
            if self.match.board[row][col] == EMPTY:
                preview = self.match.expected_symbol
                canvas.create_text(
                    x1 + step / 2,
                    y1 + step / 2,
                    text=preview,
                    fill="#70857F",
                    font=("Segoe UI", max(10, int(step * 0.42)), "bold"),
                )
            canvas.create_rectangle(
                x1 + 3,
                y1 + 3,
                x1 + step - 3,
                y1 + step - 3,
                outline=COLORS["accent"],
                width=2,
            )

        if self.match is None:
            return
        winning_cells = set(self.match.winning_cells or ())
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                symbol = self.match.board[row][col]
                if symbol == EMPTY:
                    continue
                x = first_x + (col + 0.5) * step
                y = first_y + (row + 0.5) * step
                radius = step * 0.35
                is_last = (row, col) == self.match.last_move
                is_winner = (row, col) in winning_cells
                rim = COLORS["x_light"] if symbol == "X" else "#C6BDA9"
                fill = COLORS["x"] if symbol == "X" else COLORS["o"]

                canvas.create_oval(
                    x - radius,
                    y - radius + 3,
                    x + radius,
                    y + radius + 3,
                    fill="#5D4C32",
                    outline="",
                )
                if is_last or is_winner:
                    glow = COLORS["accent"] if is_winner else COLORS["gold"]
                    canvas.create_oval(
                        x - radius - 4,
                        y - radius - 4,
                        x + radius + 4,
                        y + radius + 4,
                        fill=glow,
                        outline="",
                    )
                canvas.create_oval(
                    x - radius,
                    y - radius,
                    x + radius,
                    y + radius,
                    fill=fill,
                    outline=rim,
                    width=2,
                )
                canvas.create_oval(
                    x - radius * 0.74,
                    y - radius * 0.74,
                    x + radius * 0.74,
                    y + radius * 0.74,
                    fill=COLORS["x_light"] if symbol == "X" else "#FBF8EF",
                    outline="",
                )
                canvas.create_text(
                    x,
                    y,
                    text=symbol,
                    fill=COLORS["accent"] if symbol == "X" else "#29344A",
                    font=("Segoe UI", max(10, int(step * 0.42)), "bold"),
                )

    def _cell_at(self, x: int, y: int) -> tuple[int, int] | None:
        if self.board_geometry is None:
            return None
        first_x, first_y, step = self.board_geometry
        if not (
            first_x <= x < first_x + step * BOARD_SIZE
            and first_y <= y < first_y + step * BOARD_SIZE
        ):
            return None
        col = int((x - first_x) / step)
        row = int((y - first_y) / step)
        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            return None
        return row, col

    def _on_mouse_move(self, event) -> None:
        self.hover_cell = self._cell_at(event.x, event.y)
        self._draw_board()

    def _on_mouse_leave(self, _event) -> None:
        self.hover_cell = None
        self._draw_board()


def main() -> None:
    root = tk.Tk()
    GameApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()