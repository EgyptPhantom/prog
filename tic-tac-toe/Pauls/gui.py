import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from game_engine import BOARD_SIZE, Match
from tournament import load_bots


COLORS = {
    "background": "#0A0F1D",
    "surface": "#121A2B",
    "surface_light": "#19243A",
    "surface_border": "#25324A",
    "text": "#F2F5FC",
    "muted": "#8996B0",
    "accent": "#8CF2D2",
    "accent_dark": "#173D3B",
    "blue": "#8DB8FF",
    "board": "#D9C49A",
    "board_line": "#8D7955",
    "board_label": "#806E4D",
    "stone_x": "#172033",
    "stone_o": "#F5F1E8",
}


class GameApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Pieci rindā | Swap2")
        self.root.geometry("1240x900")
        self.root.minsize(1040, 760)
        self.root.configure(bg=COLORS["background"])

        bots_pattern = str(Path(__file__).parent / "tic-tac-toe" / "*" / "bot.py")
        self.bots = load_bots(bots_pattern)
        self.match = None
        self.bot_pending = False
        self.bot_failed = False
        self.result_shown = False
        self.previous_board = None
        self.last_move = None
        self.hover_cell = None
        self.board_geometry = None

        self._build_layout()
        self._draw_board()

        if not self.bots:
            self.bot_select.configure(state="disabled")
            self.start_button.configure(state="disabled")
            messagebox.showerror("Nav pieejamu botu", "Mapē tic-tac-toe nav atrasts neviens derīgs bots.")

    def _build_layout(self):
        self.shell = tk.Frame(self.root, bg=COLORS["background"], padx=26, pady=20)
        self.shell.grid(row=0, column=0, sticky="nsew")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.shell.grid_rowconfigure(2, weight=1)
        self.shell.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_toolbar()
        self._build_content()
        self._build_footer()

    def _build_header(self):
        header = tk.Frame(self.shell, bg=COLORS["background"])
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header.grid_columnconfigure(1, weight=1)

        logo = tk.Label(
            header,
            text="5",
            font=("Segoe UI", 22, "bold"),
            width=2,
            height=1,
            bg=COLORS["accent"],
            fg=COLORS["background"],
        )
        logo.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 14))
        tk.Label(
            header,
            text="PIECI RINDĀ",
            font=("Segoe UI", 17, "bold"),
            bg=COLORS["background"],
            fg=COLORS["text"],
        ).grid(row=0, column=1, sticky="sw")
        tk.Label(
            header,
            text="STRATĒĢIJA · 15 × 15 · SWAP2",
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["background"],
            fg=COLORS["muted"],
        ).grid(row=1, column=1, sticky="nw", pady=(2, 0))
        tk.Label(
            header,
            text="DOMĀ DAŽUS GĀJIENUS UZ PRIEKŠU",
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["background"],
            fg=COLORS["muted"],
        ).grid(row=0, column=2, rowspan=2, sticky="e")

    def _build_toolbar(self):
        toolbar = tk.Frame(self.shell, bg=COLORS["surface"], padx=16, pady=12)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        toolbar.grid_columnconfigure(1, weight=1)

        self.bot_var = tk.StringVar(value=self.bots[0]["id"] if self.bots else "")
        self.first_var = tk.StringVar(value="human")

        tk.Label(
            toolbar,
            text="OPONENTS",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["surface"],
            fg=COLORS["muted"],
        ).grid(row=0, column=0, sticky="w", padx=(0, 9))
        self.bot_select = tk.OptionMenu(
            toolbar,
            self.bot_var,
            *[bot["id"] for bot in self.bots],
        )
        self.bot_select.configure(
            bg=COLORS["surface_light"],
            fg=COLORS["text"],
            activebackground=COLORS["surface_border"],
            activeforeground=COLORS["text"],
            highlightthickness=0,
            relief="flat",
            bd=0,
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=6,
            cursor="hand2",
        )
        self.bot_select["menu"].configure(
            bg=COLORS["surface_light"],
            fg=COLORS["text"],
            activebackground=COLORS["accent_dark"],
            activeforeground=COLORS["accent"],
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        self.bot_select.grid(row=0, column=1, sticky="w")

        tk.Label(
            toolbar,
            text="SĀKUMS",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["surface"],
            fg=COLORS["muted"],
        ).grid(row=0, column=2, sticky="e", padx=(12, 8))
        self.start_choice_frame = tk.Frame(toolbar, bg=COLORS["surface_light"], padx=3, pady=3)
        self.start_choice_frame.grid(row=0, column=3, sticky="e", padx=(0, 14))
        self.human_first_button = self._button(
            self.start_choice_frame,
            "Tu sāc",
            lambda: self._select_first("human"),
            "segmented",
        )
        self.human_first_button.pack(side="left")
        self.bot_first_button = self._button(
            self.start_choice_frame,
            "Bots sāk",
            lambda: self._select_first("bot"),
            "segmented",
        )
        self.bot_first_button.pack(side="left")

        self.start_button = self._button(toolbar, "SĀKT SPĒLI  →", self.start_match, "primary")
        self.start_button.grid(row=0, column=4, sticky="e")
        self._render_start_choice()

    def _build_content(self):
        content = tk.Frame(self.shell, bg=COLORS["background"])
        content.grid(row=2, column=0, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=0)

        self.board_panel = tk.Frame(content, bg=COLORS["surface"], padx=18, pady=16)
        self.board_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self.board_panel.grid_rowconfigure(1, weight=1)
        self.board_panel.grid_columnconfigure(0, weight=1)

        board_heading = tk.Frame(self.board_panel, bg=COLORS["surface"])
        board_heading.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(
            board_heading,
            text="SPĒLES LAUKUMS",
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["surface"],
            fg=COLORS["muted"],
        ).pack(side="left")
        self.board_badge = tk.Label(
            board_heading,
            text="GATAVS",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["accent_dark"],
            fg=COLORS["accent"],
            padx=9,
            pady=4,
        )
        self.board_badge.pack(side="right")

        self.board_canvas = tk.Canvas(
            self.board_panel,
            bg=COLORS["surface"],
            highlightthickness=0,
            cursor="crosshair",
        )
        self.board_canvas.grid(row=1, column=0, sticky="nsew")
        self.board_canvas.bind("<Configure>", self._on_board_resize)
        self.board_canvas.bind("<Button-1>", self._on_board_click)
        self.board_canvas.bind("<Motion>", self._on_board_motion)
        self.board_canvas.bind("<Leave>", self._on_board_leave)

        self._build_sidebar(content)

    def _build_sidebar(self, parent):
        self.sidebar = tk.Frame(parent, bg=COLORS["background"], width=292)
        self.sidebar.grid(row=0, column=1, sticky="nsew")
        self.sidebar.grid_propagate(False)

        self.status_card = tk.Frame(self.sidebar, bg=COLORS["surface"], padx=17, pady=16)
        self.status_card.pack(fill="x", pady=(0, 12))
        self.phase_badge = tk.Label(
            self.status_card,
            text="GAIDA",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["surface_light"],
            fg=COLORS["blue"],
            padx=9,
            pady=5,
        )
        self.phase_badge.pack(anchor="w")
        self.turn_label = tk.Label(
            self.status_card,
            text="Sāc jaunu spēli",
            font=("Segoe UI", 20, "bold"),
            bg=COLORS["surface"],
            fg=COLORS["text"],
            anchor="w",
            justify="left",
        )
        self.turn_label.pack(fill="x", pady=(13, 4))
        self.hint_label = tk.Label(
            self.status_card,
            text="Izvēlies botu un sāc spēli.",
            font=("Segoe UI", 10),
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=250,
        )
        self.hint_label.pack(fill="x")

        self.players_card = tk.Frame(self.sidebar, bg=COLORS["surface"], padx=17, pady=15)
        self.players_card.pack(fill="x", pady=(0, 12))
        tk.Label(
            self.players_card,
            text="SPĒLĒTĀJI",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["surface"],
            fg=COLORS["muted"],
        ).pack(anchor="w", pady=(0, 11))
        self.player_rows = {}
        for player_id in ("P1", "P2"):
            row = tk.Frame(self.players_card, bg=COLORS["surface"])
            row.pack(fill="x", pady=4)
            icon = tk.Label(
                row,
                text="·",
                width=3,
                font=("Segoe UI", 12, "bold"),
                bg=COLORS["surface_light"],
                fg=COLORS["muted"],
                padx=3,
                pady=4,
            )
            icon.pack(side="left", padx=(0, 9))
            details = tk.Frame(row, bg=COLORS["surface"])
            details.pack(side="left", fill="x", expand=True)
            name = tk.Label(
                details,
                text="1. spēlētājs",
                font=("Segoe UI", 10, "bold"),
                bg=COLORS["surface"],
                fg=COLORS["text"],
                anchor="w",
            )
            name.pack(anchor="w")
            role = tk.Label(
                details,
                text="krāsa pēc Swap2",
                font=("Segoe UI", 8),
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                anchor="w",
            )
            role.pack(anchor="w", pady=(2, 0))
            self.player_rows[player_id] = (icon, name, role)

        self.action_card = tk.Frame(self.sidebar, bg=COLORS["surface"], padx=17, pady=15)
        self.action_card.pack(fill="x")
        tk.Label(
            self.action_card,
            text="TAVA IZVĒLE",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["surface"],
            fg=COLORS["muted"],
        ).pack(anchor="w", pady=(0, 10))
        self.action_hint = tk.Label(
            self.action_card,
            text="Atklātnē vari izvēlēties krāsu vai nodot izvēli pretiniekam.",
            font=("Segoe UI", 9),
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            wraplength=250,
            justify="left",
            anchor="w",
        )
        self.action_hint.pack(fill="x", pady=(0, 10))

        self.action_area = tk.Frame(self.action_card, bg=COLORS["surface"])
        self.action_buttons = {}
        for action, text in (
            ("TAKE_X", "Spēlēt ar X"),
            ("TAKE_O", "Spēlēt ar O"),
            ("PLACE_TWO", "Novietot X + O"),
        ):
            button = self._button(
                self.action_area,
                text,
                lambda value=action: self.respond(value),
                "secondary",
            )
            button.pack(fill="x", pady=3)
            self.action_buttons[action] = button

        self.color_area = tk.Frame(self.action_card, bg=COLORS["surface"])
        self.color_buttons = {}
        for symbol in ("X", "O"):
            button = self._button(
                self.color_area,
                f"Turpināt ar {symbol}",
                lambda value=symbol: self.choose_color(value),
                "secondary",
            )
            button.pack(fill="x", pady=3)
            self.color_buttons[symbol] = button

    def _build_footer(self):
        footer = tk.Frame(self.shell, bg=COLORS["background"])
        footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        tk.Label(
            footer,
            text="15 × 15  ·  5 PĒC KĀRTAS UZVARAI  ·  PILNS LAUKUMS = NEIZŠĶIRTS",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["background"],
            fg=COLORS["muted"],
        ).pack(side="left")
        tk.Label(
            footer,
            text="SWAP2 ATKLĀTNE",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["background"],
            fg=COLORS["accent"],
        ).pack(side="right")

    def _button(self, parent, text, command, style):
        button = tk.Button(
            parent,
            text=text,
            command=command,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            bd=0,
            padx=12,
            pady=9,
            cursor="hand2",
            activebackground=COLORS["surface_border"],
            activeforeground=COLORS["text"],
        )
        self._style_button(button, style, enabled=True)
        return button

    def _style_button(self, button, style, enabled):
        if style == "primary":
            background, foreground = COLORS["accent"], COLORS["background"]
            disabled_background, disabled_foreground = COLORS["surface_light"], COLORS["muted"]
        elif style == "selected":
            background, foreground = COLORS["accent_dark"], COLORS["accent"]
            disabled_background, disabled_foreground = COLORS["accent_dark"], COLORS["accent"]
        elif style == "segmented":
            background, foreground = COLORS["surface_light"], COLORS["muted"]
            disabled_background, disabled_foreground = COLORS["surface_light"], COLORS["muted"]
        else:
            background, foreground = COLORS["surface_light"], COLORS["text"]
            disabled_background, disabled_foreground = COLORS["surface_light"], COLORS["muted"]

        button.configure(
            bg=background if enabled else disabled_background,
            fg=foreground if enabled else disabled_foreground,
            activebackground=background if enabled else disabled_background,
            activeforeground=foreground if enabled else disabled_foreground,
            disabledforeground=disabled_foreground,
            state="normal" if enabled else "disabled",
        )

    def _select_first(self, first):
        self.first_var.set(first)
        self._render_start_choice()

    def _render_start_choice(self):
        for value, button in (
            ("human", self.human_first_button),
            ("bot", self.bot_first_button),
        ):
            selected = self.first_var.get() == value
            self._style_button(button, "selected" if selected else "segmented", enabled=True)

    def start_match(self):
        if not self.bots:
            return
        bot_id = self.bot_var.get()
        bot = next((candidate for candidate in self.bots if candidate["id"] == bot_id), None)
        if bot is None:
            messagebox.showerror("Bots nav atrasts", "Izvēlētais bots vairs nav pieejams.")
            return
        self.match = Match(bot, human_first=self.first_var.get() == "human")
        self.bot_pending = False
        self.bot_failed = False
        self.result_shown = False
        self.previous_board = None
        self.last_move = None
        self.hover_cell = None
        self.refresh()

    def place(self, row, col):
        if self.match is None:
            return
        try:
            self.match.human_place(row, col)
        except ValueError as error:
            self.hint_label.configure(text=str(error), fg=COLORS["blue"])
            return
        self.refresh()

    def respond(self, action):
        if self.match is None:
            return
        try:
            self.match.human_respond(action)
        except ValueError as error:
            self.hint_label.configure(text=str(error), fg=COLORS["blue"])
            return
        self.refresh()

    def choose_color(self, symbol):
        if self.match is None:
            return
        try:
            self.match.human_choose_color(symbol)
        except ValueError as error:
            self.hint_label.configure(text=str(error), fg=COLORS["blue"])
            return
        self.refresh()

    def refresh(self):
        if self.match is None:
            return
        match = self.match
        board_snapshot = tuple(tuple(row) for row in match.board)
        if self.previous_board is not None:
            changes = [
                (row, col)
                for row in range(BOARD_SIZE)
                for col in range(BOARD_SIZE)
                if board_snapshot[row][col] != self.previous_board[row][col]
            ]
            if changes:
                self.last_move = changes[-1]
        self.previous_board = board_snapshot
        self._render_status(match)
        self._render_players(match)
        self._render_actions(match)
        self.board_badge.configure(
            text="SPĒLE BEIGUSIES" if match.phase == "finished" else
            "GAIDA BOTU" if match.current_actor == "bot" else "TAVA KĀRTA"
        )
        self._draw_board()

        if match.phase == "finished":
            if not self.result_shown:
                self.result_shown = True
            return
        if match.current_actor == "bot" and not self.bot_pending and not self.bot_failed:
            self.bot_pending = True
            self.root.after(100, self.perform_bot_action)

    def _render_status(self, match):
        if self.bot_failed:
            self.phase_badge.configure(text="BOTA KĻŪDA", fg="#FF9A9A")
            self.turn_label.configure(text="Gājiens apturēts", fg=COLORS["text"])
            return
        if match.phase == "finished":
            if match.result == "draw":
                self.phase_badge.configure(text="NEIZŠĶIRTS", fg=COLORS["accent"])
                self.turn_label.configure(text="Neizšķirts", fg=COLORS["accent"])
                self.hint_label.configure(text="Laukums pilns — nevienam neizdevās salikt piecas pēc kārtas.", fg=COLORS["muted"])
            else:
                winner = match.players[match.winner]["name"]
                self.phase_badge.configure(text="UZVARA", fg=COLORS["accent"])
                self.turn_label.configure(text=f"{winner} uzvar!", fg=COLORS["accent"])
                self.hint_label.configure(text="Piecas figūras pēc kārtas.", fg=COLORS["muted"])
            return

        actor = "Tavs" if match.current_actor == "human" else "Bota"
        if match.phase == "opening":
            phase, title = "SWAP2 · ATKLĀTNE", f"{actor} izvieto atklātni"
            hint = f"Izvēlies rūtiņu simbolam {match.expected_symbol}."
        elif match.phase == "response":
            phase, title = "SWAP2 · IZVĒLE", f"{actor} izvēlas"
            hint = "Paņem krāsu vai novieto vēl X un O."
        elif match.phase == "place_two":
            phase, title = "SWAP2 · PAPILDINĀJUMS", f"{actor} papildina"
            hint = f"Izvēlies rūtiņu simbolam {match.expected_symbol}."
        elif match.phase == "final_choice":
            phase, title = "SWAP2 · GALĪGĀ IZVĒLE", f"{actor} izvēlas krāsu"
            hint = "Ar šo simbolu turpināsi visu spēli."
        else:
            phase, title = "PAMATSPĒLE", f"{actor} gājiens"
            hint = f"Novieto {match.current_symbol}."
            if match.current_symbol == "O":
                hint += " Pamatspēli sāk O."
        self.phase_badge.configure(text=phase)
        self.turn_label.configure(text=title, fg=COLORS["text"])
        self.hint_label.configure(text=hint, fg=COLORS["muted"])

    def _render_players(self, match):
        for player_id, (icon, name, role) in self.player_rows.items():
            player = match.players[player_id]
            is_human = player["bot"] is None
            name.configure(text="Tu" if is_human else player["name"])
            if match.colors:
                symbol = next(symbol for symbol, owner in match.colors.items() if owner == player_id)
                role.configure(text=f"{player_id}  ·  {symbol}")
                icon.configure(text=symbol, fg=COLORS["accent"] if symbol == "X" else COLORS["blue"])
            else:
                role.configure(
                    text=f"{player_id}  ·  krāsa pēc Swap2",
                    fg=COLORS["muted"],
                )
                icon.configure(text=player_id[-1], fg=COLORS["muted"])

    def _render_actions(self, match):
        human_turn = match.current_actor == "human"
        show_response = match.phase == "response" and human_turn
        show_final_choice = match.phase == "final_choice" and human_turn
        if show_response:
            if not self.action_area.winfo_manager():
                self.action_area.pack(fill="x")
            if self.color_area.winfo_manager():
                self.color_area.pack_forget()
            self.action_hint.configure(text="Izvēlies krāsu vai nodod izvēli atpakaļ.")
        elif show_final_choice:
            if self.action_area.winfo_manager():
                self.action_area.pack_forget()
            if not self.color_area.winfo_manager():
                self.color_area.pack(fill="x")
            self.action_hint.configure(text="Izvēlies, ar kuru simbolu turpināsi.")
        else:
            if self.action_area.winfo_manager():
                self.action_area.pack_forget()
            if self.color_area.winfo_manager():
                self.color_area.pack_forget()
            if match.current_actor == "bot":
                self.action_hint.configure(text="Bots domā par nākamo gājienu.")
            else:
                self.action_hint.configure(text="Spied uz laukuma, lai novietotu figūru.")

    def _draw_board(self, width=None, height=None):
        if not hasattr(self, "board_canvas"):
            return
        canvas = self.board_canvas
        width = canvas.winfo_width() if width is None else width
        height = canvas.winfo_height() if height is None else height
        size = min(width, height) - 18
        if size < 50:
            return
        canvas.delete("all")

        left = (width - size) / 2
        top = (height - size) / 2
        padding = size * 0.095
        step = (size - 2 * padding) / (BOARD_SIZE - 1)
        first_x, first_y = left + padding, top + padding
        last_x = first_x + step * (BOARD_SIZE - 1)
        last_y = first_y + step * (BOARD_SIZE - 1)
        self.board_geometry = (first_x, first_y, step)

        self._round_rect(canvas, left + 2, top + 8, left + size + 2, top + size + 8, 24, "#070B14")
        self._round_rect(canvas, left, top, left + size, top + size, 24, COLORS["board"])

        for index in range(BOARD_SIZE):
            position = first_x + index * step
            canvas.create_line(position, first_y, position, last_y, fill=COLORS["board_line"], width=1)
            position_y = first_y + index * step
            canvas.create_line(first_x, position_y, last_x, position_y, fill=COLORS["board_line"], width=1)

        for row in (3, 7, 11):
            for col in (3, 7, 11):
                x = first_x + col * step
                y = first_y + row * step
                canvas.create_oval(x - 2.5, y - 2.5, x + 2.5, y + 2.5, fill=COLORS["board_line"], outline="")

        for index in range(BOARD_SIZE):
            canvas.create_text(
                first_x + index * step,
                first_y - padding * 0.48,
                text=chr(ord("A") + index),
                fill=COLORS["board_label"],
                font=("Segoe UI", 7, "bold"),
            )
            canvas.create_text(
                first_x - padding * 0.48,
                first_y + index * step,
                text=str(index + 1),
                fill=COLORS["board_label"],
                font=("Segoe UI", 7, "bold"),
            )

        if self.hover_cell is not None and self._can_place():
            row, col = self.hover_cell
            x = first_x + col * step
            y = first_y + row * step
            radius = step * 0.32
            canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                outline=COLORS["accent_dark"],
                width=2,
                dash=(3, 2),
            )

        if self.match is not None:
            for row in range(BOARD_SIZE):
                for col in range(BOARD_SIZE):
                    symbol = self.match.board[row][col]
                    if symbol != "_":
                        self._draw_piece(canvas, first_x + col * step, first_y + row * step, step, symbol, (row, col) == self.last_move)

    def _draw_piece(self, canvas, x, y, step, symbol, is_last):
        radius = step * 0.34
        canvas.create_oval(
            x - radius,
            y - radius + 2,
            x + radius,
            y + radius + 2,
            fill="#6F624A",
            outline="",
        )
        fill = COLORS["stone_x"] if symbol == "X" else COLORS["stone_o"]
        outline = "#32415D" if symbol == "X" else "#C6BDA9"
        canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            fill=fill,
            outline=COLORS["accent"] if is_last else outline,
            width=3 if is_last else 1,
        )
        canvas.create_text(
            x,
            y - 1,
            text=symbol,
            fill=COLORS["accent"] if symbol == "X" else "#29344A",
            font=("Segoe UI", max(9, int(step * 0.36)), "bold"),
        )

    def _round_rect(self, canvas, x1, y1, x2, y2, radius, fill):
        points = (
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        )
        canvas.create_polygon(points, smooth=True, splinesteps=18, fill=fill, outline="")

    def _cell_at(self, x, y):
        if self.board_geometry is None:
            return None
        first_x, first_y, step = self.board_geometry
        col = int((x - first_x) / step + 0.5)
        row = int((y - first_y) / step + 0.5)
        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            return None
        cell_x = first_x + col * step
        cell_y = first_y + row * step
        if abs(x - cell_x) > step * 0.48 or abs(y - cell_y) > step * 0.48:
            return None
        return row, col

    def _can_place(self):
        return (
            self.match is not None
            and self.match.current_actor == "human"
            and self.match.phase in ("opening", "place_two", "play")
        )

    def _on_board_click(self, event):
        if not self._can_place():
            return
        cell = self._cell_at(event.x, event.y)
        if cell is not None:
            self.place(*cell)

    def _on_board_motion(self, event):
        cell = self._cell_at(event.x, event.y) if self._can_place() else None
        if cell != self.hover_cell:
            self.hover_cell = cell
            self._draw_board()

    def _on_board_resize(self, event):
        self._draw_board(event.width, event.height)

    def _on_board_leave(self, event):
        if self.hover_cell is not None:
            self.hover_cell = None
            self._draw_board()
        event.widget.configure(cursor="arrow")

    def perform_bot_action(self):
        self.bot_pending = False
        if self.match is None or self.match.current_actor != "bot":
            return
        try:
            self.match.perform_bot_action()
        except Exception as error:
            self.bot_failed = True
            self.phase_badge.configure(text="BOTA KĻŪDA", fg="#FF9A9A")
            self.turn_label.configure(text="Gājiens apturēts", fg=COLORS["text"])
            self.hint_label.configure(text=str(error), fg="#FF9A9A")
            messagebox.showerror("Bota kļūda", str(error))
            return
        self.refresh()


def main():
    root = tk.Tk()
    GameApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
