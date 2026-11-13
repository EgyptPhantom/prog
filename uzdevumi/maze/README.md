# Maze puzzles

This folder contains two text mazes and a small Python game for solving them.
In each maze, `#` marks a wall, spaces are walkable, `A` is the start, and `B`
is the goal.

## Files

| File | Description |
|---|---|
| `maze_15x25.txt` | 15-row, 25-column maze layout. |
| `maze_25x41.txt` | 25-row, 41-column maze layout. |
| `maze_15x25_solution.svg` | Graphic of the 15 x 25 maze with its 42-step shortest route highlighted. |
| `maze_game.py` | Tkinter maze game for the 15 x 25 maze; also accepts another maze text file as an argument. |
| `maze_game_25x41.py` | Tkinter game launcher for the larger maze; uses the shared game code in `maze_game.py`. |

## Run the games

Run these commands from this folder:

```bash
python maze_game.py
python maze_game_25x41.py
```

The games use the arrow keys or WASD to move, `H` to show or hide the
shortest-route hint, `U` to undo a move, and `R` to restart. Python's Tkinter
library is required.
