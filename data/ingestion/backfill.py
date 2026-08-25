import json
import os
import random
import sys

import pygame

BOARD_SIZE = 600
HEADER_HEIGHT = 100
WINDOW_WIDTH = BOARD_SIZE
WINDOW_HEIGHT = BOARD_SIZE + HEADER_HEIGHT
TILE_MARGIN = 10
FPS = 60
WINNING_TILE = 2048
HIGHSCORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "highscores.json")

BACKGROUND_COLOR = (187, 173, 160)
HEADER_COLOR = (250, 248, 239)
EMPTY_CELL_COLOR = (205, 193, 180)
CELL_COLOR = {
    2: (238, 228, 218),
    4: (237, 224, 200),
    8: (242, 177, 121),
    16: (245, 149, 99),
    32: (246, 124, 95),
    64: (246, 94, 59),
    128: (237, 207, 114),
    256: (237, 204, 97),
    512: (237, 200, 80),
    1024: (237, 197, 63),
    2048: (237, 194, 46),
}
SUPER_CELL_COLOR = (60, 58, 50)  # tiles above 2048
DARK_FONT_COLOR = (119, 110, 101)
LIGHT_FONT_COLOR = (249, 246, 242)

pygame.init()


def load_highscores():
    try:
        with open(HIGHSCORE_FILE) as f:
            data = json.load(f)
        return {int(k): int(v) for k, v in data.items()}
    except (OSError, ValueError):
        return {}


def save_highscores(highscores):
    try:
        with open(HIGHSCORE_FILE, "w") as f:
            json.dump(highscores, f)
    except OSError:
        pass


class Game2048:
    def __init__(self, grid_size):
        self.grid_size = grid_size
        self.grid = [[0] * grid_size for _ in range(grid_size)]
        self.score = 0
        self.won = False
        self.keep_playing = False
        self.history = []
        self.add_new_tile()
        self.add_new_tile()

    def add_new_tile(self):
        empty_tiles = [(i, j) for i in range(self.grid_size) for j in range(self.grid_size) if self.grid[i][j] == 0]
        if empty_tiles:
            i, j = random.choice(empty_tiles)
            # As in the original game, 90% of new tiles are a 2 and 10% are a 4.
            self.grid[i][j] = 2 if random.random() < 0.9 else 4

    def compress(self):
        new_grid = [[0] * self.grid_size for _ in range(self.grid_size)]
        for i in range(self.grid_size):
            pos = 0
            for j in range(self.grid_size):
                if self.grid[i][j] != 0:
                    new_grid[i][pos] = self.grid[i][j]
                    pos += 1
        self.grid = new_grid

    def merge(self):
        for i in range(self.grid_size):
            for j in range(self.grid_size - 1):
                if self.grid[i][j] == self.grid[i][j + 1] and self.grid[i][j] != 0:
                    self.grid[i][j] *= 2
                    self.score += self.grid[i][j]
                    self.grid[i][j + 1] = 0

    def reverse(self):
        self.grid = [row[::-1] for row in self.grid]

    def transpose(self):
        self.grid = [list(row) for row in zip(*self.grid)]

    def shift_left(self):
        self.compress()
        self.merge()
        self.compress()

    def move(self, direction):
        """Apply a move and return True if it changed the board.

        A new tile is only spawned when the move actually shifts or
        merges something, matching the rules of the original game.
        """
        before_grid = [row[:] for row in self.grid]
        before_score = self.score

        if direction == "left":
            self.shift_left()
        elif direction == "right":
            self.reverse()
            self.shift_left()
            self.reverse()
        elif direction == "up":
            self.transpose()
            self.shift_left()
            self.transpose()
        elif direction == "down":
            self.transpose()
            self.reverse()
            self.shift_left()
            self.reverse()
            self.transpose()

        moved = self.grid != before_grid
        if moved:
            self.history.append((before_grid, before_score))
            if len(self.history) > 10:
                self.history.pop(0)
            self.add_new_tile()
            if not self.won and any(WINNING_TILE in row for row in self.grid):
                self.won = True
        return moved

    def undo(self):
        if self.history:
            self.grid, self.score = self.history.pop()
            return True
        return False

    def has_moves(self):
        if any(0 in row for row in self.grid):
            return True
        for i in range(self.grid_size):
            for j in range(self.grid_size - 1):
                if self.grid[i][j] == self.grid[i][j + 1] or self.grid[j][i] == self.grid[j + 1][i]:
                    return True
        return False

    def is_game_over(self):
        return not self.has_moves()


class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.title_font = pygame.font.Font(None, 72)
        self.label_font = pygame.font.Font(None, 28)
        self.score_font = pygame.font.Font(None, 40)
        self.tile_fonts = {}

    def tile_font(self, size):
        if size not in self.tile_fonts:
            self.tile_fonts[size] = pygame.font.Font(None, size)
        return self.tile_fonts[size]

    def draw_header(self, game, best_score):
        pygame.draw.rect(self.screen, HEADER_COLOR, (0, 0, WINDOW_WIDTH, HEADER_HEIGHT))
        title = self.title_font.render("2048", True, DARK_FONT_COLOR)
        self.screen.blit(title, (20, HEADER_HEIGHT // 2 - title.get_height() // 2))

        for label, value, x in (("SCORE", game.score, 250), ("BEST", best_score, 430)):
            box = pygame.Rect(x, 15, 150, HEADER_HEIGHT - 30)
            pygame.draw.rect(self.screen, BACKGROUND_COLOR, box, border_radius=6)
            label_text = self.label_font.render(label, True, HEADER_COLOR)
            value_text = self.score_font.render(str(value), True, LIGHT_FONT_COLOR)
            self.screen.blit(label_text, label_text.get_rect(midtop=(box.centerx, box.top + 8)))
            self.screen.blit(value_text, value_text.get_rect(midbottom=(box.centerx, box.bottom - 8)))

    def draw_board(self, game):
        pygame.draw.rect(self.screen, BACKGROUND_COLOR, (0, HEADER_HEIGHT, BOARD_SIZE, BOARD_SIZE))
        cell_size = BOARD_SIZE // game.grid_size
        for i in range(game.grid_size):
            for j in range(game.grid_size):
                value = game.grid[i][j]
                rect = pygame.Rect(
                    j * cell_size + TILE_MARGIN // 2,
                    HEADER_HEIGHT + i * cell_size + TILE_MARGIN // 2,
                    cell_size - TILE_MARGIN,
                    cell_size - TILE_MARGIN,
                )
                color = CELL_COLOR.get(value, SUPER_CELL_COLOR) if value else EMPTY_CELL_COLOR
                pygame.draw.rect(self.screen, color, rect, border_radius=8)
                if value:
                    font_color = DARK_FONT_COLOR if value <= 4 else LIGHT_FONT_COLOR
                    font_size = max(24, int(cell_size * 0.5) - 8 * (len(str(value)) - 2))
                    text = self.tile_font(font_size).render(str(value), True, font_color)
                    self.screen.blit(text, text.get_rect(center=rect.center))

    def draw_overlay(self, lines):
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((238, 228, 218, 200))
        self.screen.blit(overlay, (0, 0))
        y = WINDOW_HEIGHT // 2 - 30 * len(lines)
        for index, line in enumerate(lines):
            font = self.title_font if index == 0 else self.score_font
            text = font.render(line, True, DARK_FONT_COLOR)
            self.screen.blit(text, text.get_rect(center=(WINDOW_WIDTH // 2, y)))
            y += text.get_height() + 20

    def draw_menu(self, highscores):
        self.screen.fill(HEADER_COLOR)
        lines = [
            ("2048", self.title_font),
            ("Press 4, 5 or 6 to choose a grid size", self.score_font),
            ("", self.label_font),
            ("Arrow keys / WASD: move tiles", self.label_font),
            ("U: undo    R: restart    Esc: menu", self.label_font),
        ]
        y = 120
        for line, font in lines:
            if line:
                text = font.render(line, True, DARK_FONT_COLOR)
                self.screen.blit(text, text.get_rect(center=(WINDOW_WIDTH // 2, y)))
            y += 60
        y += 20
        for size in (4, 5, 6):
            best = highscores.get(size, 0)
            text = self.label_font.render(f"{size} x {size}  best: {best}", True, DARK_FONT_COLOR)
            self.screen.blit(text, text.get_rect(center=(WINDOW_WIDTH // 2, y)))
            y += 40


DIRECTION_KEYS = {
    pygame.K_LEFT: "left",
    pygame.K_a: "left",
    pygame.K_RIGHT: "right",
    pygame.K_d: "right",
    pygame.K_UP: "up",
    pygame.K_w: "up",
    pygame.K_DOWN: "down",
    pygame.K_s: "down",
}

GRID_SIZE_KEYS = {pygame.K_4: 4, pygame.K_5: 5, pygame.K_6: 6}


def main():
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("2048")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)
    highscores = load_highscores()

    state = "menu"  # menu, playing, won, game_over
    game = None

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type != pygame.KEYDOWN:
                continue

            if state == "menu":
                if event.key in GRID_SIZE_KEYS:
                    game = Game2048(GRID_SIZE_KEYS[event.key])
                    state = "playing"
            elif state == "playing":
                if event.key in DIRECTION_KEYS:
                    if game.move(DIRECTION_KEYS[event.key]):
                        if game.score > highscores.get(game.grid_size, 0):
                            highscores[game.grid_size] = game.score
                            save_highscores(highscores)
                        if game.won and not game.keep_playing:
                            state = "won"
                        elif game.is_game_over():
                            state = "game_over"
                elif event.key == pygame.K_u:
                    game.undo()
                elif event.key == pygame.K_r:
                    game = Game2048(game.grid_size)
                elif event.key == pygame.K_ESCAPE:
                    state = "menu"
            elif state == "won":
                if event.key == pygame.K_c:
                    game.keep_playing = True
                    state = "playing"
                elif event.key == pygame.K_r:
                    game = Game2048(game.grid_size)
                    state = "playing"
                elif event.key == pygame.K_ESCAPE:
                    state = "menu"
            elif state == "game_over":
                if event.key == pygame.K_r:
                    game = Game2048(game.grid_size)
                    state = "playing"
                elif event.key == pygame.K_ESCAPE:
                    state = "menu"

        if state == "menu":
            renderer.draw_menu(highscores)
        else:
            renderer.draw_header(game, highscores.get(game.grid_size, 0))
            renderer.draw_board(game)
            if state == "won":
                renderer.draw_overlay(["You win!", "C: keep playing", "R: restart    Esc: menu"])
            elif state == "game_over":
                renderer.draw_overlay(["Game over!", f"Score: {game.score}", "R: restart    Esc: menu"])

        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()