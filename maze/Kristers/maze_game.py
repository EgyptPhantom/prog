"""Glowbug: a neon maze-chase game that uses the mazes in this folder.

You play a firefly. Collect sparks to charge the exit portal, grab lanterns to
scare the shades (then catch them for points), and fly through the portal to
finish the level.

Levels:
    1. maze_15x25.txt
    2. maze_25x41.txt
    3. A big maze that the game generates (51 x 101 tiles)

Setup and run (from the repository root):
    python3 -m venv .venv
    .venv/bin/pip install pygame-ce
    .venv/bin/python uzdevumi/maze/maze_game.py

pygame-ce is a drop-in replacement for pygame (it still uses "import pygame")
and, unlike pygame, has ready-made packages for the newest Python versions.

Controls:
    Arrow keys or WASD   move
    P                    pause
    Esc                  back to the title screen (quit from the title screen)
    1, 2, 3              on the title screen, jump straight to a level
"""
import math
import os
import random
from collections import deque

import pygame

HERE = os.path.dirname(os.path.abspath(__file__))

TILE = 32
VIEW_W, VIEW_H = 1024, 704
HUD_H = 64
SCREEN_W, SCREEN_H = VIEW_W, VIEW_H + HUD_H
FPS = 60

PLAYER_SPEED = 7.0  # tiles per second
FRIGHT_TIME = 7.0
INVULN_TIME = 2.0
START_LIVES = 3
MAX_LIVES = 5

BG = (7, 6, 18)
TEXT = (236, 236, 255)
DIM = (130, 130, 175)
SPARK = (255, 224, 130)
BUG = (190, 255, 110)
LANTERN = (255, 160, 60)
PORTAL = (110, 220, 255)
DANGER = (255, 80, 110)

UP, DOWN, LEFT, RIGHT = (0, -1), (0, 1), (-1, 0), (1, 0)
DIRECTIONS = (UP, LEFT, DOWN, RIGHT)
STOP = (0, 0)
ANGLES = {RIGHT: 0, UP: 90, LEFT: 180, DOWN: 270}
KEYS = {
    pygame.K_UP: UP, pygame.K_w: UP,
    pygame.K_DOWN: DOWN, pygame.K_s: DOWN,
    pygame.K_LEFT: LEFT, pygame.K_a: LEFT,
    pygame.K_RIGHT: RIGHT, pygame.K_d: RIGHT,
}

# "goal" is the share of sparks you need before the exit portal opens.
LEVELS = [
    {"name": "First steps", "file": "maze_15x25.txt", "shades": ["hunter"],
     "shade_speed": 4.4, "goal": 1.0, "lanterns": 2},
    {"name": "The long hall", "file": "maze_25x41.txt", "shades": ["hunter", "wanderer", "ambusher"],
     "shade_speed": 4.9, "goal": 0.8, "lanterns": 3},
    {"name": "The labyrinth", "size": (51, 101), "shades": ["hunter", "ambusher", "wanderer"] * 3,
     "shade_speed": 5.3, "goal": 0.45, "lanterns": 10},
]

# Personality: (body color, eye color, how far away it can sense you, in tiles).
SHADE_STYLES = {
    "hunter": ((70, 14, 40), (255, 60, 80), 14),
    "ambusher": ((48, 20, 80), (210, 90, 255), 12),
    "wanderer": ((20, 50, 50), (90, 255, 190), 6),
}
SCARED_BODY = (40, 60, 120)


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def opposite(d):
    return (-d[0], -d[1])


def scale_color(color, k):
    return tuple(max(0, min(255, int(c * k))) for c in color)


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def center_of(tile):
    return (tile[0] * TILE + TILE / 2, tile[1] * TILE + TILE / 2)


# --- Mazes -------------------------------------------------------------------

def load_maze(path):
    """Read the maze rows from a file, stopping at the first blank line."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if line and set(line) <= set("# AB"):
                rows.append(line)
            elif rows:
                break
    width = max(len(r) for r in rows)
    return [r.ljust(width, "#") for r in rows]


def generate_maze(rows, cols, seed=7, loops=0.08):
    """Carve a maze with a depth-first search, then open some walls to add loops."""
    rng = random.Random(seed)
    grid = [["#"] * cols for _ in range(rows)]
    grid[1][1] = " "
    stack = [(1, 1)]
    while stack:
        x, y = stack[-1]
        options = [(x + dx, y + dy, dx, dy) for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2))
                   if 0 < x + dx < cols - 1 and 0 < y + dy < rows - 1 and grid[y + dy][x + dx] == "#"]
        if options:
            nx, ny, dx, dy = rng.choice(options)
            grid[y + dy // 2][x + dx // 2] = " "
            grid[ny][nx] = " "
            stack.append((nx, ny))
        else:
            stack.pop()
    # A maze with no loops is a trap in a chase game, so knock out a few walls.
    for y in range(1, rows - 1):
        for x in range(1, cols - 1):
            if grid[y][x] != "#" or rng.random() > loops:
                continue
            horizontal = x % 2 == 0 and y % 2 == 1 and grid[y][x - 1] == " " and grid[y][x + 1] == " "
            vertical = x % 2 == 1 and y % 2 == 0 and grid[y - 1][x] == " " and grid[y + 1][x] == " "
            if horizontal or vertical:
                grid[y][x] = " "
    grid[1][1] = "A"
    grid[rows - 2][cols - 2] = "B"
    return ["".join(r) for r in grid]


class Level:
    def __init__(self, number):
        cfg = LEVELS[number]
        self.number = number
        self.cfg = cfg
        rows = load_maze(os.path.join(HERE, cfg["file"])) if "file" in cfg else generate_maze(*cfg["size"])
        self.h, self.w = len(rows), len(rows[0])
        self.walls = set()
        self.start = self.exit = None
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch == "#":
                    self.walls.add((x, y))
                elif ch == "A":
                    self.start = (x, y)
                elif ch == "B":
                    self.exit = (x, y)

        from_start = self.distances(self.start)
        far = max(from_start.values())
        rng = random.Random(number * 1000 + len(self.walls))
        reachable = [t for t in from_start if t not in (self.start, self.exit)]

        # Lanterns go in dead ends, which are the places you most need an escape.
        dead_ends = [t for t in reachable if from_start[t] > 6 and len(self.neighbors(t)) == 1]
        pool = dead_ends if len(dead_ends) >= cfg["lanterns"] else reachable
        self.lanterns = set(rng.sample(pool, min(cfg["lanterns"], len(pool))))
        self.sparks = set(reachable) - self.lanterns
        self.total_sparks = len(self.sparks)
        self.sparks_needed = math.ceil(self.total_sparks * cfg["goal"])

        spawn_pool = [t for t in reachable if from_start[t] >= max(8, far * 0.4)]
        self.shade_homes = rng.sample(spawn_pool, min(len(cfg["shades"]), len(spawn_pool)))
        self.phase = {t: rng.uniform(0, math.tau) for t in reachable}

        self.wall_surface = render_walls(self)
        big = self.w * TILE > VIEW_W or self.h * TILE > VIEW_H
        self.minimap = render_minimap(self) if big else None

    def walkable(self, t):
        return 0 <= t[0] < self.w and 0 <= t[1] < self.h and t not in self.walls

    def neighbors(self, t):
        return [add(t, d) for d in DIRECTIONS if self.walkable(add(t, d))]

    def distances(self, origin):
        """Breadth-first search: number of steps from origin to every reachable tile."""
        dist = {origin: 0}
        queue = deque([origin])
        while queue:
            t = queue.popleft()
            for n in self.neighbors(t):
                if n not in dist:
                    dist[n] = dist[t] + 1
                    queue.append(n)
        return dist


# --- Pre-rendered graphics ---------------------------------------------------

def render_walls(level):
    """Draw every wall once as glowing neon tubes, so each frame is a single blit."""
    surf = pygame.Surface((level.w * TILE, level.h * TILE), pygame.SRCALPHA)
    layers = [(0.48, (30, 36, 120, 110)), (0.34, (55, 75, 210, 255)),
              (0.2, (100, 135, 255, 255)), (0.07, (210, 225, 255, 255))]
    for frac, color in layers:
        r = max(1, int(TILE * frac))
        for x, y in level.walls:
            cx, cy = x * TILE + TILE // 2, y * TILE + TILE // 2
            pygame.draw.circle(surf, color, (cx, cy), r)
            if (x + 1, y) in level.walls:
                pygame.draw.rect(surf, color, (cx, cy - r, TILE, 2 * r))
            if (x, y + 1) in level.walls:
                pygame.draw.rect(surf, color, (cx - r, cy, 2 * r, TILE))
    return surf


def render_minimap(level):
    small = pygame.Surface((level.w, level.h), pygame.SRCALPHA)
    small.fill((10, 10, 30, 210))
    for t in level.walls:
        small.set_at(t, (80, 100, 230, 235))
    k = min(220 / level.w, 130 / level.h)
    return pygame.transform.scale(small, (int(level.w * k), int(level.h * k)))


def make_vignette(w, h):
    small = pygame.Surface((64, 44), pygame.SRCALPHA)
    for y in range(44):
        for x in range(64):
            dx, dy = (x + 0.5) / 32 - 1, (y + 0.5) / 22 - 1
            d = math.hypot(dx, dy) / math.sqrt(2)
            small.set_at((x, y), (0, 0, 0, int(210 * max(0.0, (d - 0.4) / 0.6) ** 1.5)))
    return pygame.transform.smoothscale(small, (w, h))


_glows = {}


def draw_glow(surf, pos, radius, color, strength=1.0):
    """Add a soft round light to the surface (additive blending, cached per size)."""
    level = round(strength * 8)
    if level <= 0:
        return
    radius = max(2, int(radius))
    key = (radius, color, min(level, 8))
    g = _glows.get(key)
    if g is None:
        g = pygame.Surface((radius * 2, radius * 2))
        peak = scale_color(color, min(level, 8) / 8)
        for r in range(radius, 0, -1):
            pygame.draw.circle(g, scale_color(peak, (1 - r / radius) ** 2), (radius, radius), r)
        _glows[key] = g
    surf.blit(g, (int(pos[0]) - radius, int(pos[1]) - radius), special_flags=pygame.BLEND_RGB_ADD)


def make_font(size):
    for name in ("avenirnext", "avenir", "helveticaneue", "segoeui", "arial"):
        path = pygame.font.match_font(name, bold=True)
        if path:
            try:
                return pygame.font.Font(path, size)
            except (OSError, RuntimeError):
                pass
    return pygame.font.Font(None, size)


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "drag", "gravity")

    def __init__(self, x, y, vx, vy, life, color, size, drag=0.9, gravity=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.color, self.size, self.drag, self.gravity = color, size, drag, gravity

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        k = self.drag ** (dt * 60)
        self.vx *= k
        self.vy = self.vy * k + self.gravity * dt
        self.life -= dt
        return self.life > 0


def draw_particles(surf, particles, ox=0.0, oy=0.0):
    for p in particles:
        k = p.life / p.max_life
        x, y = p.x + ox, p.y + oy
        draw_glow(surf, (x, y), p.size * 3 * k + 2, p.color, 0.6 * k)
        pygame.draw.circle(surf, scale_color(p.color, 0.5 + 0.5 * k), (int(x), int(y)), max(1, int(p.size * k)))


def burst(particles, x, y, color, count, speed, life=0.7, size=3.0, gravity=0.0):
    for _ in range(count):
        a = random.uniform(0, math.tau)
        v = random.uniform(0.3, 1.0) * speed * 60
        particles.append(Particle(x, y, math.cos(a) * v, math.sin(a) * v,
                                  random.uniform(0.5, 1.0) * life, color, random.uniform(0.6, 1.0) * size,
                                  gravity=gravity))


# --- Characters --------------------------------------------------------------

class Mover:
    """Something that moves from tile to tile. pos interpolates for smooth motion."""

    def __init__(self, tile, speed):
        self.speed = speed
        self.reset(tile)

    def reset(self, tile):
        self.tile = tile
        self.dir = STOP
        self.prog = 0.0

    @property
    def pos(self):
        return (self.tile[0] + self.dir[0] * self.prog, self.tile[1] + self.dir[1] * self.prog)

    def reverse(self):
        if self.dir != STOP:
            self.tile = add(self.tile, self.dir)
            self.dir = opposite(self.dir)
            self.prog = 1.0 - self.prog


class Bug(Mover):
    def __init__(self, tile):
        super().__init__(tile, PLAYER_SPEED)
        self.angle = 0.0

    def reset(self, tile):
        super().reset(tile)
        self.want = STOP

    def update(self, dt, level, arrived):
        if self.want != STOP and self.dir != STOP and self.want == opposite(self.dir):
            self.reverse()
        if self.dir == STOP:
            if self.want == STOP or not level.walkable(add(self.tile, self.want)):
                return
            self.dir = self.want
        self.prog += self.speed * dt
        while self.prog >= 1.0:
            self.prog -= 1.0
            self.tile = add(self.tile, self.dir)
            arrived(self.tile)
            # The last key you pressed is remembered, so you can turn early.
            if self.want != STOP and level.walkable(add(self.tile, self.want)):
                self.dir = self.want
            elif not level.walkable(add(self.tile, self.dir)):
                self.dir, self.prog = STOP, 0.0
                break

    def turn(self, dt):
        if self.dir != STOP:
            diff = (ANGLES[self.dir] - self.angle + 180) % 360 - 180
            self.angle += diff * min(1.0, dt * 14)


class Shade(Mover):
    def __init__(self, home, kind, speed, seed):
        super().__init__(home, speed)
        self.home, self.kind = home, kind
        self.body, self.eye, self.sight = SHADE_STYLES[kind]
        self.rng = random.Random(seed)
        self.spin = self.rng.uniform(0, math.tau)
        self.respawn(fade_in=False)

    def respawn(self, fade_in=True):
        self.reset(self.home)
        self.state = "spawning" if fade_in else "normal"
        self.timer = 1.0 if fade_in else 0.0
        self.scared = False

    def update(self, dt, game):
        if self.state == "gone":
            self.timer -= dt
            if self.timer <= 0:
                self.respawn()
            return
        if self.state == "spawning":
            self.timer -= dt
            if self.timer <= 0:
                self.state = "normal"
        if self.dir == STOP:
            self.choose(game)
            if self.dir == STOP:
                return
        self.prog += self.speed * (0.55 if self.scared else 1.0) * dt
        while self.prog >= 1.0:
            self.prog -= 1.0
            self.tile = add(self.tile, self.dir)
            self.choose(game)
            if self.dir == STOP:
                self.prog = 0.0
                break

    def choose(self, game):
        level = game.level
        options = [d for d in DIRECTIONS if level.walkable(add(self.tile, d))]
        if not options:
            self.dir = STOP
            return
        ahead = [d for d in options if d != opposite(self.dir)] or options
        field = game.player_field
        if self.scared:
            self.dir = max(ahead, key=lambda d: field.get(add(self.tile, d), 0) + self.rng.random() * 2)
            return
        if field.get(self.tile, 9999) <= self.sight and self.rng.random() > 0.08:
            # The ambusher aims a few tiles ahead of you instead of at you.
            target = game.field_to(game.ambush_tile()) if self.kind == "ambusher" else field
            if field.get(self.tile, 9999) <= 3:
                target = field
            self.dir = min(options, key=lambda d: target.get(add(self.tile, d), 9999))
            return
        self.dir = self.rng.choice(ahead)


# --- The game ----------------------------------------------------------------

class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Glowbug")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.view = self.screen.subsurface((0, HUD_H, VIEW_W, VIEW_H))
        self.clock = pygame.time.Clock()
        self.fonts = {size: make_font(size) for size in (16, 20, 28, 40, 64, 96)}
        self.text_cache = {}
        self.vignette = make_vignette(VIEW_W, VIEW_H)
        self.shade_overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self.stars = [(random.uniform(0, SCREEN_W), random.uniform(0, SCREEN_H),
                       random.uniform(0.6, 1.8), random.uniform(0, math.tau)) for _ in range(170)]
        self.t = 0.0
        self.particles = []
        self.ui_particles = []
        self.texts = []
        self.level = None
        self.shake = 0.0
        self.fade = 1.0
        self.running = True
        self.set_state("title")

    # --- State changes ---

    def set_state(self, name, fade=True):
        self.state = name
        self.state_time = 0.0
        if fade:
            self.fade = 1.0
        if name == "title":
            self.ui_particles.clear()

    def new_game(self, number):
        self.score = 0
        self.lives = START_LIVES
        self.start_level(number)

    def start_level(self, number):
        self.level = Level(number)
        cfg = LEVELS[number]
        self.collected = 0
        self.level_time = 0.0
        self.bug = Bug(self.level.start)
        self.shades = [Shade(home, kind, cfg["shade_speed"], seed=number * 10 + i)
                       for i, (home, kind) in enumerate(zip(self.level.shade_homes, cfg["shades"]))]
        self.particles.clear()
        self.texts.clear()
        self.reset_positions()
        self.invuln = 0.0
        self.cam = self.camera_target()
        self.intro_len = 2.4
        self.set_state("intro")

    def reset_positions(self):
        self.bug.reset(self.level.start)
        self.bug.angle = 0.0
        for s in self.shades:
            s.respawn(fade_in=False)
        self.fright_timer = 0.0
        self.chain = 0
        self.locked_hint = 0.0
        self.refresh_field()

    def refresh_field(self):
        self.field_tile = self.bug.tile
        self.player_field = self.level.distances(self.bug.tile)
        self.field_cache = {}

    def field_to(self, tile):
        if tile not in self.field_cache:
            self.field_cache[tile] = self.level.distances(tile)
        return self.field_cache[tile]

    def ambush_tile(self):
        tile = self.bug.tile
        facing = self.bug.dir if self.bug.dir != STOP else self.bug.want
        for _ in range(4):
            if facing == STOP or not self.level.walkable(add(tile, facing)):
                break
            tile = add(tile, facing)
        return tile

    def exit_open(self):
        return self.collected >= self.level.sparks_needed

    def finish_level(self):
        lvl = self.level
        self.report = [("Exit bonus", 1000)]
        if not lvl.sparks:
            self.report.append(("Every spark collected", 2000))
        self.score += sum(points for _, points in self.report)
        self.got_life = self.lives < MAX_LIVES
        if self.got_life:
            self.lives += 1
        self.set_state("level_done", fade=False)

    def next_level(self):
        if self.level.number + 1 < len(LEVELS):
            self.start_level(self.level.number + 1)
        else:
            self.set_state("victory")

    def lose_life(self):
        self.lives -= 1
        x, y = center_of(self.bug.pos)
        burst(self.particles, x, y, BUG, 60, 5, life=1.2, size=4)
        burst(self.particles, x, y, (255, 255, 255), 20, 3, life=0.6)
        self.shake = 0.5
        self.set_state("dying", fade=False)

    # --- Input ---

    def handle(self, event):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type != pygame.KEYDOWN:
            return
        key = event.key
        if self.state == "title":
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self.new_game(0)
            elif key in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.new_game(key - pygame.K_1)
            elif key == pygame.K_ESCAPE:
                self.running = False
            return
        if key == pygame.K_ESCAPE:
            self.set_state("title")
        elif key == pygame.K_p and self.state in ("play", "paused"):
            self.set_state("paused" if self.state == "play" else "play", fade=False)
        elif key in KEYS and self.state in ("play", "intro"):
            self.bug.want = KEYS[key]
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.state == "level_done" and self.state_time > 0.6:
                self.next_level()
            elif self.state in ("game_over", "victory") and self.state_time > 1.0:
                self.set_state("title")

    # --- Update ---

    def update(self, dt):
        self.t += dt
        self.state_time += dt
        self.fade = max(0.0, self.fade - dt * 2.5)
        if self.state == "paused":
            return
        self.shake = max(0.0, self.shake - dt)
        self.particles = [p for p in self.particles if p.update(dt)]
        self.ui_particles = [p for p in self.ui_particles if p.update(dt)]
        for text in self.texts:
            text["y"] -= 28 * dt
            text["life"] -= dt
        self.texts = [t for t in self.texts if t["life"] > 0]

        if self.state == "intro":
            self.update_camera(dt)
            if self.state_time > self.intro_len:
                self.set_state("play", fade=False)
        elif self.state == "play":
            self.update_play(dt)
        elif self.state == "dying":
            self.update_camera(dt)
            if self.state_time > 1.8:
                if self.lives > 0:
                    self.reset_positions()
                    self.invuln = INVULN_TIME
                    self.intro_len = 1.2
                    self.set_state("intro", fade=False)
                else:
                    self.set_state("game_over")
        elif self.state == "exiting":
            self.portal_swirl(0.9)
            if self.state_time > 1.4:
                self.finish_level()
        elif self.state == "victory" and random.random() < dt * 3:
            color = random.choice((SPARK, BUG, PORTAL, LANTERN, (255, 120, 200)))
            burst(self.ui_particles, random.uniform(150, SCREEN_W - 150), random.uniform(120, 420),
                  color, 50, 5, life=1.6, size=3.5, gravity=90)
        elif self.state == "title":
            self.update_title_bug()

    def update_play(self, dt):
        self.level_time += dt
        self.invuln = max(0.0, self.invuln - dt)
        self.locked_hint = max(0.0, self.locked_hint - dt)
        if self.fright_timer > 0:
            self.fright_timer -= dt
            if self.fright_timer <= 0:
                for s in self.shades:
                    s.scared = False

        self.bug.update(dt, self.level, self.on_arrive)
        if self.state != "play":  # flew into the exit
            self.bug.dir, self.bug.prog = STOP, 0.0
            return
        self.bug.turn(dt)
        if self.bug.tile != self.field_tile:
            self.refresh_field()

        for s in self.shades:
            s.update(dt, self)
        self.check_collisions()
        self.update_camera(dt)

        if self.bug.dir != STOP and random.random() < 0.7:
            x, y = center_of(self.bug.pos)
            dx, dy = self.bug.dir
            self.particles.append(Particle(x - dx * 10 + random.uniform(-3, 3), y - dy * 10 + random.uniform(-3, 3),
                                           random.uniform(-15, 15), random.uniform(-15, 15),
                                           0.45, BUG, 2.2))
        if self.exit_open():
            self.portal_swirl(0.35)

    def portal_swirl(self, chance):
        if random.random() < chance:
            cx, cy = center_of(self.level.exit)
            a = random.uniform(0, math.tau)
            r = random.uniform(28, 40)
            self.particles.append(Particle(cx + math.cos(a) * r, cy + math.sin(a) * r,
                                           -math.cos(a) * 55 - math.sin(a) * 45, -math.sin(a) * 55 + math.cos(a) * 45,
                                           0.6, PORTAL, 2.0, drag=0.98))

    def on_arrive(self, tile):
        lvl = self.level
        x, y = center_of(tile)
        if tile in lvl.sparks:
            lvl.sparks.remove(tile)
            self.collected += 1
            self.score += 10
            burst(self.particles, x, y, SPARK, 5, 1.6, life=0.4, size=2)
            if self.collected == lvl.sparks_needed:
                self.float_text("The exit is open!", lvl.exit, PORTAL, 28)
                ex, ey = center_of(lvl.exit)
                burst(self.particles, ex, ey, PORTAL, 50, 4, life=1.0)
        elif tile in lvl.lanterns:
            lvl.lanterns.remove(tile)
            self.score += 50
            self.fright_timer = FRIGHT_TIME
            self.chain = 0
            for s in self.shades:
                if s.state != "gone":
                    s.scared = True
                    s.reverse()
            burst(self.particles, x, y, LANTERN, 40, 5, life=0.9, size=3.5)
            self.float_text("Shades are scared!", tile, LANTERN, 20)
            self.shake = 0.15
        if tile == lvl.exit:
            if self.exit_open():
                self.set_state("exiting", fade=False)
            elif self.locked_hint <= 0:
                left = lvl.sparks_needed - self.collected
                self.float_text("Collect {} more spark{}".format(left, "" if left == 1 else "s"), tile, DIM, 20)
                self.locked_hint = 2.5

    def check_collisions(self):
        bx, by = self.bug.pos
        for s in self.shades:
            if s.state != "normal":
                continue
            sx, sy = s.pos
            if math.hypot(sx - bx, sy - by) > 0.7:
                continue
            if s.scared:
                self.chain += 1
                points = 200 * 2 ** (self.chain - 1)
                self.score += points
                s.state, s.timer, s.scared = "gone", 4.0, False
                x, y = center_of((sx, sy))
                burst(self.particles, x, y, s.eye, 35, 4, life=0.8)
                self.float_text("+{}".format(points), (sx, sy), TEXT, 28)
            elif self.invuln <= 0:
                self.lose_life()
                return

    def float_text(self, text, tile, color, size):
        x, y = center_of(tile)
        surf = self.fonts[size].render(text, True, color)
        self.texts.append({"surf": surf, "x": x, "y": y - 18, "life": 1.6, "max": 1.6})

    def camera_target(self):
        bx, by = center_of(self.bug.pos)

        def axis(center, size, view):
            if size <= view:
                return (size - view) / 2
            return max(0.0, min(size - view, center - view / 2))

        return [axis(bx, self.level.w * TILE, VIEW_W), axis(by, self.level.h * TILE, VIEW_H)]

    def update_camera(self, dt):
        tx, ty = self.camera_target()
        k = min(1.0, dt * 6)
        self.cam[0] += (tx - self.cam[0]) * k
        self.cam[1] += (ty - self.cam[1]) * k

    def title_bug_pos(self, t):
        return (SCREEN_W / 2 + math.sin(t * 0.8) * 330, 400 + math.sin(t * 1.6) * 55)

    def update_title_bug(self):
        x, y = self.title_bug_pos(self.t)
        if random.random() < 0.8:
            self.ui_particles.append(Particle(x + random.uniform(-4, 4), y + random.uniform(-4, 4),
                                              random.uniform(-20, 20), random.uniform(-20, 20), 0.7, BUG, 2.5))

    # --- Drawing helpers ---

    def text(self, surf, text, size, color, pos, anchor="topleft", glow=False):
        key = (text, size, color, glow)
        rendered = self.text_cache.get(key)
        if rendered is None:
            base = self.fonts[size].render(text, True, color)
            if glow:
                # Blur a padded copy by shrinking and growing it, fade it, then put the sharp text on top.
                w, h = base.get_size()
                pad = size // 2
                full = (w + pad * 2, h + pad * 2)
                rendered = pygame.Surface(full, pygame.SRCALPHA)
                rendered.blit(base, (pad, pad))
                for shrink in (3, 3):
                    tiny = pygame.transform.smoothscale(rendered, (max(1, full[0] // shrink), max(1, full[1] // shrink)))
                    rendered = pygame.transform.smoothscale(tiny, full)
                rendered.fill((255, 255, 255, 120), special_flags=pygame.BLEND_RGBA_MULT)
                rendered.blit(base, (pad, pad))
            else:
                rendered = base
            if len(self.text_cache) > 400:
                self.text_cache.clear()
            self.text_cache[key] = rendered
        rect = rendered.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
        surf.blit(rendered, rect)

    def draw_stars(self, surf, cam_x, cam_y, w, h):
        for sx, sy, size, ph in self.stars:
            x = (sx - cam_x * 0.25 * size) % w
            y = (sy - cam_y * 0.25 * size) % h
            k = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(self.t * 1.5 + ph))
            pygame.draw.circle(surf, scale_color((90, 90, 150), k), (int(x), int(y)), max(1, int(size * 0.8)))

    def draw_bug(self, surf, cx, cy, angle, scale=1.0, alpha=255):
        draw_glow(surf, (cx, cy), 46 * scale, BUG, 0.55 * (alpha / 255))
        c = 28
        img = pygame.Surface((56, 56), pygame.SRCALPHA)
        flap = math.sin(self.t * 32)
        for side in (-1, 1):
            wy = c + side * (7 + 3 * flap)
            pygame.draw.ellipse(img, (200, 235, 255, 120), (c - 13, wy - 5, 18, 10))
            pygame.draw.ellipse(img, (235, 248, 255, 200), (c - 13, wy - 5, 18, 10), 1)
        pulse = 0.5 + 0.5 * math.sin(self.t * 5)
        pygame.draw.ellipse(img, mix(BUG, (255, 255, 200), pulse * 0.6), (c - 18, c - 7, 21, 14))
        pygame.draw.ellipse(img, (255, 255, 225), (c - 14, c - 4, 10, 8))
        pygame.draw.circle(img, (70, 85, 45), (c + 3, c), 6)
        pygame.draw.circle(img, (45, 52, 35), (c + 9, c), 5)
        wiggle = math.sin(self.t * 9) * 2
        for side in (-1, 1):
            pygame.draw.circle(img, (255, 255, 255), (c + 11, c + side * 3), 2)
            pygame.draw.circle(img, (0, 0, 0), (c + 12, c + side * 3), 1)
            tip = (c + 20, int(c + side * (7 + wiggle)))
            pygame.draw.line(img, (90, 105, 60), (c + 12, c + side * 2), tip, 2)
            pygame.draw.circle(img, BUG, tip, 2)
        img = pygame.transform.rotozoom(img, angle, scale)
        if alpha < 255:
            img.set_alpha(alpha)
        surf.blit(img, img.get_rect(center=(int(cx), int(cy))))

    def draw_shade(self, surf, cx, cy, body, eye, direction, spin, scared=False, size=1.0, flash=False):
        if scared:
            body = SCARED_BODY
            eye = (255, 255, 255) if flash else (190, 220, 255)
        wob = math.sin(self.t * 6 + spin) * 1.5
        draw_glow(surf, (cx, cy), 30 * size, eye, 0.3)
        rot = self.t * (-1.5 if scared else 2.5) + spin
        spike = scale_color(body, 1.8)
        for i in range(9):
            a = rot + i * math.tau / 9
            tip = (15 + 2.5 * math.sin(self.t * 7 + i + spin)) * size
            base = 10 * size
            pygame.draw.polygon(surf, spike, [
                (cx + math.cos(a - 0.3) * base, cy + math.sin(a - 0.3) * base),
                (cx + math.cos(a) * tip, cy + math.sin(a) * tip),
                (cx + math.cos(a + 0.3) * base, cy + math.sin(a + 0.3) * base)])
        pygame.draw.circle(surf, body, (int(cx), int(cy + wob)), int(12 * size))
        pygame.draw.circle(surf, scale_color(body, 1.5), (int(cx - 3 * size), int(cy - 4 * size + wob)), int(5 * size))
        dx, dy = direction
        for side in (-1, 1):
            ex, ey = cx + side * 4.5 * size + dx * 3, cy - 1 + dy * 3 + wob
            draw_glow(surf, (ex, ey), 8 * size, eye, 0.5)
            pygame.draw.circle(surf, eye, (int(ex), int(ey)), max(1, int(3 * size)))
        if scared:
            pts = [(cx - 7 + i * 2.8, cy + 6 + wob + (2 if i % 2 else 0)) for i in range(6)]
            pygame.draw.lines(surf, eye, False, pts, 2)

    def draw_lantern(self, surf, cx, cy, phase):
        bob = math.sin(self.t * 3 + phase) * 2
        pulse = 0.5 + 0.5 * math.sin(self.t * 5 + phase)
        cy += bob
        draw_glow(surf, (cx, cy), 34 + pulse * 6, LANTERN, 0.5 + 0.3 * pulse)
        pygame.draw.arc(surf, (150, 110, 70), (cx - 5, cy - 14, 10, 10), 0, math.pi, 2)
        pygame.draw.rect(surf, (90, 60, 40), (cx - 6, cy - 10, 12, 3), border_radius=1)
        pygame.draw.rect(surf, LANTERN, (cx - 6, cy - 7, 12, 14), border_radius=4)
        pygame.draw.rect(surf, mix(SPARK, (255, 255, 255), pulse), (cx - 3, cy - 4, 6, 8), border_radius=2)
        pygame.draw.rect(surf, (90, 60, 40), (cx - 6, cy + 7, 12, 3), border_radius=1)

    def draw_spark(self, surf, cx, cy, phase):
        tw = 0.5 + 0.5 * math.sin(self.t * 3 + phase)
        cy += math.sin(self.t * 2 + phase) * 1.5
        draw_glow(surf, (cx, cy), 10 + 3 * tw, SPARK, 0.3 + 0.25 * tw)
        pygame.draw.circle(surf, mix(SPARK, (255, 255, 255), tw * 0.7), (int(cx), int(cy)), int(2 + tw * 1.5))

    def draw_portal(self, surf, cx, cy):
        lvl = self.level
        if self.exit_open():
            pulse = 0.5 + 0.5 * math.sin(self.t * 4)
            draw_glow(surf, (cx, cy), 50 + 8 * pulse, PORTAL, 0.75)
            for i, (r, speed) in enumerate(((15, 2.0), (11, -3.2), (7, 4.6))):
                a = self.t * speed + i
                rect = pygame.Rect(0, 0, r * 2, r * 2)
                rect.center = (int(cx), int(cy))
                pygame.draw.arc(surf, mix(PORTAL, (255, 255, 255), i * 0.35), rect, a, a + 4.3, 3)
            pygame.draw.circle(surf, (235, 250, 255), (int(cx), int(cy)), 3)
        else:
            charge = self.collected / max(1, lvl.sparks_needed)
            rect = pygame.Rect(0, 0, 30, 30)
            rect.center = (int(cx), int(cy))
            draw_glow(surf, (cx, cy), 30, PORTAL, 0.15 + 0.3 * charge)
            pygame.draw.circle(surf, (45, 45, 80), rect.center, 15, 2)
            if charge > 0:
                pygame.draw.arc(surf, scale_color(PORTAL, 0.8), rect, math.pi / 2, math.pi / 2 + math.tau * charge, 3)
            pygame.draw.rect(surf, DIM, (cx - 5, cy - 2, 10, 8), border_radius=2)
            pygame.draw.arc(surf, DIM, (cx - 4, cy - 8, 8, 10), 0, math.pi, 2)

    # --- Drawing ---

    def draw(self):
        if self.state == "title":
            self.draw_title()
        else:
            self.draw_world()
            self.draw_hud()
            self.draw_overlay()
        draw_particles(self.screen, self.ui_particles)
        if self.fade > 0:
            self.shade_overlay.fill((0, 0, 0, int(255 * min(1.0, self.fade))))
            self.screen.blit(self.shade_overlay, (0, 0))

    def draw_world(self):
        v = self.view
        lvl = self.level
        v.fill(BG)
        cam_x, cam_y = self.cam
        if self.shake > 0:
            cam_x += random.uniform(-1, 1) * self.shake * 16
            cam_y += random.uniform(-1, 1) * self.shake * 16
        ox, oy = -cam_x, -cam_y
        self.draw_stars(v, cam_x, cam_y, VIEW_W, VIEW_H)

        x0, x1 = max(0, int(cam_x // TILE)), min(lvl.w, int((cam_x + VIEW_W) // TILE) + 2)
        y0, y1 = max(0, int(cam_y // TILE)), min(lvl.h, int((cam_y + VIEW_H) // TILE) + 2)
        for y in range(y0, y1):
            for x in range(x0, x1):
                if (x, y) in lvl.sparks:
                    self.draw_spark(v, x * TILE + TILE / 2 + ox, y * TILE + TILE / 2 + oy, lvl.phase[(x, y)])
        v.blit(lvl.wall_surface, (int(ox), int(oy)))

        ex, ey = center_of(lvl.exit)
        self.draw_portal(v, ex + ox, ey + oy)
        for t in lvl.lanterns:
            lx, ly = center_of(t)
            self.draw_lantern(v, lx + ox, ly + oy, lvl.phase[t])

        flash = self.fright_timer < 2.0 and int(self.t * 8) % 2 == 0
        for s in self.shades:
            if s.state == "gone":
                continue
            size = 1.0
            if s.state == "spawning":
                size = max(0.05, 1.0 - s.timer)
                if int(self.t * 20) % 2 == 0:
                    continue
            sx, sy = center_of(s.pos)
            self.draw_shade(v, sx + ox, sy + oy, s.body, s.eye, s.dir, s.spin, s.scared, size, flash)

        bx, by = center_of(self.bug.pos)
        if self.state == "exiting":
            k = min(1.0, self.state_time / 1.2)
            self.draw_bug(v, ex + ox, ey + oy, self.bug.angle + 900 * k * k, max(0.05, 1 - k))
        elif self.state == "dying":
            k = min(1.0, self.state_time / 0.6)
            if k < 1:
                self.draw_bug(v, bx + ox, by + oy, self.bug.angle + 720 * k, 1 - k)
        elif self.state != "level_done":
            alpha = 110 if self.invuln > 0 and int(self.t * 12) % 2 == 0 else 255
            self.draw_bug(v, bx + ox, by + oy, self.bug.angle, 1.0, alpha)

        draw_particles(v, self.particles, ox, oy)
        for text in self.texts:
            surf = text["surf"]
            surf.set_alpha(int(255 * min(1.0, text["life"] / text["max"] * 2)))
            v.blit(surf, surf.get_rect(center=(int(text["x"] + ox), int(text["y"] + oy))))
        v.blit(self.vignette, (0, 0))
        if lvl.minimap:
            self.draw_minimap(v, cam_x, cam_y)

    def draw_minimap(self, v, cam_x, cam_y):
        lvl = self.level
        mm = lvl.minimap
        k = mm.get_width() / lvl.w
        mx, my = VIEW_W - mm.get_width() - 14, VIEW_H - mm.get_height() - 14
        pygame.draw.rect(v, (60, 70, 170), (mx - 3, my - 3, mm.get_width() + 6, mm.get_height() + 6), 1, border_radius=4)
        v.blit(mm, (mx, my))

        def dot(tile, color, r):
            pygame.draw.circle(v, color, (int(mx + (tile[0] + 0.5) * k), int(my + (tile[1] + 0.5) * k)), r)

        for t in lvl.lanterns:
            dot(t, LANTERN, 2)
        dot(lvl.exit, PORTAL if self.exit_open() else DIM, 3)
        for s in self.shades:
            if s.state != "gone":
                dot(s.pos, (140, 170, 255) if s.scared else s.eye, 2)
        if int(self.t * 4) % 2 == 0:
            dot(self.bug.pos, BUG, 3)
        view_rect = (mx + cam_x / TILE * k, my + cam_y / TILE * k, VIEW_W / TILE * k, VIEW_H / TILE * k)
        pygame.draw.rect(v, (200, 210, 255), view_rect, 1)

    def draw_hud(self):
        s = self.screen
        lvl = self.level
        pygame.draw.rect(s, (12, 10, 30), (0, 0, SCREEN_W, HUD_H))
        pygame.draw.line(s, (50, 60, 170), (0, HUD_H - 1), (SCREEN_W, HUD_H - 1), 2)
        self.text(s, "LEVEL {}".format(lvl.number + 1), 16, DIM, (20, 8))
        self.text(s, lvl.cfg["name"], 28, TEXT, (20, 24))

        bx, by, bw, bh = 290, 38, 270, 12
        opened = self.exit_open()
        if opened:
            label, color = "Exit open! Fly to the portal", PORTAL
        else:
            label, color = "Sparks {} / {} to open the exit".format(self.collected, lvl.sparks_needed), DIM
        self.text(s, label, 16, color, (bx, 12))
        pygame.draw.rect(s, (30, 28, 60), (bx, by, bw, bh), border_radius=6)
        fill = int(bw * self.collected / max(1, lvl.total_sparks))
        if fill > 0:
            pygame.draw.rect(s, PORTAL if opened else SPARK, (bx, by, fill, bh), border_radius=6)
        if lvl.sparks_needed < lvl.total_sparks:
            gx = bx + int(bw * lvl.sparks_needed / lvl.total_sparks)
            pygame.draw.line(s, TEXT, (gx, by - 3), (gx, by + bh + 2), 2)

        if self.fright_timer > 0 and self.state == "play":
            self.text(s, "Scared: {:.0f}s".format(math.ceil(self.fright_timer)), 16, LANTERN, (bx + bw + 20, 12))
        self.text(s, "SCORE", 16, DIM, (680, 8))
        self.text(s, "{:,}".format(self.score), 28, TEXT, (680, 24))
        for i in range(min(self.lives, MAX_LIVES)):
            self.draw_bug(s, SCREEN_W - 36 - i * 38, HUD_H / 2, 90, 0.7)

    def draw_panel(self, w, h):
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(panel, (10, 10, 30, 215), (0, 0, w, h), border_radius=18)
        pygame.draw.rect(panel, (80, 100, 230, 255), (0, 0, w, h), 2, border_radius=18)
        rect = panel.get_rect(center=(SCREEN_W / 2, HUD_H + VIEW_H / 2))
        self.screen.blit(panel, rect)
        return rect

    def draw_overlay(self):
        s = self.screen
        cx = SCREEN_W / 2
        cy = HUD_H + VIEW_H / 2
        blink = int(self.t * 2.5) % 2 == 0
        if self.state == "intro":
            if self.intro_len > 2:
                self.draw_panel(560, 250)
                lvl = self.level
                self.text(s, "LEVEL {}".format(lvl.number + 1), 20, DIM, (cx, cy - 90), "center")
                self.text(s, lvl.cfg["name"], 64, BUG, (cx, cy - 35), "center", glow=True)
                if lvl.sparks_needed == lvl.total_sparks:
                    goal = "Collect every spark to open the exit"
                else:
                    goal = "Collect {} of {} sparks to open the exit".format(lvl.sparks_needed, lvl.total_sparks)
                self.text(s, goal, 20, TEXT, (cx, cy + 30), "center")
                if blink:
                    self.text(s, "Get ready...", 20, SPARK, (cx, cy + 75), "center")
            else:
                self.text(s, "Ready!", 64, SPARK, (cx, cy), "center", glow=True)
        elif self.state == "paused":
            self.draw_panel(420, 160)
            self.text(s, "Paused", 64, TEXT, (cx, cy - 20), "center", glow=True)
            self.text(s, "Press P to continue", 20, DIM, (cx, cy + 45), "center")
        elif self.state == "level_done":
            self.draw_panel(600, 340)
            lvl = self.level
            self.text(s, "Level complete!", 64, PORTAL, (cx, cy - 115), "center", glow=True)
            minutes, seconds = divmod(int(self.level_time), 60)
            lines = [("Sparks collected", "{} / {}".format(self.collected, lvl.total_sparks)),
                     ("Time", "{}:{:02d}".format(minutes, seconds))]
            lines += [(name, "+{:,}".format(points)) for name, points in self.report]
            if self.got_life:
                lines.append(("Extra life", "+1"))
            y = cy - 50
            for name, value in lines:
                self.text(s, name, 20, DIM, (cx - 190, y))
                self.text(s, value, 20, TEXT, (cx + 190, y), "topright")
                y += 32
            if blink:
                self.text(s, "Press Enter to continue", 20, SPARK, (cx, cy + 135), "center")
        elif self.state == "game_over":
            self.draw_panel(480, 230)
            self.text(s, "Game over", 64, DANGER, (cx, cy - 50), "center", glow=True)
            self.text(s, "Final score: {:,}".format(self.score), 28, TEXT, (cx, cy + 15), "center")
            if blink and self.state_time > 1:
                self.text(s, "Press Enter to return to the title screen", 20, DIM, (cx, cy + 70), "center")
        elif self.state == "victory":
            self.draw_panel(840, 250)
            self.text(s, "You escaped every maze!", 64, SPARK, (cx, cy - 50), "center", glow=True)
            self.text(s, "Final score: {:,}".format(self.score), 28, TEXT, (cx, cy + 20), "center")
            if blink and self.state_time > 1:
                self.text(s, "Press Enter to return to the title screen", 20, DIM, (cx, cy + 75), "center")

    def draw_title(self):
        s = self.screen
        s.fill(BG)
        self.draw_stars(s, self.t * 40, self.t * 12, SCREEN_W, SCREEN_H)

        title = "GLOWBUG"
        font = self.fonts[96]
        x = SCREEN_W / 2 - font.size(title)[0] / 2
        letters = []
        for i, ch in enumerate(title):
            letters.append((ch, x, 110 + math.sin(self.t * 2.5 + i * 0.6) * 10))
            x += font.size(ch)[0]
        # Glows first, so no letter's glow covers its neighbor.
        for ch, x, y in letters:
            self.text(s, ch, 96, BUG, (x - 48, y - 48), glow=True)
        for ch, x, y in letters:
            self.text(s, ch, 96, BUG, (x, y))
        self.text(s, "a neon maze chase", 28, DIM, (SCREEN_W / 2, 250), "center")

        # A little chase scene: the firefly, followed by two shades.
        for delay, kind in ((1.0, "hunter"), (1.6, "ambusher")):
            t = self.t - delay
            sx, sy = self.title_bug_pos(t)
            body, eye, _ = SHADE_STYLES[kind]
            self.draw_shade(s, sx, sy, body, eye, STOP, delay * 3)
        bx, by = self.title_bug_pos(self.t)
        nx, ny = self.title_bug_pos(self.t + 0.01)
        self.draw_bug(s, bx, by, -math.degrees(math.atan2(ny - by, nx - bx)), 1.4)

        rows = [("spark", "Collect sparks to charge the exit portal"),
                ("lantern", "Grab a lantern to scare the shades, then catch them for points"),
                ("shade", "Don't let a shade touch you"),
                ("portal", "Fly into the open portal to finish the level")]
        y = 520
        for icon, line in rows:
            ix = 250
            if icon == "spark":
                self.draw_spark(s, ix, y, 0)
            elif icon == "lantern":
                self.draw_lantern(s, ix, y, 0)
            elif icon == "shade":
                self.draw_shade(s, ix, y, *SHADE_STYLES["hunter"][:2], STOP, 0, size=0.8)
            else:
                pulse = 0.5 + 0.5 * math.sin(self.t * 4)
                draw_glow(s, (ix, y), 26 + 4 * pulse, PORTAL, 0.6)
                pygame.draw.circle(s, PORTAL, (ix, y), 10, 3)
            self.text(s, line, 20, TEXT, (ix + 35, y), "midleft")
            y += 40

        if int(self.t * 2) % 2 == 0:
            self.text(s, "Press Enter to start", 40, SPARK, (SCREEN_W / 2, 712), "center", glow=True)
        self.text(s, "1, 2, 3: choose a level      Arrow keys or WASD: move      P: pause      Esc: quit",
                  16, DIM, (SCREEN_W / 2, 750), "center")

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            for event in pygame.event.get():
                self.handle(event)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
