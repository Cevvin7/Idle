import pygame
import math
import sys

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCREEN_W, SCREEN_H = 1024, 768
FPS = 60
UI_BAR_H = 48  # height of the top UI bar
BOTTOM_BAR_H = 48  # height of the bottom bar

# Dot grid for wall placement
GRID_SPACING = 64
GRID_DOT_RADIUS = 4
GRID_COLOR = (60, 60, 60)

# Cannon
CANNON_RADIUS = 22
CANNON_BARREL_LEN = 34
CANNON_BARREL_W = 10
CANNON_COLOR = (180, 180, 200)
CANNON_BARREL_COLOR = (140, 140, 160)

# Orbs
ORB_RADIUS = 8
ORB_SPEED = 7
ORB_COLOR = (100, 200, 255)
ORB_MAX_BOUNCES = 3

# Walls
WALL_COLOR = (220, 220, 220)
WALL_THICKNESS = 6
WALL_PREVIEW_COLOR = (220, 220, 220, 120)

# UI colors
BG_COLOR = (18, 18, 24)
UI_BG = (30, 30, 40)
UI_TEXT = (230, 230, 230)
UI_ACCENT = (80, 140, 220)
UI_ACCENT_HOVER = (100, 160, 240)
UI_BUTTON_BG = (45, 45, 60)
UI_BUTTON_HOVER = (60, 60, 80)
SHOP_BG = (25, 25, 35)
SHOP_ITEM_BG = (40, 40, 55)
SHOP_ITEM_HOVER = (55, 55, 75)
MENU_BG = (25, 25, 35)

# Shop panel
SHOP_W = 280

# Upgrade costs
BASE_UPGRADE_COST = 10
COST_MULTIPLIER = 10


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def grid_dots(surface_w, surface_h):
    """Return list of (x, y) grid dot positions inside the play area."""
    dots = []
    start_y = UI_BAR_H + GRID_SPACING
    x = GRID_SPACING
    while x < surface_w:
        y = start_y
        while y < surface_h - BOTTOM_BAR_H:
            dots.append((x, y))
            y += GRID_SPACING
        x += GRID_SPACING
    return dots


def snap_to_grid(pos):
    """Snap a position to the nearest grid dot."""
    x = round(pos[0] / GRID_SPACING) * GRID_SPACING
    y_start = UI_BAR_H + GRID_SPACING
    # snap y relative to grid start
    y_rel = pos[1] - y_start
    y_idx = round(y_rel / GRID_SPACING)
    y = y_start + y_idx * GRID_SPACING
    return (x, y)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_on_grid(p):
    """Check if a point lies on a valid grid position."""
    snapped = snap_to_grid(p)
    if snapped[1] < UI_BAR_H + GRID_SPACING:
        return False
    if snapped[0] < GRID_SPACING or snapped[0] >= SCREEN_W:
        return False
    if snapped[1] >= SCREEN_H - BOTTOM_BAR_H:
        return False
    return dist(p, snapped) < GRID_DOT_RADIUS + 12


def walls_are_axis_aligned(a, b):
    """Only allow horizontal or vertical walls (between adjacent dots)."""
    return a[0] == b[0] or a[1] == b[1]


def walls_are_adjacent(a, b):
    """Points must be exactly one grid spacing apart."""
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return (dx == GRID_SPACING and dy == 0) or (dx == 0 and dy == GRID_SPACING)


# ---------------------------------------------------------------------------
# Enclosed-box detection using flood fill
# ---------------------------------------------------------------------------
def find_enclosed_cells(walls):
    """Find all enclosed cells given the current walls.

    Returns a set of (row, col) tuples for cells that are fully enclosed.
    """
    wall_set = set()
    for w in walls:
        wall_set.add(frozenset([w[0], w[1]]))

    def has_wall(p1, p2):
        return frozenset([p1, p2]) in wall_set

    # Build list of cell top-left corners
    cells = []
    y = UI_BAR_H + GRID_SPACING
    while y + GRID_SPACING <= SCREEN_H - BOTTOM_BAR_H:
        x = GRID_SPACING
        while x + GRID_SPACING <= SCREEN_W:
            cells.append((x, y))
            x += GRID_SPACING
        y += GRID_SPACING

    if not cells:
        return set()

    cols = (SCREEN_W - GRID_SPACING) // GRID_SPACING
    rows = len(cells) // cols if cols > 0 else 0
    if rows == 0 or cols == 0:
        return set()

    # Flood fill: start from every edge cell
    visited = [[False] * cols for _ in range(rows)]
    queue = []
    for r in range(rows):
        for c in range(cols):
            if r == 0 or r == rows - 1 or c == 0 or c == cols - 1:
                queue.append((r, c))
                visited[r][c] = True

    while queue:
        r, c = queue.pop()
        tl = (GRID_SPACING + c * GRID_SPACING, UI_BAR_H + GRID_SPACING + r * GRID_SPACING)
        tr = (tl[0] + GRID_SPACING, tl[1])
        bl = (tl[0], tl[1] + GRID_SPACING)
        br = (tl[0] + GRID_SPACING, tl[1] + GRID_SPACING)

        # Up (r-1, c): wall between tl-tr
        if r > 0 and not visited[r - 1][c] and not has_wall(tl, tr):
            visited[r - 1][c] = True
            queue.append((r - 1, c))
        # Down (r+1, c): wall between bl-br
        if r < rows - 1 and not visited[r + 1][c] and not has_wall(bl, br):
            visited[r + 1][c] = True
            queue.append((r + 1, c))
        # Left (r, c-1): wall between tl-bl
        if c > 0 and not visited[r][c - 1] and not has_wall(tl, bl):
            visited[r][c - 1] = True
            queue.append((r, c - 1))
        # Right (r, c+1): wall between tr-br
        if c < cols - 1 and not visited[r][c + 1] and not has_wall(tr, br):
            visited[r][c + 1] = True
            queue.append((r, c + 1))

    enclosed = set()
    for r in range(rows):
        for c in range(cols):
            if not visited[r][c]:
                enclosed.add((r, c))
    return enclosed


def would_enclose(walls, new_wall, cannon_pos=None):
    """Check whether adding new_wall would create a fully enclosed region
    that contains the cannon (if cannon_pos given). If cannon_pos is None,
    enclosing is always blocked (legacy behavior).
    """
    all_walls = walls + [new_wall]
    enclosed = find_enclosed_cells(all_walls)
    if not enclosed:
        return False

    if cannon_pos is None:
        return True

    # Check if cannon is in any enclosed cell
    cannon_cell = get_cell_at_pos(cannon_pos)
    if cannon_cell is not None and cannon_cell in enclosed:
        return True

    # Enclosing is allowed as long as cannon is not enclosed
    return False


def get_cell_at_pos(pos):
    """Get the (row, col) cell that contains the given position."""
    x, y = pos
    col = (x - GRID_SPACING) // GRID_SPACING
    row = (y - (UI_BAR_H + GRID_SPACING)) // GRID_SPACING
    cols = (SCREEN_W - GRID_SPACING) // GRID_SPACING
    rows_max = (SCREEN_H - BOTTOM_BAR_H - (UI_BAR_H + GRID_SPACING)) // GRID_SPACING
    if 0 <= row < rows_max and 0 <= col < cols:
        return (row, col)
    return None


def cell_center(row, col):
    """Get the pixel center of a grid cell given its (row, col)."""
    x = GRID_SPACING + col * GRID_SPACING + GRID_SPACING // 2
    y = UI_BAR_H + GRID_SPACING + row * GRID_SPACING + GRID_SPACING // 2
    return (x, y)


# ---------------------------------------------------------------------------
# Orb class
# ---------------------------------------------------------------------------
class Orb:
    def __init__(self, x, y, dx, dy):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.bounces = 0
        self.alive = True

    def update(self, walls):
        """Move the orb and check for wall collisions. Returns points earned."""
        points = 0
        self.x += self.dx
        self.y += self.dy

        # Check wall collisions
        for wall in walls:
            pts = self._collide_wall(wall)
            if pts:
                points += pts

        # Check if off screen (with margin)
        margin = 50
        if (self.x < -margin or self.x > SCREEN_W + margin
                or self.y < UI_BAR_H - margin or self.y > SCREEN_H + margin):
            self.alive = False

        if self.bounces >= ORB_MAX_BOUNCES:
            self.alive = False

        return points

    def _collide_wall(self, wall):
        """Check and resolve collision with a wall segment. Returns 1 if bounced."""
        (x1, y1), (x2, y2) = wall

        # Represent wall as a line segment, find closest point on segment to orb
        wx = x2 - x1
        wy = y2 - y1
        seg_len_sq = wx * wx + wy * wy
        if seg_len_sq == 0:
            return 0

        t = max(0, min(1, ((self.x - x1) * wx + (self.y - y1) * wy) / seg_len_sq))
        closest_x = x1 + t * wx
        closest_y = y1 + t * wy

        dx = self.x - closest_x
        dy = self.y - closest_y
        d = math.hypot(dx, dy)

        if d < ORB_RADIUS + WALL_THICKNESS / 2 and d > 0:
            # Normal vector from wall to orb
            nx = dx / d
            ny = dy / d

            # Reflect velocity
            dot = self.dx * nx + self.dy * ny
            if dot < 0:  # only bounce if moving toward wall
                self.dx -= 2 * dot * nx
                self.dy -= 2 * dot * ny

                # Push orb out of wall
                overlap = ORB_RADIUS + WALL_THICKNESS / 2 - d
                self.x += nx * overlap
                self.y += ny * overlap

                self.bounces += 1
                return 1
        return 0

    def draw(self, surface):
        # Fade orb color as bounces increase
        fade = max(0, 1 - self.bounces / (ORB_MAX_BOUNCES + 1))
        color = (
            int(ORB_COLOR[0] * fade),
            int(ORB_COLOR[1] * fade),
            int(ORB_COLOR[2] * fade + 80 * (1 - fade)),
        )
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), ORB_RADIUS)
        # glow
        glow_surf = pygame.Surface((ORB_RADIUS * 4, ORB_RADIUS * 4), pygame.SRCALPHA)
        pygame.draw.circle(
            glow_surf,
            (color[0], color[1], color[2], 40),
            (ORB_RADIUS * 2, ORB_RADIUS * 2),
            ORB_RADIUS * 2,
        )
        surface.blit(
            glow_surf,
            (int(self.x) - ORB_RADIUS * 2, int(self.y) - ORB_RADIUS * 2),
        )


# ---------------------------------------------------------------------------
# Game class
# ---------------------------------------------------------------------------
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Idle Cannon")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("monospace", 20, bold=True)
        self.font_sm = pygame.font.SysFont("monospace", 15)
        self.font_lg = pygame.font.SysFont("monospace", 28, bold=True)

        self.grid_dots = grid_dots(SCREEN_W, SCREEN_H)

        self.reset()

    def reset(self):
        self.score = 0
        self.orbs = []
        self.walls = []
        self.cannon_x = SCREEN_W // 2
        self.cannon_y = SCREEN_H // 2
        self.cannon_angle = 0

        # Wall placement state
        self.wall_start = None  # first grid dot clicked

        # UI state
        self.shop_open = False
        self.menu_open = False
        self.shop_scroll = 0

        # Cannon placement mode
        self.placing_cannon = False

        # Auto-fire state
        self.autofire_enabled = False
        self.autofire_timer = 0.0
        self.autofire_base_delay = 10.0  # 10 seconds base

        # Upgrade levels (how many times each upgrade has been purchased)
        self.upgrade_levels = {
            "Auto-Fire": 0,
        }

        # Shop items
        self.shop_items = [
            {
                "name": "Auto-Fire",
                "desc": "Reduce fire delay by 10%",
                "base_cost": BASE_UPGRADE_COST,
            },
        ]

    def _get_upgrade_cost(self, item):
        """Calculate the cost for the next level of an upgrade."""
        level = self.upgrade_levels.get(item["name"], 0)
        return item["base_cost"] * (COST_MULTIPLIER ** level)

    def _get_autofire_delay(self):
        """Get current auto-fire delay based on upgrade level."""
        level = self.upgrade_levels.get("Auto-Fire", 0)
        delay = self.autofire_base_delay * (0.9 ** level)
        return delay

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        # Close any open panel, or quit
                        if self.placing_cannon:
                            self.placing_cannon = False
                        elif self.shop_open:
                            self.shop_open = False
                        elif self.menu_open:
                            self.menu_open = False
                        else:
                            running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._handle_click(event, mouse_pos)
                elif event.type == pygame.MOUSEWHEEL:
                    if self.shop_open:
                        self.shop_scroll -= event.y * 30
                        self.shop_scroll = max(0, self.shop_scroll)

            # Update cannon angle toward mouse (only when not placing)
            if not self.placing_cannon:
                mx, my = mouse_pos
                dx = mx - self.cannon_x
                dy = my - self.cannon_y
                self.cannon_angle = math.atan2(dy, dx)

            # Auto-fire logic
            if self.autofire_enabled and self.upgrade_levels.get("Auto-Fire", 0) > 0:
                self.autofire_timer += dt
                delay = self._get_autofire_delay()
                if self.autofire_timer >= delay:
                    self.autofire_timer -= delay
                    self._fire_cannon()

            # Update orbs
            for orb in self.orbs:
                pts = orb.update(self.walls)
                self.score += pts
            self.orbs = [o for o in self.orbs if o.alive]

            # Draw
            self._draw(mouse_pos)
            pygame.display.flip()

        pygame.quit()
        sys.exit()

    # -- Input handling -------------------------------------------------------
    def _handle_click(self, event, pos):
        # Left click
        if event.button == 1:
            # Check bottom bar clicks first (auto-fire toggle)
            if self._click_bottom_bar(pos):
                return

            # Check UI clicks first
            if self._click_ui(pos):
                return

            # If shop is open, handle shop clicks or close
            if self.shop_open:
                if pos[0] >= SCREEN_W - SHOP_W:
                    self._click_shop_item(pos)
                else:
                    self.shop_open = False
                return
            if self.menu_open:
                if not self._in_menu_area(pos):
                    self.menu_open = False
                return

            # Cannon placement mode
            if self.placing_cannon:
                if pos[1] > UI_BAR_H and pos[1] < SCREEN_H - BOTTOM_BAR_H:
                    self._try_place_cannon(pos)
                return

            # Check if clicking on a grid dot for wall placement
            if event.button == 1 and pos[1] > UI_BAR_H and pos[1] < SCREEN_H - BOTTOM_BAR_H:
                snapped = snap_to_grid(pos)
                if dist(pos, snapped) < GRID_DOT_RADIUS + 14:
                    # Valid grid dot click
                    if snapped[1] >= UI_BAR_H + GRID_SPACING and snapped[0] >= GRID_SPACING:
                        if self.wall_start is None:
                            self.wall_start = snapped
                        else:
                            self._try_place_wall(snapped)
                        return

            # Otherwise, fire cannon
            if pos[1] > UI_BAR_H and pos[1] < SCREEN_H - BOTTOM_BAR_H:
                self._fire_cannon()

        # Right click cancels wall placement
        elif event.button == 3:
            self.wall_start = None

    def _click_ui(self, pos):
        """Handle clicks on the top UI bar. Returns True if consumed."""
        if pos[1] > UI_BAR_H:
            return False

        # Menu button (top-left)
        if pos[0] < 100:
            self.menu_open = not self.menu_open
            self.shop_open = False
            return True

        # Cannon placement button (next to menu)
        cannon_btn_rect = pygame.Rect(100, 8, 42, 32)
        if cannon_btn_rect.collidepoint(pos):
            self.placing_cannon = not self.placing_cannon
            self.wall_start = None
            return True

        # Shop button (top-right)
        if pos[0] > SCREEN_W - 100:
            self.shop_open = not self.shop_open
            self.menu_open = False
            return True

        return False

    def _click_bottom_bar(self, pos):
        """Handle clicks on the bottom bar. Returns True if consumed."""
        if pos[1] < SCREEN_H - BOTTOM_BAR_H:
            return False

        # Auto-fire toggle button
        autofire_rect = pygame.Rect(SCREEN_W // 2 - 70, SCREEN_H - BOTTOM_BAR_H + 8, 140, 32)
        if autofire_rect.collidepoint(pos):
            if self.upgrade_levels.get("Auto-Fire", 0) > 0:
                self.autofire_enabled = not self.autofire_enabled
                if self.autofire_enabled:
                    self.autofire_timer = 0.0
            return True

        return False

    def _in_menu_area(self, pos):
        """Check if pos is inside the menu dropdown area."""
        return pos[0] < 180 and pos[1] < UI_BAR_H + 120

    def _click_menu(self, pos):
        """Handle clicks inside the menu dropdown."""
        if pos[1] > UI_BAR_H and pos[1] < UI_BAR_H + 50 and pos[0] < 180:
            self.reset()
            return True
        return False

    def _fire_cannon(self):
        dx = math.cos(self.cannon_angle) * ORB_SPEED
        dy = math.sin(self.cannon_angle) * ORB_SPEED
        # Spawn orb at the tip of the barrel
        spawn_x = self.cannon_x + math.cos(self.cannon_angle) * (CANNON_BARREL_LEN + ORB_RADIUS + 2)
        spawn_y = self.cannon_y + math.sin(self.cannon_angle) * (CANNON_BARREL_LEN + ORB_RADIUS + 2)
        self.orbs.append(Orb(spawn_x, spawn_y, dx, dy))

    def _try_place_cannon(self, pos):
        """Place the cannon in the center of the cell the user clicked."""
        cell = get_cell_at_pos(pos)
        if cell is None:
            return

        # Check that this cell is not enclosed
        enclosed = find_enclosed_cells(self.walls)
        if cell in enclosed:
            return

        cx, cy = cell_center(cell[0], cell[1])
        self.cannon_x = cx
        self.cannon_y = cy
        self.placing_cannon = False

    def _try_place_wall(self, end_dot):
        start = self.wall_start
        self.wall_start = None

        if start == end_dot:
            return

        if not walls_are_axis_aligned(start, end_dot):
            return

        if not walls_are_adjacent(start, end_dot):
            return

        # Check for duplicate
        for w in self.walls:
            if (w[0] == start and w[1] == end_dot) or (w[0] == end_dot and w[1] == start):
                return

        # Check enclosed box - allow enclosing as long as cannon isn't inside
        new_wall = (start, end_dot)
        cannon_pos = (self.cannon_x, self.cannon_y)
        if would_enclose(self.walls, new_wall, cannon_pos):
            return

        self.walls.append(new_wall)

    def _click_shop_item(self, pos):
        """Handle clicking on a shop item to purchase it."""
        panel_x = SCREEN_W - SHOP_W
        item_h = 64
        padding = 8
        for i, item in enumerate(self.shop_items):
            item_y = UI_BAR_H + 52 + i * (item_h + padding) - self.shop_scroll
            item_rect = pygame.Rect(panel_x + padding, item_y, SHOP_W - padding * 2, item_h)
            if item_rect.collidepoint(pos):
                self._try_buy_upgrade(item)
                return

    def _try_buy_upgrade(self, item):
        """Attempt to purchase an upgrade."""
        cost = self._get_upgrade_cost(item)
        if self.score >= cost:
            self.score -= cost
            self.upgrade_levels[item["name"]] = self.upgrade_levels.get(item["name"], 0) + 1
            return True
        return False

    # -- Drawing --------------------------------------------------------------
    def _draw(self, mouse_pos):
        self.screen.fill(BG_COLOR)

        # Draw grid dots
        for dot in self.grid_dots:
            color = GRID_COLOR
            # Highlight dot near mouse if placing wall
            if (not self.placing_cannon
                    and dist(mouse_pos, dot) < GRID_DOT_RADIUS + 14
                    and mouse_pos[1] > UI_BAR_H
                    and mouse_pos[1] < SCREEN_H - BOTTOM_BAR_H):
                color = (120, 120, 140)
            pygame.draw.circle(self.screen, color, dot, GRID_DOT_RADIUS)

        # Draw enclosed cells with a subtle fill
        enclosed = find_enclosed_cells(self.walls)
        for (r, c) in enclosed:
            cx, cy = cell_center(r, c)
            rect = pygame.Rect(
                cx - GRID_SPACING // 2 + 1,
                cy - GRID_SPACING // 2 + 1,
                GRID_SPACING - 2,
                GRID_SPACING - 2,
            )
            fill_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            fill_surf.fill((80, 140, 220, 20))
            self.screen.blit(fill_surf, rect.topleft)

        # Draw walls
        for wall in self.walls:
            pygame.draw.line(self.screen, WALL_COLOR, wall[0], wall[1], WALL_THICKNESS)
            # Draw dots at endpoints slightly brighter
            pygame.draw.circle(self.screen, (200, 200, 220), wall[0], GRID_DOT_RADIUS + 1)
            pygame.draw.circle(self.screen, (200, 200, 220), wall[1], GRID_DOT_RADIUS + 1)

        # Draw wall placement preview
        if self.wall_start is not None and not self.placing_cannon:
            pygame.draw.circle(self.screen, UI_ACCENT, self.wall_start, GRID_DOT_RADIUS + 3)
            snapped_mouse = snap_to_grid(mouse_pos)
            if (snapped_mouse != self.wall_start
                    and walls_are_axis_aligned(self.wall_start, snapped_mouse)
                    and walls_are_adjacent(self.wall_start, snapped_mouse)):
                preview_color = (100, 200, 100)
                new_wall = (self.wall_start, snapped_mouse)
                cannon_pos = (self.cannon_x, self.cannon_y)
                if would_enclose(self.walls, new_wall, cannon_pos):
                    preview_color = (200, 80, 80)
                pygame.draw.line(
                    self.screen, preview_color,
                    self.wall_start, snapped_mouse, WALL_THICKNESS
                )

        # Cannon placement preview
        if self.placing_cannon and mouse_pos[1] > UI_BAR_H and mouse_pos[1] < SCREEN_H - BOTTOM_BAR_H:
            cell = get_cell_at_pos(mouse_pos)
            if cell is not None:
                cx, cy = cell_center(cell[0], cell[1])
                valid = cell not in enclosed
                # Draw a ghost cannon at the cell center
                ghost_color = (100, 200, 100, 80) if valid else (200, 80, 80, 80)
                ghost_surf = pygame.Surface((CANNON_RADIUS * 2 + 4, CANNON_RADIUS * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(
                    ghost_surf, ghost_color,
                    (CANNON_RADIUS + 2, CANNON_RADIUS + 2), CANNON_RADIUS
                )
                self.screen.blit(ghost_surf, (cx - CANNON_RADIUS - 2, cy - CANNON_RADIUS - 2))
                # Highlight the cell
                rect = pygame.Rect(
                    cx - GRID_SPACING // 2 + 1,
                    cy - GRID_SPACING // 2 + 1,
                    GRID_SPACING - 2,
                    GRID_SPACING - 2,
                )
                highlight_color = (100, 200, 100, 30) if valid else (200, 80, 80, 30)
                hl_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                hl_surf.fill(highlight_color)
                self.screen.blit(hl_surf, rect.topleft)

        # Draw orbs
        for orb in self.orbs:
            orb.draw(self.screen)

        # Draw cannon
        self._draw_cannon()

        # Draw UI bar
        self._draw_ui(mouse_pos)

        # Draw bottom bar
        self._draw_bottom_bar(mouse_pos)

        # Draw shop panel
        if self.shop_open:
            self._draw_shop(mouse_pos)

        # Draw menu dropdown
        if self.menu_open:
            self._draw_menu(mouse_pos)

    def _draw_cannon(self):
        cx, cy = self.cannon_x, self.cannon_y

        # Barrel
        end_x = cx + math.cos(self.cannon_angle) * CANNON_BARREL_LEN
        end_y = cy + math.sin(self.cannon_angle) * CANNON_BARREL_LEN
        pygame.draw.line(
            self.screen, CANNON_BARREL_COLOR,
            (cx, cy), (int(end_x), int(end_y)),
            CANNON_BARREL_W,
        )

        # Base circle
        pygame.draw.circle(self.screen, CANNON_COLOR, (cx, cy), CANNON_RADIUS)
        pygame.draw.circle(self.screen, CANNON_BARREL_COLOR, (cx, cy), CANNON_RADIUS, 3)

        # Inner detail
        pygame.draw.circle(self.screen, (120, 120, 140), (cx, cy), 8)

    def _draw_ui(self, mouse_pos):
        # Top bar background
        pygame.draw.rect(self.screen, UI_BG, (0, 0, SCREEN_W, UI_BAR_H))
        pygame.draw.line(self.screen, (50, 50, 65), (0, UI_BAR_H), (SCREEN_W, UI_BAR_H), 2)

        # Menu button (top-left)
        menu_rect = pygame.Rect(8, 8, 84, 32)
        menu_hover = menu_rect.collidepoint(mouse_pos)
        color = UI_BUTTON_HOVER if menu_hover else UI_BUTTON_BG
        pygame.draw.rect(self.screen, color, menu_rect, border_radius=6)
        pygame.draw.rect(self.screen, UI_ACCENT, menu_rect, 2, border_radius=6)
        menu_text = self.font_sm.render("MENU", True, UI_TEXT)
        self.screen.blit(menu_text, (menu_rect.centerx - menu_text.get_width() // 2,
                                      menu_rect.centery - menu_text.get_height() // 2))

        # Cannon placement button (next to menu)
        cannon_btn_rect = pygame.Rect(100, 8, 42, 32)
        cannon_hover = cannon_btn_rect.collidepoint(mouse_pos)
        if self.placing_cannon:
            btn_bg = UI_ACCENT
        elif cannon_hover:
            btn_bg = UI_BUTTON_HOVER
        else:
            btn_bg = UI_BUTTON_BG
        pygame.draw.rect(self.screen, btn_bg, cannon_btn_rect, border_radius=6)
        border_color = (100, 200, 100) if self.placing_cannon else UI_ACCENT
        pygame.draw.rect(self.screen, border_color, cannon_btn_rect, 2, border_radius=6)

        # Draw mini cannon icon inside button
        bcx = cannon_btn_rect.centerx
        bcy = cannon_btn_rect.centery
        mini_r = 8
        pygame.draw.circle(self.screen, CANNON_COLOR, (bcx, bcy), mini_r)
        pygame.draw.circle(self.screen, CANNON_BARREL_COLOR, (bcx, bcy), mini_r, 2)
        pygame.draw.line(self.screen, CANNON_BARREL_COLOR, (bcx, bcy), (bcx + 12, bcy), 4)
        pygame.draw.circle(self.screen, (120, 120, 140), (bcx, bcy), 3)

        # Score (top-center)
        score_text = self.font_lg.render(f"Score: {self.score}", True, UI_TEXT)
        self.screen.blit(score_text, (SCREEN_W // 2 - score_text.get_width() // 2, 10))

        # Shop button (top-right)
        shop_rect = pygame.Rect(SCREEN_W - 92, 8, 84, 32)
        shop_hover = shop_rect.collidepoint(mouse_pos)
        color = UI_BUTTON_HOVER if shop_hover else UI_BUTTON_BG
        pygame.draw.rect(self.screen, color, shop_rect, border_radius=6)
        pygame.draw.rect(self.screen, UI_ACCENT, shop_rect, 2, border_radius=6)
        shop_text = self.font_sm.render("SHOP", True, UI_TEXT)
        self.screen.blit(shop_text, (shop_rect.centerx - shop_text.get_width() // 2,
                                      shop_rect.centery - shop_text.get_height() // 2))

    def _draw_bottom_bar(self, mouse_pos):
        """Draw the bottom bar with auto-fire toggle."""
        bar_y = SCREEN_H - BOTTOM_BAR_H
        pygame.draw.rect(self.screen, UI_BG, (0, bar_y, SCREEN_W, BOTTOM_BAR_H))
        pygame.draw.line(self.screen, (50, 50, 65), (0, bar_y), (SCREEN_W, bar_y), 2)

        has_autofire = self.upgrade_levels.get("Auto-Fire", 0) > 0
        autofire_rect = pygame.Rect(SCREEN_W // 2 - 70, bar_y + 8, 140, 32)
        hover = autofire_rect.collidepoint(mouse_pos)

        if not has_autofire:
            # Grayed out - not yet purchased
            bg = (35, 35, 45)
            text_color = (80, 80, 90)
        elif self.autofire_enabled:
            bg = (40, 120, 60)
            text_color = UI_TEXT
        elif hover:
            bg = UI_BUTTON_HOVER
            text_color = UI_TEXT
        else:
            bg = UI_BUTTON_BG
            text_color = UI_TEXT

        pygame.draw.rect(self.screen, bg, autofire_rect, border_radius=6)
        border = (40, 120, 60) if self.autofire_enabled else (70, 70, 90) if not has_autofire else UI_ACCENT
        pygame.draw.rect(self.screen, border, autofire_rect, 2, border_radius=6)

        label = "AUTO-FIRE"
        if has_autofire and self.autofire_enabled:
            delay = self._get_autofire_delay()
            label = f"AUTO: {delay:.1f}s"
        af_text = self.font_sm.render(label, True, text_color)
        self.screen.blit(af_text, (autofire_rect.centerx - af_text.get_width() // 2,
                                    autofire_rect.centery - af_text.get_height() // 2))

    def _draw_shop(self, mouse_pos):
        panel_x = SCREEN_W - SHOP_W
        panel_rect = pygame.Rect(panel_x, UI_BAR_H, SHOP_W, SCREEN_H - UI_BAR_H - BOTTOM_BAR_H)

        # Background
        pygame.draw.rect(self.screen, SHOP_BG, panel_rect)
        pygame.draw.line(self.screen, (50, 50, 65), (panel_x, UI_BAR_H), (panel_x, SCREEN_H - BOTTOM_BAR_H), 2)

        # Title
        title = self.font.render("UPGRADES", True, UI_TEXT)
        self.screen.blit(title, (panel_x + SHOP_W // 2 - title.get_width() // 2, UI_BAR_H + 12))

        # Scrollable item list
        clip_rect = pygame.Rect(panel_x, UI_BAR_H + 44, SHOP_W, SCREEN_H - UI_BAR_H - BOTTOM_BAR_H - 44)
        self.screen.set_clip(clip_rect)

        item_h = 64
        padding = 8
        max_scroll = max(0, len(self.shop_items) * (item_h + padding) - clip_rect.height + padding)
        self.shop_scroll = min(self.shop_scroll, max_scroll)

        for i, item in enumerate(self.shop_items):
            item_y = UI_BAR_H + 52 + i * (item_h + padding) - self.shop_scroll
            item_rect = pygame.Rect(panel_x + padding, item_y, SHOP_W - padding * 2, item_h)

            if item_rect.bottom < clip_rect.top or item_rect.top > clip_rect.bottom:
                continue

            hover = item_rect.collidepoint(mouse_pos) and self.shop_open
            bg = SHOP_ITEM_HOVER if hover else SHOP_ITEM_BG
            pygame.draw.rect(self.screen, bg, item_rect, border_radius=8)
            pygame.draw.rect(self.screen, (70, 70, 90), item_rect, 1, border_radius=8)

            # Item name + level
            level = self.upgrade_levels.get(item["name"], 0)
            name_str = f"{item['name']}"
            if level > 0:
                name_str += f" (Lv {level})"
            name_text = self.font_sm.render(name_str, True, UI_TEXT)
            self.screen.blit(name_text, (item_rect.x + 12, item_rect.y + 8))

            # Item description
            desc_text = self.font_sm.render(item["desc"], True, (150, 150, 170))
            self.screen.blit(desc_text, (item_rect.x + 12, item_rect.y + 28))

            # Cost
            cost = self._get_upgrade_cost(item)
            can_afford = self.score >= cost
            cost_color = UI_ACCENT if can_afford else (120, 60, 60)
            cost_text = self.font_sm.render(f"{cost} pts", True, cost_color)
            self.screen.blit(cost_text, (item_rect.right - cost_text.get_width() - 12, item_rect.y + 8))

        self.screen.set_clip(None)

        # Scroll indicator
        if max_scroll > 0:
            scroll_frac = self.shop_scroll / max_scroll if max_scroll > 0 else 0
            indicator_h = max(20, clip_rect.height * clip_rect.height
                              / (len(self.shop_items) * (item_h + padding)))
            indicator_y = clip_rect.y + scroll_frac * (clip_rect.height - indicator_h)
            pygame.draw.rect(
                self.screen, (80, 80, 100),
                (panel_x + SHOP_W - 6, int(indicator_y), 4, int(indicator_h)),
                border_radius=2,
            )

    def _draw_menu(self, mouse_pos):
        menu_rect = pygame.Rect(8, UI_BAR_H + 4, 170, 50)
        pygame.draw.rect(self.screen, MENU_BG, menu_rect, border_radius=8)
        pygame.draw.rect(self.screen, (50, 50, 65), menu_rect, 1, border_radius=8)

        # Reset button
        reset_rect = pygame.Rect(16, UI_BAR_H + 12, 154, 34)
        hover = reset_rect.collidepoint(mouse_pos)
        bg = (100, 50, 50) if hover else (70, 40, 40)
        pygame.draw.rect(self.screen, bg, reset_rect, border_radius=6)
        reset_text = self.font_sm.render("Reset Game", True, (220, 120, 120))
        self.screen.blit(reset_text, (reset_rect.centerx - reset_text.get_width() // 2,
                                       reset_rect.centery - reset_text.get_height() // 2))

        # Handle click on reset
        if hover and pygame.mouse.get_pressed()[0]:
            self.menu_open = False
            self.reset()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    game = Game()
    game.run()
