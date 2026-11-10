"""Render English Instagram assets for De Anza Chess Club weekly puzzles.

- render_puzzle_post(): 1080x1350 feed post with the puzzle position.
- render_answer_post(): 1080x1350 feed post with the solution (STARTING position).
- render_question_story() / render_answer_story(): 1080x1920 story variants.
All text is English. No emojis (avoids tofu on renderers without emoji fonts).

Fonts: resolved at import time by searching Noto first, then DejaVu, so the
same code works on the original dev machine and on GitHub Actions
ubuntu-latest runners (which need fonts-noto-core installed; DejaVu ships
with the base image). Import fails loudly if no usable font is found.
"""
import io
import os

import cairosvg
import chess
import chess.svg
from PIL import Image, ImageDraw, ImageFont

def _find_font(role, *candidates):
    """Return the first existing font path, or fail loudly with a clear error."""
    for path in candidates:
        if os.path.exists(path):
            return path
    raise RuntimeError(
        f"No font found for {role}. Tried: {', '.join(candidates)}. "
        "On GitHub Actions ubuntu runners, install fonts-noto-core "
        "(DejaVu ships with the base image)."
    )


# Prefer Noto (as on the original dev machine), fall back to DejaVu
# (present on stock ubuntu-latest runners).
SANS = _find_font(
    "regular sans",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
SANS_BOLD = _find_font(
    "bold sans",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
SANS_MED = _find_font(
    "medium sans",
    "/usr/share/fonts/truetype/noto/NotoSans-Medium.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
DEJA = _find_font(
    "DejaVu sans",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
)
SERIF_BOLD = _find_font(
    "bold serif",
    "/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
)

BG = (24, 26, 32)
PANEL = (33, 36, 45)
GOLD = (240, 185, 60)
WHITE = (245, 245, 245)
MUTED = (150, 155, 165)

LIGHT_SQ = "#EBD8B7"
DARK_SQ = "#9E6F4A"
LIGHT_LAST = "#CDEB8B"
DARK_LAST = "#A8C25A"


def _font(path, size):
    return ImageFont.truetype(path, size)


def _centered(d, W, y, text, font, fill):
    bbox = d.textbbox((0, 0), text, font=font)
    d.text(((W - (bbox[2] - bbox[0])) / 2, y), text, font=font, fill=fill)
    return bbox[3] - bbox[1]


def _board_png(fen, size, lastmove=None):
    board = chess.Board(fen)
    svg = chess.svg.board(
        board, size=size, coordinates=True,
        lastmove=lastmove,
        colors={"square light": LIGHT_SQ, "square dark": DARK_SQ,
                "square light lastmove": LIGHT_LAST,
                "square dark lastmove": DARK_LAST},
    )
    png = cairosvg.svg2png(bytestring=svg.encode(),
                           output_width=size, output_height=size)
    return Image.open(io.BytesIO(png))


def _stars(rating):
    # 800-2000 -> 1..5 stars
    n = max(1, min(5, 1 + int((rating - 800) / 300)))
    return "★" * n + "☆" * (5 - n)


def _pair_moves(san_list):
    """['Qh5+','Kg8','Qh7#'] -> ['1. Qh5+  Kg8', '2. Qh7#']"""
    lines = []
    for i in range(0, len(san_list), 2):
        num = i // 2 + 1
        w = san_list[i]
        b = san_list[i + 1] if i + 1 < len(san_list) else ""
        lines.append(f"{num}. {w}" + (f"   {b}" if b else ""))
    return lines


def render_puzzle_post(puzzle, number, out_path):
    """puzzle: dict with fen, side, theme, rating, lastmove_uci (optional)."""
    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    mate_n = puzzle["theme"].replace("mateIn", "")
    side = puzzle["side"].capitalize()

    _centered(d, W, 48, "DE ANZA CHESS CLUB", _font(SANS_MED, 32), MUTED)
    _centered(d, W, 96, "WEEKLY PUZZLE", _font(SERIF_BOLD, 68), GOLD)
    _centered(d, W, 182, f"#{number:03d}  ·  {side} to move  ·  Mate in {mate_n}",
              _font(SANS_BOLD, 36), WHITE)

    lastmove = None
    if puzzle.get("lastmove_uci"):
        lastmove = chess.Move.from_uci(puzzle["lastmove_uci"])
    board_img = _board_png(puzzle["fen"], 780, lastmove)
    img.paste(board_img, (150, 400))

    _centered(d, W, 1218, f"Difficulty {_stars(puzzle['rating'])}   (Lichess {puzzle['rating']})",
              _font(DEJA, 30), MUTED)
    _centered(d, W, 1268, "Answer revealed at 4 PM",
              _font(SANS_BOLD, 30), GOLD)

    img.save(out_path)
    return out_path


def render_question_story(puzzle, number, out_path):
    """1080x1920 story version of the puzzle (question only, no solution)."""
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    mate_n = puzzle["theme"].replace("mateIn", "")
    side = puzzle["side"].capitalize()

    _centered(d, W, 90, "DE ANZA CHESS CLUB", _font(SANS_MED, 32), MUTED)
    _centered(d, W, 140, "WEEKLY PUZZLE", _font(SERIF_BOLD, 76), GOLD)
    _centered(d, W, 240, f"#{number:03d}  ·  {side} to move  ·  Mate in {mate_n}",
              _font(SANS_BOLD, 36), WHITE)

    lastmove = None
    if puzzle.get("lastmove_uci"):
        lastmove = chess.Move.from_uci(puzzle["lastmove_uci"])
    board_img = _board_png(puzzle["fen"], 860, lastmove)
    img.paste(board_img, (110, 330))

    _centered(d, W, 1230, "Can you find the mate?", _font(SERIF_BOLD, 52), GOLD)
    _centered(d, W, 1310, f"Difficulty {_stars(puzzle['rating'])}   (Lichess {puzzle['rating']})",
              _font(DEJA, 30), MUTED)
    _centered(d, W, 1365, "Comment your first move on our latest post",
              _font(SANS, 30), MUTED)
    _centered(d, W, 1410, "Answer revealed at 4 PM in our story",
              _font(SANS_BOLD, 32), WHITE)

    _centered(d, W, H - 170, "New puzzle every Mon & Thu at 9 AM",
              _font(SANS_BOLD, 32), GOLD)
    _centered(d, W, H - 115, "De Anza Chess Club", _font(SANS, 28), MUTED)

    img.save(out_path)
    return out_path


def render_answer_post(puzzle, number, out_path):
    """puzzle: dict with fen, side, theme, rating, san, uci. 1080x1350 feed post with the solution."""
    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    mate_n = puzzle["theme"].replace("mateIn", "")
    side = puzzle["side"].capitalize()
    san_list = puzzle["san"].split()

    _centered(d, W, 48, "DE ANZA CHESS CLUB", _font(SANS_MED, 32), MUTED)
    _centered(d, W, 96, "PUZZLE ANSWER", _font(SERIF_BOLD, 68), GOLD)
    _centered(d, W, 182, f"#{number:03d}  ·  {side} to move  ·  Mate in {mate_n}",
              _font(SANS_BOLD, 36), WHITE)

    # Solution moves panel
    lines = _pair_moves(san_list)
    panel_top = 290
    line_h = 70
    panel_h = len(lines) * line_h + 60
    d.rounded_rectangle([90, panel_top, W - 90, panel_top + panel_h],
                        radius=28, fill=PANEL)
    y = panel_top + 34
    for line in lines:
        _centered(d, W, y, line, _font(SANS_MED, 44), WHITE)
        y += line_h

    # Answer board = the STARTING position (same board as the question post),
    # so readers can replay the solution — not the final checkmate position.
    # Board size adapts: mate-in-4 puzzles have a taller solution panel.
    board_max = H - 130 - (panel_top + panel_h + 40) - 50  # room for label + footer
    board_size = max(420, min(600, board_max))
    start_img = _board_png(puzzle["fen"], board_size)
    fx = (W - board_size) // 2
    fy = panel_top + panel_h + 40
    img.paste(start_img, (fx, fy))
    _centered(d, W, fy + board_size + 18, "Starting position",
              _font(SANS, 30), MUTED)

    _centered(d, W, H - 88, "New puzzle every Mon & Thu at 9 AM",
              _font(SANS_BOLD, 30), GOLD)
    _centered(d, W, H - 52, "De Anza Chess Club", _font(SANS, 26), MUTED)

    img.save(out_path)
    return out_path


def render_answer_story(puzzle, number, out_path):
    """puzzle: dict with fen, side, theme, rating, san (space-separated)."""
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    mate_n = puzzle["theme"].replace("mateIn", "")
    side = puzzle["side"].capitalize()
    san_list = puzzle["san"].split()

    _centered(d, W, 90, "DE ANZA CHESS CLUB", _font(SANS_MED, 32), MUTED)
    _centered(d, W, 140, "PUZZLE ANSWER", _font(SERIF_BOLD, 76), GOLD)
    _centered(d, W, 240, f"#{number:03d}  ·  {side} to move  ·  Mate in {mate_n}",
              _font(SANS_BOLD, 36), WHITE)

    # Solution moves panel
    lines = _pair_moves(san_list)
    panel_top = 340
    line_h = 84
    panel_h = len(lines) * line_h + 60
    d.rounded_rectangle([90, panel_top, W - 90, panel_top + panel_h],
                        radius=28, fill=PANEL)
    y = panel_top + 34
    for line in lines:
        _centered(d, W, y, line, _font(SANS_MED, 44), WHITE)
        y += line_h

    # Final (mating) position
    board = chess.Board(puzzle["fen"])
    for uci in puzzle["uci"].split():
        board.push(chess.Move.from_uci(uci))
    final_img = _board_png(board.fen(), 640)
    fx = (W - 640) // 2
    fy = panel_top + panel_h + 60
    img.paste(final_img, (fx, fy))
    _centered(d, W, fy + 660, "Final position — checkmate",
              _font(SANS, 30), MUTED)

    _centered(d, W, H - 170, "New puzzle every Mon & Thu at 9 AM",
              _font(SANS_BOLD, 32), GOLD)
    _centered(d, W, H - 115, "De Anza Chess Club", _font(SANS, 28), MUTED)

    img.save(out_path)
    return out_path
