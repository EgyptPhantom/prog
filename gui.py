"""Play Dive Grid against the bot. Run with python3 gui.py."""

import tkinter as tk

from dive_view import ArenaView
from main import BOARD_SIZE, check_winner, create_board
from studenti.nikita_kotovs.bot import (
    get_move,
    swap2_final_choice,
    swap2_propose,
    swap2_respond,
)


class Swap2Game:
    def __init__(self, human_starts, *, full_swap2=False):
        self.board = create_board()
        self.first, self.second = ("human", "bot") if human_starts else ("bot", "human")
        self.bot_takes_o = human_starts and not full_swap2
        self.actor = self.first
        self.phase = "opening"
        self.pending = list("XOX")
        self.colors = {}
        self.symbol = "O"
        self.last_move = None
        self.move_count = 0
        self.winner = None

    def _put(self, row, col, symbol):
        self.board[row][col] = symbol
        self.last_move = row, col
        self.move_count += 1

    def _finish_placement(self):
        if self.phase == "opening":
            self.phase, self.actor = "respond", self.second
            if self.bot_takes_o:
                self.choose("TAKE_O")
        else:
            self.phase, self.actor = "choose", self.first

    def place(self, row, col):
        if self.phase not in ("opening", "extra", "play"):
            return
        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            return
        if self.board[row][col] != "_":
            return

        if self.phase != "play":
            self._put(row, col, self.pending.pop(0))
            if not self.pending:
                self._finish_placement()
            return

        self._put(row, col, self.symbol)
        if check_winner(self.board, row, col, self.symbol):
            self.winner = self.actor
            self.phase = "finished"
        elif self.move_count == BOARD_SIZE * BOARD_SIZE:
            self.phase = "finished"
        else:
            self.symbol = "X" if self.symbol == "O" else "O"
            self.actor = self.colors[self.symbol]

    def choose(self, action):
        if self.phase not in ("respond", "choose"):
            return
        if action == "PLACE_TWO" and self.phase == "respond":
            self.phase = "extra"
            self.pending = list("XO")
        elif action in ("TAKE_X", "TAKE_O"):
            symbol = action[-1]
            other_symbol = "X" if symbol == "O" else "O"
            other_actor = self.first if self.actor == self.second else self.second
            self.colors = {symbol: self.actor, other_symbol: other_actor}
            self.phase, self.symbol, self.actor = "play", "O", self.colors["O"]

    def play_bot(self):
        if self.actor != "bot":
            return
        if self.phase == "opening":
            for row, col, symbol in swap2_propose(self.board):
                self._put(row, col, symbol)
            self.pending.clear()
            self._finish_placement()
        elif self.phase == "respond":
            response = swap2_respond(self.board)
            self.choose(response["action"])
            if self.phase == "extra":
                for row, col, symbol in response["moves"]:
                    self._put(row, col, symbol)
                self.pending.clear()
                self._finish_placement()
        elif self.phase == "choose":
            self.choose(f"TAKE_{swap2_final_choice(self.board)}")
        elif self.phase == "play":
            self.place(*get_move(self.board, self.symbol))

    def status_title(self):
        if self.phase == "opening":
            return "THE OPENING"
        if self.phase == "extra":
            return "PLACE TWO"
        if self.phase in ("respond", "choose"):
            return "PICK A SIDE" if self.actor == "human" else "BOT IS CHOOSING"
        turn = "YOUR TURN" if self.actor == "human" else "BOT'S TURN"
        return f"MOVE {self.move_count + 1}  /  {turn}"

    def hint(self):
        if self.phase == "finished":
            if self.winner == "human":
                return "Five in a row! The winning line is lit up."
            if self.winner == "bot":
                return "The bot made five in a row. Ready for a rematch?"
            return "The board is full. Neither side made five in a row."
        if self.phase == "opening":
            if self.actor == "bot":
                return "The bot opens with X, O, X. Then you choose a side."
            lead = f"Place {self.pending[0]} ({self.move_count + 1}/3)."
            if self.bot_takes_o:
                return f"{lead} You keep X. The bot plays O on move 4."
            return f"{lead} The bot chooses a side after the opening."
        if self.phase == "extra":
            return f"Place an extra {self.pending[0]} ({self.move_count - 2}/2), then the opener picks a side."
        if self.phase == "respond":
            if self.actor == "bot":
                return "The bot can take X, take O, or place two extra marks."
            return "Take X or O, or place two and let the bot choose. O plays next."
        if self.phase == "choose":
            return "Choose X or O. O plays next." if self.actor == "human" else "The bot picks a side. O plays next."
        if self.actor == "bot":
            return f"The bot is placing {self.symbol}. Get ready for your turn."
        return f"Place {self.symbol} on an empty tile. Make five in a row to win."


class GameWindow:
    def __init__(self, root):
        self.root = root
        self.job = None
        root.title("Dive Grid — Five in a Row")
        root.resizable(False, False)
        self.canvas = ArenaView(root, self.place, self.choose, self.restart)
        self.canvas.pack()
        self.restart(True)

    def restart(self, human_starts, *, full_swap2=False):
        if self.job is not None:
            self.root.after_cancel(self.job)
            self.job = None
        self.game = Swap2Game(human_starts, full_swap2=full_swap2)
        self.refresh(new_match=True)

    def place(self, row, col):
        if self.game.actor == "human":
            before = self.game.move_count
            self.game.place(row, col)
            if self.game.move_count != before:
                self.refresh()

    def choose(self, action):
        if self.game.actor == "human":
            before = self.game.phase
            self.game.choose(action)
            if self.game.phase != before:
                self.refresh()

    def _bot_turn(self):
        self.job = None
        self.game.play_bot()
        self.refresh()

    def refresh(self, *, new_match=False):
        self.canvas.show(self.game, new_match=new_match)
        if self.game.actor == "bot" and self.game.phase != "finished" and self.job is None:
            self.job = self.root.after(420, self._bot_turn)


if __name__ == "__main__":
    root = tk.Tk()
    GameWindow(root)
    root.mainloop()
