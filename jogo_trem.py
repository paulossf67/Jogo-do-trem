"""
Jogo do Trem: controle uma torre de tanque e impeça o trem de atravessar o segundo túnel.

Controles: mouse move/mira a torre, clique esquerdo atira, P pausa, R reinicia, ESC sai.
"""
import array
import bisect
import math
import os
import random
import sys

import pygame

W, H = 1000, 640
CX, CY = W // 2, 34 + (H - 34) // 2     # centro da tela (onde fica o tanque)
TRACK_R = 200                            # raio da pista circular
IN_ANG = math.radians(-50)               # ângulo do túnel de entrada (o trem gira no sentido horário)
OUT_ANG = math.radians(230)              # ângulo do túnel de saída
TUNNEL_LEN = 140
START_LIVES = 3
MAX_LIVES = 5
BOSS_EVERY = 5         # um chefe a cada N ondas (mais chefes nas ondas seguintes)
WEAPON_TIME = 8.0
BLAST_R = 85           # raio da explosão do míssil

FIRE_DELAY = 0.25
FIRE_DELAY_RAPID = 0.12
RAPID_TIME = 3.0
HEAVY_TIME = 5.0
POWERUP_CHANCE = 0.25
POWERUP_SPEED = 60       # px/s em direção ao tanque; some ao alcançá-lo
COMBO_WINDOW = 2.0     # segundos para encadear a próxima destruição

# tipo: (vida, pontos, largura, altura, cor, nome)
CAR_TYPES = {
    "locomotiva": (2, 50, 90, 50, (200, 40, 40), "Locomotiva"),
    "carga": (1, 10, 70, 44, (230, 140, 40), "Carga"),
    "tanque": (2, 15, 70, 44, (215, 175, 40), "Tanque"),
    "blindado": (3, 25, 70, 44, (130, 135, 145), "Blindado"),
    "passageiro": (1, 10, 70, 44, (60, 130, 210), "Passageiro"),
    "chefe": (15, 300, 130, 64, (90, 30, 120), "Chefe"),
}
CAR_SPACING = 12

POWERUPS = {
    "rapidez": ((60, 140, 255), "R"),
    "pesado": ((230, 60, 60), "P"),
    "escudo": ((60, 200, 90), "E"),
    "espalhar": ((255, 150, 40), "L"),
    "perfurante": ((60, 220, 220), "F"),
    "missil": ((200, 80, 220), "M"),
}
WEAPON_NAMES = {"espalhar": "LEQUE", "perfurante": "PERFURANTE", "missil": "MÍSSIL"}
POWERUP_MIN_WAVE = {"espalhar": 2, "perfurante": 3, "missil": 4}   # onda em que cada arma passa a aparecer


RECORD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recorde.txt")


def load_record():
    try:
        with open(RECORD_FILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def save_record(value):
    try:
        with open(RECORD_FILE, "w", encoding="utf-8") as f:
            f.write(str(value))
    except OSError:
        pass


def make_sound(freq, dur, noise=0.0, slide=0.0, vol=0.35):
    """Gera um efeito sonoro simples (onda quadrada + ruído com decaimento)."""
    rate = 22050
    n = int(rate * dur)
    buf = array.array("h")
    phase = 0.0
    for i in range(n):
        k = 1 - i / n
        phase += (freq + slide * i / n) / rate
        wave = 1.0 if (phase % 1) < 0.5 else -1.0
        val = ((1 - noise) * wave + noise * random.uniform(-1, 1)) * k * vol
        buf.append(int(val * 32767))
    return pygame.mixer.Sound(buffer=buf.tobytes())


PAD = 30
_sprites = {}


class Track:
    """Pista fechada em volta do tanque; a forma muda a cada onda.

    O raio varia com o ângulo: rho = 1 + a*cos(k*ang + fase), esticado na horizontal por 'stretch'.
    """

    def __init__(self, a, k, phase, stretch):
        ry = TRACK_R / (1 + a)
        rx = ry * stretch
        n = 720
        self.pts = []
        for i in range(n + 1):
            th = IN_ANG + (OUT_ANG - IN_ANG) * i / n
            rho = 1 + a * math.cos(k * th + phase)
            self.pts.append((CX + rx * rho * math.cos(th), CY + ry * rho * math.sin(th)))
        self.cum = [0.0]
        for (x0, y0), (x1, y1) in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + math.hypot(x1 - x0, y1 - y0))
        self.length = self.cum[-1]

    def point(self, s, radial=0.0):
        last = len(self.pts) - 2
        if s <= 0:                       # antes do túnel de entrada: prolonga a primeira reta
            i = 0
        elif s >= self.length:           # dentro do túnel de saída: prolonga a última
            i = last
        else:
            i = min(bisect.bisect_right(self.cum, s) - 1, last)
        d = s - self.cum[i]
        (x0, y0), (x1, y1) = self.pts[i], self.pts[i + 1]
        seg = self.cum[i + 1] - self.cum[i]
        tx, ty = (x1 - x0) / seg, (y1 - y0) / seg
        nx, ny = ty, -tx                 # normal para fora (o trem gira no sentido horário)
        return (x0 + tx * d + nx * radial, y0 + ty * d + ny * radial,
                math.atan2(ty, tx) - math.pi / 2)


_track = Track(0, 2, 0.0, 1.0)
TRACK_LEN = _track.length


def set_track(wave):
    global _track, TRACK_LEN
    if wave <= 1:
        _track = Track(0, 2, 0.0, 1.0)
    else:
        a = min(0.05 * (wave - 1), 0.22) * random.uniform(0.6, 1.0)
        k = random.choice([2, 3, 4] if wave < 6 else [2, 3, 4, 5])
        stretch = 1 + random.uniform(0.1, 0.2) * min(wave - 1, 3)
        _track = Track(a, k, random.uniform(0, math.tau), stretch)
    TRACK_LEN = _track.length


def track_point(s, radial=0.0):
    """Posição (x, y) e ângulo na pista para a distância s percorrida; radial afasta do centro."""
    return _track.point(s, radial)


def car_sprite(kind, flash):
    """Vagão desenhado na horizontal (frente à direita, topo para fora da pista)."""
    key = (kind, flash)
    if key in _sprites:
        return _sprites[key]
    _, _, w, h, base, _ = CAR_TYPES[kind]
    surf = pygame.Surface((w + 2 * PAD, h + 2 * PAD), pygame.SRCALPHA)
    r = pygame.Rect(PAD, PAD, w, h)
    color = (255, 255, 255) if flash else base
    pygame.draw.rect(surf, color, r, border_radius=6)
    pygame.draw.rect(surf, (30, 30, 30), r, 2, border_radius=6)
    if kind == "locomotiva":
        pygame.draw.rect(surf, (150, 25, 25), (r.x + 50, r.y - 14, 32, 14))       # cabine
        pygame.draw.rect(surf, (200, 230, 255), (r.x + 56, r.y - 10, 20, 8))      # janela
        pygame.draw.rect(surf, (40, 40, 40), (r.x + 8, r.y - 12, 12, 14))         # chaminé
        pygame.draw.circle(surf, (255, 240, 120), (r.right - 4, r.y + 18), 5)     # farol
    elif kind == "tanque":
        pygame.draw.ellipse(surf, (240, 205, 90), r.inflate(-10, -12))
        pygame.draw.ellipse(surf, (30, 30, 30), r.inflate(-10, -12), 2)
    elif kind == "blindado":
        for i in range(3):
            pygame.draw.line(surf, (80, 85, 95), (r.x + 8, r.y + 10 + i * 12), (r.right - 8, r.y + 10 + i * 12), 3)
    elif kind == "passageiro":
        for i in range(3):
            pygame.draw.rect(surf, (210, 235, 255), (r.x + 8 + i * 20, r.y + 8, 14, 14))
    elif kind == "chefe":
        for i in range(5):
            pygame.draw.polygon(surf, (255, 210, 40), [(r.x + 10 + i * 22, r.bottom - 4), (r.x + 22 + i * 22, r.y + 8),
                                                        (r.x + 32 + i * 22, r.bottom - 4)])
        pygame.draw.circle(surf, (255, 60, 60), (r.centerx, r.y + 18), 9)
        pygame.draw.circle(surf, (20, 0, 0), (r.centerx, r.y + 18), 4)
    elif kind == "carga":
        pygame.draw.line(surf, (150, 85, 20), (r.centerx, r.y), (r.centerx, r.bottom), 3)
    wheels = (r.x + 14, r.x + 46, r.right - 46, r.right - 14) if kind == "chefe" else (r.x + 14, r.centerx, r.right - 14)
    for wx in wheels:
        pygame.draw.circle(surf, (25, 25, 25), (wx, r.bottom + 4), 7)
        pygame.draw.circle(surf, (120, 120, 120), (wx, r.bottom + 4), 3)
    _sprites[key] = surf
    return surf


class Car:
    def __init__(self, kind, s, hp_bonus=0):
        self.kind = kind
        self.hp, self.points, self.w, self.h, self.color, _ = CAR_TYPES[kind]
        self.hp += hp_bonus
        self.max_hp = self.hp
        self.s = s          # posição do centro ao longo da pista (px)
        self.flash = 0.0

    def _center(self):
        return track_point(self.s, self.h / 2 + 4)

    @property
    def pos(self):
        x, y, _ = self._center()
        return x, y

    @property
    def on_track(self):
        """Já saiu do túnel de entrada e ainda não chegou ao de saída."""
        return self.s + self.w / 2 > 0 and self.s < TRACK_LEN

    def hit_test(self, px, py, margin=4):
        cx, cy, ang = self._center()
        dx, dy = px - cx, py - cy
        along = -dx * math.sin(ang) + dy * math.cos(ang)      # ao longo da pista
        radial = dx * math.cos(ang) + dy * math.sin(ang)      # para fora da pista
        return abs(along) <= self.w / 2 + margin and abs(radial) <= self.h / 2 + margin

    def draw(self, surf):
        if self.s + self.w / 2 <= 0:
            return
        cx, cy, ang = self._center()
        sprite = pygame.transform.rotate(car_sprite(self.kind, self.flash > 0), -(math.degrees(ang) + 90))
        surf.blit(sprite, sprite.get_rect(center=(cx, cy)))
        if self.max_hp > 1 and self.on_track:
            bw = self.w - 8
            bx, by = int(cx - bw / 2), int(cy - self.h / 2 - 26)
            pygame.draw.rect(surf, (60, 0, 0), (bx, by, bw, 4))
            pygame.draw.rect(surf, (80, 230, 80), (bx, by, bw * self.hp / self.max_hp, 4))


class Bullet:
    def __init__(self, x, y, angle, damage, pierce=False, blast=False):
        self.x, self.y = x, y
        self.vx = math.cos(angle) * 750
        self.vy = math.sin(angle) * 750
        self.damage = damage
        self.pierce = pierce      # atravessa os vagões
        self.blast = blast        # explode em área
        self.hit = set()          # vagões já atingidos (para o tiro perfurante não repetir dano)
        self.alive = True

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        if not (-20 < self.x < W + 20 and -20 < self.y < H + 20):
            self.alive = False

    @property
    def rect(self):
        return pygame.Rect(int(self.x) - 4, int(self.y) - 4, 8, 8)

    def draw(self, surf):
        if self.pierce:
            tail = (int(self.x - self.vx * 0.03), int(self.y - self.vy * 0.03))
            pygame.draw.line(surf, (60, 220, 220), tail, (int(self.x), int(self.y)), 5)
            return
        if self.blast:
            color, r = (200, 80, 220), 7
        elif self.damage > 1:
            color, r = (255, 90, 60), 6
        else:
            color, r = (255, 230, 100), 4
        pygame.draw.circle(surf, color, (int(self.x), int(self.y)), r)


class Particle:
    def __init__(self, x, y, color, big):
        ang = random.uniform(0, math.tau)
        spd = random.uniform(60, 320 if big else 220)
        self.x, self.y = x, y
        self.vx, self.vy = math.cos(ang) * spd, math.sin(ang) * spd
        self.life = self.max_life = random.uniform(0.4, 0.9 if big else 0.7)
        self.size = random.uniform(3, 8 if big else 6)
        self.color = random.choice([color, (255, 200, 60), (255, 120, 40)])

    def update(self, dt):
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 300 * dt

    def draw(self, surf):
        k = max(self.life / self.max_life, 0)
        pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), max(int(self.size * k), 1))


class PowerUp:
    def __init__(self, kind, x, y):
        self.kind, self.x, self.y = kind, x, y
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        d = math.hypot(CX - self.x, CY - self.y) or 1.0
        self.x += (CX - self.x) / d * POWERUP_SPEED * dt
        self.y += (CY - self.y) / d * POWERUP_SPEED * dt

    @property
    def rect(self):
        return pygame.Rect(int(self.x) - 16, int(self.y) - 16, 32, 32)

    def draw(self, surf, font):
        color, letter = POWERUPS[self.kind]
        pulse = 2 * math.sin(self.t * 8)
        pygame.draw.circle(surf, color, (int(self.x), int(self.y)), int(16 + pulse))
        pygame.draw.circle(surf, (255, 255, 255), (int(self.x), int(self.y)), int(16 + pulse), 2)
        txt = font.render(letter, True, (255, 255, 255))
        surf.blit(txt, txt.get_rect(center=(int(self.x), int(self.y))))


class Game:
    def __init__(self):
        self.font = pygame.font.SysFont("arial", 20, bold=True)
        self.big = pygame.font.SysFont("arial", 56, bold=True)
        self.small = pygame.font.SysFont("arial", 16)
        self.record = load_record()
        self.sfx = {}
        try:
            self.sfx = {
                "shot": make_sound(500, 0.10, slide=-350),
                "hit": make_sound(220, 0.08, noise=0.5),
                "boom": make_sound(90, 0.35, noise=0.8, slide=-40, vol=0.5),
                "power": make_sound(600, 0.18, slide=700),
                "lose": make_sound(300, 0.5, slide=-250),
                "wave": make_sound(400, 0.3, slide=400),
            }
        except pygame.error:
            pass
        self.reset()
        self.state = "menu"

    def play(self, name):
        snd = self.sfx.get(name)
        if snd:
            snd.play()

    def finish(self, state):
        self.state = state
        if self.score > self.record:
            self.record = self.score
            save_record(self.record)

    # ---------------------------------------------------------------- estado
    def reset(self):
        self.wave = 0
        self.score = 0
        self.lives = START_LIVES
        self.state = "playing"   # playing | banner | won | lost
        self.aim = -math.pi / 2
        self.bullets, self.particles, self.powerups, self.cars = [], [], [], []
        self.cooldown = 0.0
        self.rapid = self.heavy = 0.0
        self.weapon = None       # arma temporária: espalhar | perfurante | missil
        self.weapon_t = 0.0
        self.banner_notes = []
        self.combo = 0
        self.combo_t = 0.0
        self.shake = 0.0
        self.shields = 0
        self.banner_t = 0.0
        self.next_wave()

    def next_wave(self):
        self.wave += 1
        w = self.wave
        n = 8 + 3 * (w - 1)                      # composição cresce a cada onda
        kinds = ["carga", "tanque", "passageiro"]
        if w >= 2:
            kinds.append("blindado")
        if w >= 3:
            kinds += ["blindado", "tanque"]
        if w >= 6:
            kinds += ["blindado", "blindado"]
        self.speed = min(40 + 10 * w, 220)
        bonus = (w - 1) // 4                     # vagões ganham vida com o tempo
        set_track(w)
        bosses = min(w // BOSS_EVERY, 3) if w % BOSS_EVERY == 0 else 0
        self.cars = [Car("locomotiva", 0, bonus)] + [Car(random.choice(kinds), 0, bonus) for _ in range(n - 1)]
        for i in range(bosses):                  # chefes logo atrás da locomotiva
            self.cars[1 + i] = Car("chefe", 0, 5 * (w // BOSS_EVERY - 1))
        pos = 0.0
        for c in self.cars:
            c.s = pos - c.w / 2
            pos -= c.w + CAR_SPACING
        notes = []
        if w >= 2:
            notes.append(("NOVO TRAJETO!", (255, 220, 100)))
        for kind, first in POWERUP_MIN_WAVE.items():
            if first == w:
                notes.append((f"Nova arma disponível: {WEAPON_NAMES[kind]} ({POWERUPS[kind][1]})", POWERUPS[kind][0]))
        if bosses:
            notes.append(("CHEFE À VISTA!" if bosses == 1 else f"{bosses} CHEFES À VISTA!", (255, 120, 120)))
        notes.append((f"{n} vagões", (255, 255, 255)))
        self.banner_notes = notes
        self.bullets.clear()
        self.banner_t = 2.5
        self.state = "banner"

    def powerup_pool(self):
        return [k for k in POWERUPS if POWERUP_MIN_WAVE.get(k, 1) <= self.wave]

    # ---------------------------------------------------------------- lógica
    @property
    def muzzle(self):
        return (CX + math.cos(self.aim) * 56, CY + math.sin(self.aim) * 56)

    def shoot(self):
        if self.state != "playing" or self.cooldown > 0:
            return
        mx, my = self.muzzle
        dmg = 2 if self.heavy > 0 else 1
        angles = (-0.22, 0.0, 0.22) if self.weapon == "espalhar" else (0.0,)
        for da in angles:
            self.bullets.append(Bullet(mx, my, self.aim + da, dmg,
                                       pierce=self.weapon == "perfurante", blast=self.weapon == "missil"))
        self.cooldown = FIRE_DELAY_RAPID if self.rapid > 0 else FIRE_DELAY
        self.play("shot")

    def explode(self, x, y, color, big):
        for _ in range(45 if big else 18):
            self.particles.append(Particle(x, y, color, big))

    def hurt(self, c, dmg, x, y):
        c.hp -= dmg
        c.flash = 0.08
        self.explode(x, y, c.color, False)
        self.play("hit")
        if c.hp <= 0:
            self.kill(c)

    def kill(self, c):
        self.play("boom")
        self.combo += 1
        self.combo_t = COMBO_WINDOW
        self.score += c.points * self.multiplier
        cx, cy = c.pos
        big = c.kind in ("locomotiva", "chefe")
        if big:
            self.shake = 0.35
        self.explode(cx, cy, c.color, big)
        if c.kind == "chefe":
            self.lives = min(self.lives + 1, MAX_LIVES)     # recompensa por derrubar um chefe
        if c.kind == "chefe" or random.random() < POWERUP_CHANCE:
            self.powerups.append(PowerUp(random.choice(self.powerup_pool()), cx, cy))

    def toggle_pause(self):
        if self.state == "playing":
            self.state = "paused"
        elif self.state == "paused":
            self.state = "playing"

    def update(self, dt, mouse):
        if self.state == "paused":
            return
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]

        if self.state == "menu":
            return
        if self.state == "banner":
            self.banner_t -= dt
            if self.banner_t <= 0:
                self.state = "playing"
            return
        if self.state != "playing":
            return

        self.aim = math.atan2(mouse[1] - CY, mouse[0] - CX)

        self.cooldown = max(0.0, self.cooldown - dt)
        self.rapid = max(0.0, self.rapid - dt)
        self.shake = max(0.0, self.shake - dt)
        if self.combo_t > 0:
            self.combo_t -= dt
            if self.combo_t <= 0:
                self.combo = 0
        self.heavy = max(0.0, self.heavy - dt)
        if self.weapon:
            self.weapon_t -= dt
            if self.weapon_t <= 0:
                self.weapon = None

        for c in self.cars:
            c.s += self.speed * dt
            c.flash = max(0.0, c.flash - dt)
        for b in self.bullets:
            b.update(dt)
        for p in self.powerups:
            p.update(dt)
        self.powerups = [p for p in self.powerups if math.hypot(p.x - CX, p.y - CY) > 34]

        # tiros x vagões / power-ups
        for b in self.bullets:
            for c in self.cars:
                if c.hp <= 0 or id(c) in b.hit or not c.on_track or not c.hit_test(b.x, b.y):
                    continue
                b.hit.add(id(c))
                self.hurt(c, b.damage, b.x, b.y)
                if b.blast:
                    self.explode(b.x, b.y, (255, 150, 40), True)
                    self.shake = max(self.shake, 0.15)
                    for o in self.cars:
                        if o is not c and o.hp > 0 and o.on_track:
                            ox, oy = o.pos
                            if math.hypot(ox - b.x, oy - b.y) < BLAST_R:
                                self.hurt(o, b.damage, ox, oy)
                if not b.pierce:
                    b.alive = False
                    break
            if b.alive:
                for pu in self.powerups[:]:
                    if b.rect.colliderect(pu.rect):
                        b.alive = False
                        self.collect(pu)
                        self.powerups.remove(pu)
                        break
        self.bullets = [b for b in self.bullets if b.alive]
        self.cars = [c for c in self.cars if c.hp > 0]

        # vagões que atravessam o segundo túnel
        for c in self.cars[:]:
            if c.s - c.w / 2 >= TRACK_LEN:
                self.cars.remove(c)
                ex, ey, _ = track_point(TRACK_LEN, 40)
                if self.shields > 0:
                    self.shields -= 1
                    self.explode(ex, ey, (60, 200, 90), False)
                else:
                    self.lives -= 1
                    self.explode(ex, ey, (255, 60, 60), False)
                    self.play("lose")
                    if self.lives <= 0:
                        self.finish("lost")
                        return

        if not self.cars:
            self.score += 100 * self.wave  # bônus de onda
            self.play("wave")
            self.next_wave()

    @property
    def multiplier(self):
        return min(1 + self.combo // 3, 5)

    def shake_offset(self):
        if self.shake <= 0:
            return (0, 0)
        amp = 10 * self.shake / 0.35
        return (random.randint(-int(amp), int(amp)), random.randint(-int(amp), int(amp)))

    def collect(self, pu):
        self.play("power")
        if pu.kind == "rapidez":
            self.rapid = RAPID_TIME
        elif pu.kind == "pesado":
            self.heavy = HEAVY_TIME
        elif pu.kind == "escudo":
            self.shields += 1
        else:
            self.weapon = pu.kind
            self.weapon_t = WEAPON_TIME

    # ---------------------------------------------------------------- desenho
    def draw(self, surf, mouse):
        surf.fill((90, 160, 80))
        self.draw_track(surf)
        for c in self.cars:
            c.draw(surf)
        self.draw_tunnel(surf, -TUNNEL_LEN / 2)
        self.draw_tunnel(surf, TRACK_LEN + TUNNEL_LEN / 2)

        for pu in self.powerups:
            pu.draw(surf, self.font)
        for b in self.bullets:
            b.draw(surf)
        for p in self.particles:
            p.draw(surf)
        if self.state in ("playing", "banner", "paused"):
            self.draw_tower(surf, mouse)
        self.draw_hud(surf)

        if self.state == "menu":
            self.overlay_menu(surf)
        elif self.state == "paused":
            self.overlay(surf, "PAUSADO", (255, 255, 255), "P para continuar  |  R reinicia  |  ESC sai")
        elif self.state == "banner":
            self.center_text(surf, f"ONDA {self.wave}", (255, 255, 255), -50)
            for i, (txt, col) in enumerate(self.banner_notes):
                self.center_text(surf, txt, col, 10 + i * 30, small=True)
        elif self.state == "lost":
            self.overlay(surf, "O TREM PASSOU!", (255, 100, 100))

    def draw_track(self, surf):
        n = int(TRACK_LEN / 6)
        pts = [track_point(TRACK_LEN * i / n)[:2] for i in range(n + 1)]
        pygame.draw.lines(surf, (110, 85, 60), False, pts, 30)
        for i in range(0, n + 1, 3):
            x1, y1, _ = track_point(TRACK_LEN * i / n, -14)
            x2, y2, _ = track_point(TRACK_LEN * i / n, 14)
            pygame.draw.line(surf, (75, 55, 35), (x1, y1), (x2, y2), 4)
        for off in (-8, 8):
            rail = [track_point(TRACK_LEN * i / n, off)[:2] for i in range(n + 1)]
            pygame.draw.lines(surf, (60, 60, 60), False, rail, 3)

    def draw_tunnel(self, surf, s):
        tw, th = TUNNEL_LEN, 112
        spr = pygame.Surface((tw, th), pygame.SRCALPHA)
        pygame.draw.rect(spr, (85, 80, 75), (0, 0, tw, th), border_radius=16)
        pygame.draw.rect(spr, (15, 15, 15), (10, 16, tw - 20, th - 26), border_radius=26)
        x, y, ang = track_point(s, 22)
        spr = pygame.transform.rotate(spr, -(math.degrees(ang) + 90))
        surf.blit(spr, spr.get_rect(center=(x, y)))

    def draw_tower(self, surf, mouse):
        # base fixa no centro; só a torre gira
        pygame.draw.circle(surf, (60, 110, 60), (CX, CY), 46)
        hull = pygame.Rect(0, 0, 72, 52)
        hull.center = (CX, CY)
        for side in (-30, 30):
            pygame.draw.rect(surf, (35, 40, 35), (CX + side - 8, CY - 30, 16, 60), border_radius=5)
        pygame.draw.rect(surf, (55, 75, 55), hull, border_radius=8)
        pygame.draw.rect(surf, (25, 35, 25), hull, 2, border_radius=8)
        mx, my = self.muzzle
        pygame.draw.line(surf, (50, 60, 50), (CX, CY), (mx, my), 12)
        pygame.draw.line(surf, (25, 30, 25), (CX, CY), (mx, my), 4)
        pygame.draw.circle(surf, (70, 95, 70), (CX, CY), 22)
        pygame.draw.circle(surf, (25, 35, 25), (CX, CY), 22, 2)
        if self.shields:
            pygame.draw.circle(surf, (60, 200, 90), (CX, CY), 62, 3)
        pygame.draw.circle(surf, (255, 255, 255), mouse, 10, 2)
        pygame.draw.line(surf, (255, 255, 255), (mouse[0] - 14, mouse[1]), (mouse[0] + 14, mouse[1]), 1)
        pygame.draw.line(surf, (255, 255, 255), (mouse[0], mouse[1] - 14), (mouse[0], mouse[1] + 14), 1)

    def draw_hud(self, surf):
        pygame.draw.rect(surf, (20, 25, 35), (0, 0, W, 34))
        surf.blit(self.font.render(f"Pontos: {self.score}  Recorde: {self.record}", True, (255, 255, 255)), (12, 6))
        surf.blit(self.font.render(f"Onda {self.wave}", True, (255, 255, 255)), (W // 2 + 100, 6))
        for i in range(MAX_LIVES):
            col = (255, 80, 80) if i < self.lives else (80, 60, 60)
            pygame.draw.circle(surf, col, (W - 30 - i * 30, 17), 10)
        x = 12
        for label, t, col in (("RAPIDEZ", self.rapid, POWERUPS["rapidez"][0]),
                              ("PESADO", self.heavy, POWERUPS["pesado"][0])):
            if t > 0:
                surf.blit(self.small.render(f"{label} {t:.1f}s", True, col), (x, H - 26))
                x += 120
        if self.weapon:
            surf.blit(self.small.render(f"{WEAPON_NAMES[self.weapon]} {self.weapon_t:.1f}s", True,
                                        POWERUPS[self.weapon][0]), (x, H - 26))
            x += 140
        if self.multiplier > 1:
            col = (255, 220, 80)
            img = self.font.render(f"COMBO x{self.multiplier}", True, col)
            surf.blit(img, (W // 2 - img.get_width() // 2 - 60, 6))
        if self.shields:
            surf.blit(self.small.render(f"ESCUDO x{self.shields}", True, POWERUPS["escudo"][0]), (x, H - 26))

    def center_text(self, surf, text, color, dy, small=False):
        img = (self.font if small else self.big).render(text, True, color)
        surf.blit(img, img.get_rect(center=(W // 2, H // 2 + dy)))

    def overlay_menu(self, surf):
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 160))
        surf.blit(shade, (0, 0))
        self.center_text(surf, "JOGO DO TREM", (255, 220, 100), -130)
        lines = ["Destrua os vagões antes que atravessem o segundo túnel. Jogo sem fim!",
                 "Mouse: mira   |   Clique: atira   |   P: pausa",
                 "Power-ups (atire antes que cheguem ao tanque): R rapidez, P pesado, E escudo",
                 "Armas novas surgem nas ondas seguintes: L leque, F perfurante, M míssil",
                 "Quanto mais joga, mais longo e rápido fica o trem, e a pista muda.",
                 f"Recorde: {self.record}"]
        for i, line in enumerate(lines):
            self.center_text(surf, line, (255, 255, 255), -60 + i * 28, small=True)
        self.center_text(surf, "Clique para começar", (120, 255, 140), 130, small=True)

    def overlay(self, surf, title, color, hint="R para jogar de novo  |  ESC para sair"):
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        surf.blit(shade, (0, 0))
        self.center_text(surf, title, color, -40)
        if self.state != "paused":
            self.center_text(surf, f"Onda {self.wave}  |  Pontuação: {self.score}  |  Recorde: {self.record}",
                             (255, 255, 255), 20, small=True)
        self.center_text(surf, hint, (200, 200, 200), 55, small=True)


def main():
    pygame.init()
    try:
        pygame.mixer.init(22050, -16, 1)
    except pygame.error:
        pass
    screen = pygame.display.set_mode((W, H))
    canvas = pygame.Surface((W, H))
    pygame.display.set_caption("Jogo do Trem")
    clock = pygame.time.Clock()
    game = Game()

    while True:
        dt = min(clock.tick(60) / 1000, 0.05)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                pygame.quit()
                sys.exit()
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_r:
                game.reset()
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_p:
                game.toggle_pause()
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if game.state == "menu":
                    game.state = "banner"
                else:
                    game.shoot()
        mouse = pygame.mouse.get_pos()
        if game.state == "playing" and pygame.mouse.get_pressed()[0]:
            game.shoot()  # segurar o botão mantém o fogo, respeitando o cooldown
        game.update(dt, mouse)
        game.draw(canvas, mouse)
        screen.fill((0, 0, 0))
        screen.blit(canvas, game.shake_offset())
        pygame.display.flip()


if __name__ == "__main__":
    main()
