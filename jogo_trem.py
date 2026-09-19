"""
Jogo do Trem (melhorado): controle uma torre e impeça o trem de atravessar o segundo túnel.

Controles:
  Mouse .......... mira a torre
  Clique / segurar atira
  P .............. pausa
  R .............. reinicia
  1/2/3 .......... escolha de dificuldade no menu
  ESC ............ sai
"""
import array
import json
import math
import os
import random
import sys
from datetime import datetime

import pygame

# ---------------------------------------------------------------------------
# Constantes de tela e geometria da pista
# ---------------------------------------------------------------------------
W, H = 1000, 640                          # largura e altura da janela
CX, CY = W // 2, 34 + (H - 34) // 2       # centro da tela (posição da torre)
TRACK_R = 200                             # raio da pista circular (em pixels)
IN_ANG = math.radians(-50)                # ângulo do túnel de entrada (sentido horário)
OUT_ANG = math.radians(230)               # ângulo do túnel de saída
TRACK_LEN = TRACK_R * (OUT_ANG - IN_ANG)  # comprimento total da pista visível
TUNNEL_LEN = 140                          # comprimento visual de cada túnel
TOTAL_WAVES = 5                           # ondas normais antes do modo Endless
START_LIVES = 3                           # vidas padrão (pode mudar pela dificuldade)

# ---------------------------------------------------------------------------
# Constantes de combate e power-ups
# ---------------------------------------------------------------------------
FIRE_DELAY = 0.25          # intervalo entre tiros normais (segundos)
FIRE_DELAY_RAPID = 0.10    # intervalo com power-up de rapidez
RAPID_TIME = 3.5           # duração do power-up "rapidez"
HEAVY_TIME = 5.5           # duração do power-up "pesado" (tiro com mais dano)
POWERUP_CHANCE = 0.28      # chance base de dropar power-up ao destruir vagão
POWERUP_SPEED = 70         # velocidade com que o power-up voa até a torre (px/s)
COMBO_WINDOW = 2.2         # tempo máximo entre destruições para manter o combo

# tipo: (vida, pontos, largura, altura, cor RGB, nome exibido)
CAR_TYPES = {
    "locomotiva": (2, 50, 90, 50, (200, 40, 40), "Locomotiva"),
    "carga": (1, 10, 70, 44, (230, 140, 40), "Carga"),
    "tanque": (2, 15, 70, 44, (215, 175, 40), "Tanque"),
    "blindado": (3, 25, 70, 44, (130, 135, 145), "Blindado"),
    "passageiro": (1, 10, 70, 44, (60, 130, 210), "Passageiro"),
    "rapido": (1, 20, 58, 36, (40, 200, 180), "Rápido"),      # mais veloz
    "bomba": (2, 30, 64, 48, (180, 50, 20), "Bomba"),         # explode e danifica vizinhos
    "atirador": (2, 35, 68, 44, (160, 60, 200), "Atirador"),  # atira de volta na torre
    "chefe": (18, 400, 140, 68, (90, 30, 120), "Chefe"),       # boss da onda
}
CAR_SPACING = 12  # espaço entre vagões na formação do trem

# Power-ups: (cor RGB, letra exibida no ícone)
POWERUPS = {
    "rapidez": ((60, 140, 255), "R"),      # aumenta cadência de tiro
    "pesado": ((230, 60, 60), "P"),        # tiros causam 2 de dano
    "escudo": ((60, 200, 90), "E"),        # bloqueia uma vida perdida
    "multitiros": ((255, 180, 40), "M"),   # dispara 3 tiros em leque
}

# Configurações por dificuldade
# speed_mul / hp_mul: multiplicadores de velocidade e vida dos vagões
# lives: vidas iniciais | power_chance: chance de dropar power-up
DIFFICULTIES = {
    1: {"name": "Fácil", "speed_mul": 0.85, "hp_mul": 0.8, "lives": 4, "power_chance": 0.35},
    2: {"name": "Normal", "speed_mul": 1.0, "hp_mul": 1.0, "lives": 3, "power_chance": 0.28},
    3: {"name": "Difícil", "speed_mul": 1.2, "hp_mul": 1.25, "lives": 2, "power_chance": 0.20},
}

# ---------------------------------------------------------------------------
# Sistema de save (JSON)
# ---------------------------------------------------------------------------
SAVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "save.json")
# Arquivo antigo de recorde (migração automática se ainda existir)
OLD_RECORD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recorde.txt")

# Estrutura padrão do save — qualquer campo ausente é preenchido com estes valores
DEFAULT_SAVE = {
    "version": 1,
    "high_score": 0,           # maior pontuação de todos os tempos
    "best_wave": 0,            # maior onda alcançada (incluindo Endless)
    "preferred_difficulty": 2, # última dificuldade escolhida (1/2/3)
    "games_played": 0,         # total de partidas iniciadas
    "games_won": 0,            # partidas em que chegou ao Endless
    "cars_destroyed": 0,       # total de vagões destruídos
    "total_score": 0,          # soma de todas as pontuações (estatística)
    "last_played": None,       # data/hora da última partida (ISO)
}


def _migrate_old_record():
    """Se existir o antigo recorde.txt, importa o valor para o novo sistema."""
    try:
        with open(OLD_RECORD_FILE, encoding="utf-8") as f:
            old = int(f.read().strip())
        if old > 0:
            return old
    except (OSError, ValueError):
        pass
    return 0


def load_save():
    """
    Carrega o save do disco.
    - Se save.json não existir, tenta migrar o recorde.txt antigo.
    - Campos faltantes são preenchidos com DEFAULT_SAVE.
    """
    data = dict(DEFAULT_SAVE)
    try:
        with open(SAVE_FILE, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data.update(loaded)
    except (OSError, json.JSONDecodeError, TypeError):
        # Arquivo inexistente ou corrompido — tenta migrar o recorde antigo
        old = _migrate_old_record()
        if old > 0:
            data["high_score"] = old
    return data


def write_save(data):
    """Grava o dicionário de save em disco (JSON formatado)."""
    try:
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


class SaveManager:
    """
    Gerencia o save do jogador: carrega, atualiza estatísticas e grava em disco.

    Uso típico:
        sm = SaveManager()
        sm.data["high_score"] ...
        sm.save()
    """

    def __init__(self):
        self.data = load_save()

    @property
    def high_score(self):
        return self.data.get("high_score", 0)

    @property
    def best_wave(self):
        return self.data.get("best_wave", 0)

    @property
    def preferred_difficulty(self):
        return self.data.get("preferred_difficulty", 2)

    def begin_game(self, difficulty):
        """Chamado ao iniciar uma partida: incrementa contador e salva preferência."""
        self.data["games_played"] = self.data.get("games_played", 0) + 1
        self.data["preferred_difficulty"] = difficulty
        self.data["last_played"] = datetime.now().isoformat(timespec="seconds")
        self.save()

    def end_game(self, score, wave, cars_destroyed, reached_endless):
        """
        Chamado ao terminar uma partida (vitória ou derrota).
        Atualiza recordes e estatísticas se necessário.
        """
        self.data["total_score"] = self.data.get("total_score", 0) + score
        self.data["cars_destroyed"] = self.data.get("cars_destroyed", 0) + cars_destroyed

        if score > self.data.get("high_score", 0):
            self.data["high_score"] = score

        if wave > self.data.get("best_wave", 0):
            self.data["best_wave"] = wave

        if reached_endless:
            self.data["games_won"] = self.data.get("games_won", 0) + 1

        self.data["last_played"] = datetime.now().isoformat(timespec="seconds")
        self.save()

    def save(self):
        """Persiste o estado atual em save.json."""
        write_save(self.data)


def make_sound(freq, dur, noise=0.0, slide=0.0, vol=0.35):
    """
    Gera um efeito sonoro procedural (onda quadrada + ruído opcional).

    freq  – frequência inicial em Hz
    dur   – duração em segundos
    noise – quantidade de ruído (0 = puro, 1 = só ruído)
    slide – variação de frequência ao longo do som (Hz)
    vol   – volume (0 a 1)
    """
    rate = 22050
    n = int(rate * dur)
    buf = array.array("h")
    phase = 0.0
    for i in range(n):
        k = 1 - i / n                          # envelope de decaimento linear
        phase += (freq + slide * i / n) / rate
        wave = 1.0 if (phase % 1) < 0.5 else -1.0  # onda quadrada
        val = ((1 - noise) * wave + noise * random.uniform(-1, 1)) * k * vol
        buf.append(int(val * 32767))
    return pygame.mixer.Sound(buffer=buf.tobytes())


# Margem extra ao redor dos sprites de vagão (para rotação sem cortar)
PAD = 30
# Cache de sprites já gerados: chave = (tipo, flash) → Surface
_sprites = {}


def track_point(s, radial=0.0):
    """
    Converte distância percorrida na pista (s) em coordenadas de tela.

    s      – distância ao longo da pista a partir do túnel de entrada
    radial – deslocamento para fora/dentro do trilho (útil para altura do vagão)

    Retorna (x, y, ângulo) em radianos.
    """
    ang = IN_ANG + s / TRACK_R
    r = TRACK_R + radial
    return CX + math.cos(ang) * r, CY + math.sin(ang) * r, ang


def car_sprite(kind, flash):
    """
    Desenha (ou reutiliza do cache) o sprite de um vagão na horizontal.

    kind  – chave em CAR_TYPES
    flash – se True, o vagão fica branco (feedback de dano)

    O sprite é desenhado com a frente apontando para a direita;
    depois é rotacionado conforme o ângulo da pista.
    """
    key = (kind, flash)
    if key in _sprites:
        return _sprites[key]

    _, _, w, h, base, _ = CAR_TYPES[kind]
    surf = pygame.Surface((w + 2 * PAD, h + 2 * PAD), pygame.SRCALPHA)
    r = pygame.Rect(PAD, PAD, w, h)
    color = (255, 255, 255) if flash else base
    pygame.draw.rect(surf, color, r, border_radius=6)
    pygame.draw.rect(surf, (30, 30, 30), r, 2, border_radius=6)

    # Detalhes visuais por tipo de vagão
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
            pygame.draw.line(surf, (80, 85, 95),
                             (r.x + 8, r.y + 10 + i * 12),
                             (r.right - 8, r.y + 10 + i * 12), 3)
    elif kind == "passageiro":
        for i in range(3):
            pygame.draw.rect(surf, (210, 235, 255), (r.x + 8 + i * 20, r.y + 8, 14, 14))
    elif kind == "rapido":
        # Forma aerodinâmica + luz frontal
        pygame.draw.polygon(surf, (20, 140, 130), [
            (r.x + 8, r.centery), (r.x + 28, r.y + 6),
            (r.right - 6, r.centery), (r.x + 28, r.bottom - 6)
        ])
        pygame.draw.circle(surf, (255, 255, 180), (r.right - 10, r.centery), 4)
    elif kind == "bomba":
        # Círculo de explosivo + pavio
        pygame.draw.circle(surf, (255, 80, 40), (r.centerx, r.centery), 16)
        pygame.draw.circle(surf, (40, 10, 5), (r.centerx, r.centery), 16, 2)
        pygame.draw.line(surf, (255, 200, 80), (r.centerx, r.y + 4), (r.centerx + 8, r.y - 6), 3)
    elif kind == "atirador":
        # Torre de canhão + janelas
        pygame.draw.rect(surf, (100, 40, 140), (r.x + 18, r.y - 10, 28, 12), border_radius=3)
        pygame.draw.circle(surf, (255, 100, 255), (r.centerx, r.y + 8), 6)
        for i in range(2):
            pygame.draw.rect(surf, (220, 180, 255), (r.x + 12 + i * 28, r.y + 14, 16, 12))
    elif kind == "chefe":
        # Coroa de triângulos + olho central
        for i in range(5):
            pygame.draw.polygon(surf, (255, 210, 40), [
                (r.x + 10 + i * 22, r.bottom - 4),
                (r.x + 22 + i * 22, r.y + 8),
                (r.x + 32 + i * 22, r.bottom - 4)
            ])
        pygame.draw.circle(surf, (255, 60, 60), (r.centerx, r.y + 18), 10)
        pygame.draw.circle(surf, (20, 0, 0), (r.centerx, r.y + 18), 4)
    elif kind == "carga":
        pygame.draw.line(surf, (150, 85, 20), (r.centerx, r.y), (r.centerx, r.bottom), 3)

    # Rodas (o chefe tem 4, os demais têm 3)
    wheels = (r.x + 14, r.x + 46, r.right - 46, r.right - 14) if kind == "chefe" \
             else (r.x + 14, r.centerx, r.right - 14)
    for wx in wheels:
        pygame.draw.circle(surf, (25, 25, 25), (wx, r.bottom + 4), 7)
        pygame.draw.circle(surf, (120, 120, 120), (wx, r.bottom + 4), 3)

    _sprites[key] = surf
    return surf


# ===========================================================================
# Classes de entidades
# ===========================================================================

class Car:
    """Representa um vagão (ou locomotiva/chefe) do trem."""

    def __init__(self, kind, s, hp_mul=1.0, speed_bonus=0.0):
        self.kind = kind
        base_hp, self.points, self.w, self.h, self.color, _ = CAR_TYPES[kind]
        self.hp = max(1, int(base_hp * hp_mul))   # vida atual (já com multiplicador de dificuldade)
        self.max_hp = self.hp
        self.s = s                                 # posição ao longo da pista (centro do vagão)
        self.flash = 0.0                           # tempo restante de flash branco (dano)
        self.speed_bonus = speed_bonus             # multiplicador extra de velocidade (ex.: rápido)
        # Cooldown de tiro só para o tipo "atirador"
        self.shoot_cd = random.uniform(1.5, 3.0) if kind == "atirador" else 0.0

    def _center(self):
        """Retorna (x, y, ângulo) do centro do vagão na pista."""
        return track_point(self.s, self.h / 2 + 4)

    @property
    def pos(self):
        """Apenas as coordenadas (x, y) do centro."""
        x, y, _ = self._center()
        return x, y

    @property
    def on_track(self):
        """True se o vagão já saiu do túnel de entrada e ainda não chegou ao de saída."""
        return self.s + self.w / 2 > 0 and self.s < TRACK_LEN

    def hit_test(self, px, py, margin=4):
        """
        Testa se o ponto (px, py) colide com o vagão.
        Usa eixos alinhados ao ângulo da pista (along + radial).
        """
        cx, cy, ang = self._center()
        dx, dy = px - cx, py - cy
        along = -dx * math.sin(ang) + dy * math.cos(ang)   # eixo longitudinal
        radial = dx * math.cos(ang) + dy * math.sin(ang)   # eixo perpendicular
        return abs(along) <= self.w / 2 + margin and abs(radial) <= self.h / 2 + margin

    def draw(self, surf):
        """Desenha o vagão (e a barra de vida se tiver mais de 1 HP)."""
        if self.s + self.w / 2 <= 0:   # ainda totalmente dentro do túnel de entrada
            return
        cx, cy, ang = self._center()
        sprite = pygame.transform.rotate(
            car_sprite(self.kind, self.flash > 0),
            -(math.degrees(ang) + 90)
        )
        surf.blit(sprite, sprite.get_rect(center=(cx, cy)))

        # Barra de vida acima do vagão
        if self.max_hp > 1 and self.on_track:
            bw = self.w - 8
            bx, by = int(cx - bw / 2), int(cy - self.h / 2 - 26)
            pygame.draw.rect(surf, (60, 0, 0), (bx, by, bw, 4))
            pygame.draw.rect(surf, (80, 230, 80), (bx, by, int(bw * self.hp / self.max_hp), 4))


class Bullet:
    """Projétil disparado pela torre (ou por um vagão atirador)."""

    def __init__(self, x, y, angle, damage, enemy=False):
        self.x, self.y = x, y
        speed = 420 if enemy else 750          # tiros inimigos são mais lentos
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.damage = damage
        self.alive = True
        self.enemy = enemy                     # True = tiro do inimigo
        self.trail = []                        # posições recentes para desenhar rastro

    def update(self, dt):
        """Avança a posição e atualiza o rastro. Marca como morto se sair da tela."""
        self.trail.append((self.x, self.y))
        if len(self.trail) > 6:
            self.trail.pop(0)
        self.x += self.vx * dt
        self.y += self.vy * dt
        if not (-30 < self.x < W + 30 and -30 < self.y < H + 30):
            self.alive = False

    @property
    def rect(self):
        """Retângulo de colisão aproximado (8×8)."""
        return pygame.Rect(int(self.x) - 4, int(self.y) - 4, 8, 8)

    def draw(self, surf):
        """Desenha o rastro e o projétil em si."""
        if self.enemy:
            color = (255, 80, 255)
            r = 5
        else:
            color = (255, 90, 60) if self.damage > 1 else (255, 230, 100)
            r = 6 if self.damage > 1 else 4
        for i, (tx, ty) in enumerate(self.trail):
            s = max(1, r - 2 + i // 2)
            pygame.draw.circle(surf, color, (int(tx), int(ty)), s)
        pygame.draw.circle(surf, color, (int(self.x), int(self.y)), r)


class Particle:
    """Partícula de explosão ou fumaça."""

    def __init__(self, x, y, color, big=False, smoke=False):
        ang = random.uniform(0, math.tau)
        spd = random.uniform(40, 380 if big else 240)
        self.x, self.y = x, y
        self.vx, self.vy = math.cos(ang) * spd, math.sin(ang) * spd
        self.life = self.max_life = random.uniform(0.35, 1.1 if big else 0.75)
        self.size = random.uniform(2, 10 if big else 6)
        self.smoke = smoke
        if smoke:
            # Fumaça cinza que sobe lentamente
            self.color = random.choice([(80, 80, 80), (120, 120, 120), (60, 60, 60)])
            self.vy -= 40
        else:
            # Faíscas coloridas
            self.color = random.choice([color, (255, 200, 60), (255, 120, 40), (255, 255, 200)])

    def update(self, dt):
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += (80 if self.smoke else 280) * dt   # gravidade (fumaça é mais leve)
        self.vx *= 0.98                                 # atrito leve

    def draw(self, surf):
        k = max(self.life / self.max_life, 0)
        size = max(int(self.size * k), 1)
        if self.smoke:
            size = max(int(self.size * (1.2 - k * 0.5)), 2)
        pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), size)


class PowerUp:
    """Ícone de power-up que voa em direção à torre até ser coletado ou atirado."""

    def __init__(self, kind, x, y):
        self.kind, self.x, self.y = kind, x, y
        self.t = 0.0   # tempo de vida (para animação de pulso)

    def update(self, dt):
        """Move o power-up em direção ao centro da torre."""
        self.t += dt
        d = math.hypot(CX - self.x, CY - self.y) or 1.0
        self.x += (CX - self.x) / d * POWERUP_SPEED * dt
        self.y += (CY - self.y) / d * POWERUP_SPEED * dt

    @property
    def rect(self):
        return pygame.Rect(int(self.x) - 16, int(self.y) - 16, 32, 32)

    def draw(self, surf, font):
        color, letter = POWERUPS[self.kind]
        pulse = 2.5 * math.sin(self.t * 9)   # efeito de "pulsar"
        pygame.draw.circle(surf, color, (int(self.x), int(self.y)), int(16 + pulse))
        pygame.draw.circle(surf, (255, 255, 255), (int(self.x), int(self.y)), int(16 + pulse), 2)
        txt = font.render(letter, True, (255, 255, 255))
        surf.blit(txt, txt.get_rect(center=(int(self.x), int(self.y))))


class FloatingText:
    """Texto que sobe e some (ex.: '+50', 'COMBO', 'ESCUDO!')."""

    def __init__(self, x, y, text, color):
        self.x, self.y = x, y
        self.text = text
        self.color = color
        self.life = 1.0

    def update(self, dt):
        self.life -= dt
        self.y -= 40 * dt   # sobe lentamente

    def draw(self, surf, font):
        if self.life <= 0:
            return
        img = font.render(self.text, True, self.color)
        img.set_alpha(int(255 * max(self.life, 0)))
        surf.blit(img, img.get_rect(center=(int(self.x), int(self.y))))


# ===========================================================================
# Classe principal do jogo
# ===========================================================================

class Game:
    """Controla todo o estado, lógica e desenho do jogo."""

    def __init__(self):
        # Fontes
        self.font = pygame.font.SysFont("arial", 20, bold=True)
        self.big = pygame.font.SysFont("arial", 56, bold=True)
        self.med = pygame.font.SysFont("arial", 28, bold=True)
        self.small = pygame.font.SysFont("arial", 16)

        # Sistema de save (recorde, estatísticas, preferências)
        self.save_mgr = SaveManager()
        self.record = self.save_mgr.high_score
        self.difficulty = self.save_mgr.preferred_difficulty  # restaura última dificuldade

        # Efeitos sonoros gerados proceduralmente
        self.sfx = {}
        try:
            self.sfx = {
                "shot": make_sound(520, 0.09, slide=-380),
                "hit": make_sound(240, 0.07, noise=0.55),
                "boom": make_sound(85, 0.38, noise=0.85, slide=-50, vol=0.55),
                "power": make_sound(650, 0.2, slide=800),
                "lose": make_sound(280, 0.55, slide=-280),
                "wave": make_sound(420, 0.32, slide=450),
                "enemy_shot": make_sound(180, 0.12, noise=0.3, slide=-100),
            }
        except pygame.error:
            pass   # se o mixer falhar, o jogo continua sem som

        self.reset(from_menu=False)   # prepara estado interno, mas não conta como partida
        self.state = "menu"            # estados: menu | banner | playing | paused | lost | won
        self.flash_t = 0.0            # tempo restante de flash branco na tela
        self.float_texts = []

    def play(self, name):
        """Toca um efeito sonoro pelo nome (ignora se não existir)."""
        snd = self.sfx.get(name)
        if snd:
            snd.play()

    def finish(self, state):
        """
        Finaliza a partida (vitória ou derrota).
        Atualiza recordes e estatísticas no save.
        """
        self.state = state
        # Grava estatísticas desta partida
        self.save_mgr.end_game(
            score=self.score,
            wave=self.wave,
            cars_destroyed=self.cars_destroyed_session,
            reached_endless=self.endless,
        )
        # Atualiza o recorde exibido no HUD
        self.record = self.save_mgr.high_score

    def reset(self, from_menu=True):
        """
        Reinicia todos os valores para uma nova partida com a dificuldade atual.

        from_menu=True  → conta como partida iniciada e salva a preferência de dificuldade.
        from_menu=False → só prepara o estado (usado no __init__).
        """
        if from_menu:
            self.save_mgr.begin_game(self.difficulty)

        diff = DIFFICULTIES[self.difficulty]
        self.wave = 0
        self.score = 0
        self.lives = diff["lives"]
        self.max_lives = diff["lives"]
        self.state = "playing"
        self.aim = -math.pi / 2          # mira inicial apontando para cima
        self.bullets = []
        self.particles = []
        self.powerups = []
        self.cars = []
        self.enemy_bullets = []
        self.cooldown = 0.0              # tempo até poder atirar de novo
        self.rapid = 0.0                 # tempo restante de power-up rapidez
        self.heavy = 0.0                 # tempo restante de power-up pesado
        self.multi = 0.0                 # tempo restante de multitiros
        self.combo = 0
        self.combo_t = 0.0
        self.shake = 0.0                 # intensidade do tremor de tela
        self.shields = 0
        self.banner_t = 0.0
        self.flash_t = 0.0
        self.float_texts = []
        self.endless = False             # True depois de completar as 5 ondas normais
        self.cars_destroyed_session = 0  # contador de vagões destruídos nesta partida
        self.next_wave()

    def next_wave(self):
        """Prepara a próxima onda de vagões (ou entra no Endless)."""
        self.wave += 1
        diff = DIFFICULTIES[self.difficulty]

        # Quantidade de vagões cresce com a onda
        base_n = 7 + 3 * (self.wave - 1)
        if self.wave > TOTAL_WAVES:
            self.endless = True
            n = 10 + 2 * (self.wave - TOTAL_WAVES)
        else:
            n = base_n

        # Tipos disponíveis aumentam conforme a onda avança
        kinds = ["carga", "tanque", "passageiro"]
        if self.wave >= 2:
            kinds += ["blindado", "rapido"]
        if self.wave >= 3:
            kinds += ["blindado", "tanque", "bomba"]
        if self.wave >= 4:
            kinds += ["atirador", "rapido", "bomba"]
        if self.wave >= 6:
            kinds += ["atirador", "blindado", "bomba"]

        # Velocidade base da onda (limitada para não ficar impossível)
        speed_base = (38 + 11 * min(self.wave, 12)) * diff["speed_mul"]
        self.speed = speed_base

        # Monta o trem: locomotiva na frente + vagões aleatórios
        self.cars = [Car("locomotiva", 0, diff["hp_mul"])]
        for _ in range(n - 1):
            k = random.choice(kinds)
            bonus = 0.35 if k == "rapido" else 0.0   # vagões rápidos andam 35% mais rápido
            self.cars.append(Car(k, 0, diff["hp_mul"], bonus))

        # Chefe na onda 5 (e a cada 5 ondas no Endless)
        if self.wave == TOTAL_WAVES or (self.endless and self.wave % 5 == 0):
            self.cars[1] = Car("chefe", 0, diff["hp_mul"])

        # Posiciona os vagões enfileirados dentro do túnel de entrada
        pos = 0.0
        for c in self.cars:
            c.s = pos - c.w / 2
            pos -= c.w + CAR_SPACING

        self.bullets.clear()
        self.enemy_bullets.clear()
        self.banner_t = 2.0          # mostra o banner da onda por 2 segundos
        self.state = "banner"

    @property
    def muzzle(self):
        """Posição da ponta do canhão da torre."""
        return (CX + math.cos(self.aim) * 56, CY + math.sin(self.aim) * 56)

    def shoot(self):
        """Dispara um (ou três) projéteis a partir da torre, respeitando o cooldown."""
        if self.state != "playing" or self.cooldown > 0:
            return
        mx, my = self.muzzle
        dmg = 2 if self.heavy > 0 else 1
        if self.multi > 0:
            # Três tiros em leque
            for offset in (-0.18, 0.0, 0.18):
                self.bullets.append(Bullet(mx, my, self.aim + offset, dmg))
        else:
            self.bullets.append(Bullet(mx, my, self.aim, dmg))
        self.cooldown = FIRE_DELAY_RAPID if self.rapid > 0 else FIRE_DELAY
        self.play("shot")

    def explode(self, x, y, color, big=False, smoke=False):
        """Cria um conjunto de partículas de explosão (e fumaça se big=True)."""
        n = 55 if big else 22
        for _ in range(n):
            self.particles.append(Particle(x, y, color, big, smoke=smoke))
        if big:
            for _ in range(12):
                self.particles.append(Particle(x, y, color, False, smoke=True))

    def add_float(self, x, y, text, color=(255, 220, 80)):
        """Adiciona um texto flutuante na posição indicada."""
        self.float_texts.append(FloatingText(x, y, text, color))

    def toggle_pause(self):
        """Alterna entre jogando e pausado."""
        if self.state == "playing":
            self.state = "paused"
        elif self.state == "paused":
            self.state = "playing"

    def update(self, dt, mouse):
        """
        Atualiza toda a lógica do jogo a cada frame.

        dt    – tempo decorrido desde o último frame (segundos)
        mouse – posição atual do mouse (x, y)
        """
        if self.state == "paused":
            return

        # --- partículas e textos flutuantes (sempre atualizam) ---
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]
        for ft in self.float_texts:
            ft.update(dt)
        self.float_texts = [ft for ft in self.float_texts if ft.life > 0]
        self.flash_t = max(0.0, self.flash_t - dt)

        if self.state == "menu":
            return
        if self.state == "banner":
            self.banner_t -= dt
            if self.banner_t <= 0:
                self.state = "playing"
            return
        if self.state != "playing":
            return

        # --- mira segue o mouse ---
        self.aim = math.atan2(mouse[1] - CY, mouse[0] - CX)

        # --- timers de power-ups e efeitos ---
        self.cooldown = max(0.0, self.cooldown - dt)
        self.rapid = max(0.0, self.rapid - dt)
        self.heavy = max(0.0, self.heavy - dt)
        self.multi = max(0.0, self.multi - dt)
        self.shake = max(0.0, self.shake - dt)
        if self.combo_t > 0:
            self.combo_t -= dt
            if self.combo_t <= 0:
                self.combo = 0

        # --- movimento dos vagões ---
        for c in self.cars:
            spd = self.speed * (1.0 + c.speed_bonus)
            c.s += spd * dt
            c.flash = max(0.0, c.flash - dt)

            # Atiradores disparam periodicamente na torre
            if c.kind == "atirador" and c.on_track:
                c.shoot_cd -= dt
                if c.shoot_cd <= 0:
                    c.shoot_cd = random.uniform(1.8, 3.2)
                    cx, cy = c.pos
                    ang = math.atan2(CY - cy, CX - cx)
                    self.enemy_bullets.append(Bullet(cx, cy, ang, 1, enemy=True))
                    self.play("enemy_shot")

        # --- atualiza projéteis e power-ups ---
        for b in self.bullets:
            b.update(dt)
        for b in self.enemy_bullets:
            b.update(dt)
        for p in self.powerups:
            p.update(dt)
        # Remove power-ups que chegaram até a torre sem serem coletados
        self.powerups = [p for p in self.powerups if math.hypot(p.x - CX, p.y - CY) > 34]

        # --- colisão: tiros do jogador × vagões ---
        for b in self.bullets:
            if not b.alive:
                continue
            for c in self.cars:
                if c.on_track and c.hit_test(b.x, b.y):
                    b.alive = False
                    c.hp -= b.damage
                    c.flash = 0.09
                    self.explode(b.x, b.y, c.color, False)
                    self.play("hit")
                    if c.hp <= 0:
                        self._destroy_car(c)
                    break
            else:
                # Se não acertou vagão, tenta acertar um power-up (coleta)
                for pu in self.powerups[:]:
                    if b.rect.colliderect(pu.rect):
                        b.alive = False
                        self.collect(pu)
                        self.powerups.remove(pu)
                        break

        self.bullets = [b for b in self.bullets if b.alive]

        # --- colisão: tiros inimigos × torre ---
        for b in self.enemy_bullets:
            if math.hypot(b.x - CX, b.y - CY) < 40:
                b.alive = False
                if self.shields > 0:
                    self.shields -= 1
                    self.explode(CX, CY, (60, 200, 90), False)
                else:
                    self.lives -= 1
                    self.shake = 0.3
                    self.flash_t = 0.15
                    self.explode(CX, CY, (255, 60, 60), False)
                    self.play("lose")
                    if self.lives <= 0:
                        self.finish("lost")
                        return
        self.enemy_bullets = [b for b in self.enemy_bullets if b.alive]

        # Remove vagões destruídos
        self.cars = [c for c in self.cars if c.hp > 0]

        # --- vagões que atravessaram o túnel de saída ---
        for c in self.cars[:]:
            if c.s - c.w / 2 >= TRACK_LEN:
                self.cars.remove(c)
                ex, ey, _ = track_point(TRACK_LEN, 40)
                if self.shields > 0:
                    self.shields -= 1
                    self.explode(ex, ey, (60, 200, 90), False)
                    self.add_float(ex, ey, "ESCUDO!", (60, 220, 100))
                else:
                    self.lives -= 1
                    self.explode(ex, ey, (255, 60, 60), False)
                    self.play("lose")
                    self.flash_t = 0.2
                    if self.lives <= 0:
                        self.finish("lost")
                        return

        # --- onda concluída ---
        if not self.cars:
            bonus = 100 * self.wave
            self.score += bonus
            self.add_float(CX, CY - 80, f"+{bonus} ONDA!", (120, 255, 160))
            if self.wave >= TOTAL_WAVES and not self.endless:
                self.endless = True
            self.play("wave")
            self.next_wave()

    def _destroy_car(self, c):
        """
        Processa a destruição de um vagão:
        - soma pontos (com multiplicador de combo)
        - cria explosão
        - se for bomba, danifica vizinhos
        - chance de dropar power-up
        """
        self.play("boom")
        self.combo += 1
        self.combo_t = COMBO_WINDOW
        self.cars_destroyed_session += 1
        pts = c.points * self.multiplier
        self.score += pts
        cx, cy = c.pos
        self.add_float(cx, cy - 20, f"+{pts}", (255, 230, 100))

        big = c.kind in ("locomotiva", "chefe", "bomba")
        if c.kind in ("locomotiva", "chefe"):
            self.shake = 0.4
            self.flash_t = 0.18
        self.explode(cx, cy, c.color, big)

        # Efeito em cadeia da bomba
        if c.kind == "bomba":
            for other in self.cars:
                if other is not c and other.hp > 0:
                    ox, oy = other.pos
                    if math.hypot(ox - cx, oy - cy) < 90:
                        other.hp -= 1
                        other.flash = 0.12
                        if other.hp <= 0:
                            self._destroy_car(other)

        # Drop de power-up
        chance = DIFFICULTIES[self.difficulty]["power_chance"]
        if c.kind == "chefe" or random.random() < chance:
            kind = random.choice(list(POWERUPS.keys()))
            self.powerups.append(PowerUp(kind, cx, cy))

    @property
    def multiplier(self):
        """Multiplicador de pontos baseado no combo atual (máx. x6)."""
        return min(1 + self.combo // 3, 6)

    def shake_offset(self):
        """Retorna um deslocamento aleatório para o efeito de tremor de tela."""
        if self.shake <= 0:
            return (0, 0)
        amp = 12 * self.shake / 0.4
        return (random.randint(-int(amp), int(amp)), random.randint(-int(amp), int(amp)))

    def collect(self, pu):
        """Aplica o efeito do power-up coletado."""
        self.play("power")
        self.add_float(pu.x, pu.y - 25, pu.kind.upper(), POWERUPS[pu.kind][0])
        if pu.kind == "rapidez":
            self.rapid = RAPID_TIME
        elif pu.kind == "pesado":
            self.heavy = HEAVY_TIME
        elif pu.kind == "multitiros":
            self.multi = 4.0
        else:   # escudo
            self.shields += 1

    # -----------------------------------------------------------------------
    # Desenho
    # -----------------------------------------------------------------------

    def draw(self, surf, mouse):
        """Desenha o frame completo do jogo na superfície fornecida."""
        # Fundo com leve gradiente vertical
        surf.fill((78, 145, 70))
        for i in range(0, H, 4):
            shade = max(0, 20 - i // 30)
            pygame.draw.line(surf, (78 + shade, 145 + shade // 2, 70), (0, i), (W, i))

        self.draw_track(surf)
        for c in self.cars:
            c.draw(surf)
        self.draw_tunnel(surf, -TUNNEL_LEN / 2)                 # túnel de entrada
        self.draw_tunnel(surf, TRACK_LEN + TUNNEL_LEN / 2)      # túnel de saída

        for pu in self.powerups:
            pu.draw(surf, self.font)
        for b in self.bullets:
            b.draw(surf)
        for b in self.enemy_bullets:
            b.draw(surf)
        for p in self.particles:
            p.draw(surf)
        for ft in self.float_texts:
            ft.draw(surf, self.small)

        if self.state in ("playing", "banner", "paused"):
            self.draw_tower(surf, mouse)
        self.draw_hud(surf)

        # Flash branco de tela (dano / chefe morto)
        if self.flash_t > 0:
            alpha = int(90 * (self.flash_t / 0.2))
            flash = pygame.Surface((W, H), pygame.SRCALPHA)
            flash.fill((255, 255, 255, alpha))
            surf.blit(flash, (0, 0))

        # Overlays de estado
        if self.state == "menu":
            self.overlay_menu(surf)
        elif self.state == "paused":
            self.overlay(surf, "PAUSADO", (255, 255, 255),
                         "P continua  |  R reinicia  |  ESC sai")
        elif self.state == "banner":
            label = f"ONDA {self.wave}" if not self.endless else f"ENDLESS {self.wave}"
            self.center_text(surf, label, (255, 255, 255), -30)
            if any(c.kind == "chefe" for c in self.cars):
                self.center_text(surf, "CHEFE À VISTA!", (255, 100, 120), 50, small=True)
            self.center_text(surf, f"{len(self.cars)} vagões", (220, 220, 220), 20, small=True)
        elif self.state == "won":
            self.overlay(surf, "VITÓRIA!", (120, 255, 140))
        elif self.state == "lost":
            self.overlay(surf, "O TREM PASSOU!", (255, 100, 100))

    def draw_track(self, surf):
        """Desenha os trilhos e as dormentes da pista circular."""
        n = int(TRACK_LEN / 5)
        pts = [track_point(TRACK_LEN * i / n)[:2] for i in range(n + 1)]
        pygame.draw.lines(surf, (105, 80, 55), False, pts, 32)   # lastro
        # Dormentes
        for i in range(0, n + 1, 2):
            x1, y1, _ = track_point(TRACK_LEN * i / n, -15)
            x2, y2, _ = track_point(TRACK_LEN * i / n, 15)
            pygame.draw.line(surf, (70, 50, 30), (x1, y1), (x2, y2), 4)
        # Dois trilhos paralelos
        for off in (-9, 9):
            rail = [track_point(TRACK_LEN * i / n, off)[:2] for i in range(n + 1)]
            pygame.draw.lines(surf, (55, 55, 55), False, rail, 3)

    def draw_tunnel(self, surf, s):
        """Desenha um túnel na posição s da pista (entrada ou saída)."""
        tw, th = TUNNEL_LEN, 112
        spr = pygame.Surface((tw, th), pygame.SRCALPHA)
        pygame.draw.rect(spr, (80, 75, 70), (0, 0, tw, th), border_radius=16)
        pygame.draw.rect(spr, (12, 12, 12), (10, 16, tw - 20, th - 26), border_radius=26)
        # Tijolos decorativos
        for bx in range(4, tw - 8, 18):
            pygame.draw.rect(spr, (95, 90, 85), (bx, 4, 14, 10), 1)
        x, y, ang = track_point(s, 22)
        spr = pygame.transform.rotate(spr, -(math.degrees(ang) + 90))
        surf.blit(spr, spr.get_rect(center=(x, y)))

    def draw_tower(self, surf, mouse):
        """Desenha a torre central, o canhão e a mira do mouse."""
        # Sombra e base
        pygame.draw.circle(surf, (50, 90, 50), (CX + 3, CY + 4), 48)
        pygame.draw.circle(surf, (55, 105, 55), (CX, CY), 46)
        hull = pygame.Rect(0, 0, 72, 52)
        hull.center = (CX, CY)
        # Esteiras laterais
        for side in (-30, 30):
            pygame.draw.rect(surf, (32, 38, 32), (CX + side - 8, CY - 30, 16, 60), border_radius=5)
        pygame.draw.rect(surf, (50, 70, 50), hull, border_radius=8)
        pygame.draw.rect(surf, (22, 32, 22), hull, 2, border_radius=8)
        # Canhão
        mx, my = self.muzzle
        pygame.draw.line(surf, (45, 55, 45), (CX, CY), (mx, my), 14)
        pygame.draw.line(surf, (20, 25, 20), (CX, CY), (mx, my), 5)
        pygame.draw.circle(surf, (65, 90, 65), (CX, CY), 22)
        pygame.draw.circle(surf, (22, 32, 22), (CX, CY), 22, 2)
        # Escudo (círculo pulsante)
        if self.shields:
            pulse = 2 * math.sin(pygame.time.get_ticks() * 0.008)
            pygame.draw.circle(surf, (60, 210, 95), (CX, CY), int(60 + pulse), 3)
            if self.shields > 1:
                pygame.draw.circle(surf, (40, 180, 80), (CX, CY), int(68 + pulse), 2)
        # Mira (cruz + círculo)
        pygame.draw.circle(surf, (255, 255, 255), mouse, 11, 2)
        pygame.draw.line(surf, (255, 255, 255), (mouse[0] - 16, mouse[1]), (mouse[0] + 16, mouse[1]), 1)
        pygame.draw.line(surf, (255, 255, 255), (mouse[0], mouse[1] - 16), (mouse[0], mouse[1] + 16), 1)

    def draw_hud(self, surf):
        """Desenha a barra superior com pontuação, onda, vidas e power-ups ativos."""
        pygame.draw.rect(surf, (18, 22, 32), (0, 0, W, 36))

        # Pontos e recorde
        surf.blit(self.font.render(f"Pontos: {self.score}", True, (255, 255, 255)), (12, 7))
        surf.blit(self.small.render(f"Recorde: {self.record}", True, (180, 180, 200)), (12, 22))

        # Número da onda
        wave_label = f"Endless {self.wave}" if self.endless else f"Onda {self.wave}/{TOTAL_WAVES}"
        img = self.font.render(wave_label, True, (255, 220, 120) if self.endless else (255, 255, 255))
        surf.blit(img, (W // 2 - img.get_width() // 2 + 40, 8))

        # Vidas (círculos vermelhos)
        for i in range(self.max_lives):
            col = (255, 75, 75) if i < self.lives else (55, 45, 45)
            pygame.draw.circle(surf, col, (W - 28 - i * 28, 18), 9)
            pygame.draw.circle(surf, (30, 20, 20), (W - 28 - i * 28, 18), 9, 1)

        # Indicadores de power-ups ativos
        x = 280
        for label, t, col in (
            ("RAPIDEZ", self.rapid, POWERUPS["rapidez"][0]),
            ("PESADO", self.heavy, POWERUPS["pesado"][0]),
            ("MULTI", self.multi, POWERUPS["multitiros"][0]),
        ):
            if t > 0:
                surf.blit(self.small.render(f"{label} {t:.1f}s", True, col), (x, 10))
                x += 105

        # Combo
        if self.multiplier > 1:
            col = (255, 220, 80)
            img = self.font.render(f"COMBO x{self.multiplier}", True, col)
            surf.blit(img, (W // 2 - img.get_width() // 2 - 90, 7))

        # Escudos
        if self.shields:
            surf.blit(self.small.render(f"ESCUDO x{self.shields}", True, POWERUPS["escudo"][0]), (x, 10))

    def center_text(self, surf, text, color, dy, small=False):
        """Desenha texto centralizado horizontalmente, com deslocamento vertical dy."""
        f = self.font if small else self.big
        img = f.render(text, True, color)
        surf.blit(img, img.get_rect(center=(W // 2, H // 2 + dy)))

    def overlay_menu(self, surf):
        """Tela de menu inicial com seleção de dificuldade, estatísticas e instruções."""
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 175))
        surf.blit(shade, (0, 0))

        self.center_text(surf, "JOGO DO TREM", (255, 220, 90), -170)
        self.center_text(surf, "Destrua os vagões antes que atravessem o túnel!",
                         (230, 230, 230), -115, small=True)

        # Lista de dificuldades (a selecionada fica destacada)
        y0 = -55
        for d, info in DIFFICULTIES.items():
            selected = self.difficulty == d
            col = (120, 255, 140) if selected else (200, 200, 200)
            prefix = "▶ " if selected else "  "
            self.center_text(surf, f"{prefix}{d} - {info['name']}", col, y0 + (d - 1) * 28, small=True)

        # Estatísticas do save
        sd = self.save_mgr.data
        stats_lines = [
            f"Recorde: {sd.get('high_score', 0)}   |   Melhor onda: {sd.get('best_wave', 0)}",
            f"Partidas: {sd.get('games_played', 0)}   |   Endless: {sd.get('games_won', 0)}   |   Vagões: {sd.get('cars_destroyed', 0)}",
        ]
        for i, line in enumerate(stats_lines):
            self.center_text(surf, line, (180, 210, 255), 45 + i * 24, small=True)

        lines = [
            "Mouse: mira  |  Clique: atira  |  P: pausa",
            "Power-ups: R rapidez · P pesado · E escudo · M multitiros",
            "Novos inimigos: Rápido · Bomba · Atirador",
        ]
        for i, line in enumerate(lines):
            self.center_text(surf, line, (190, 190, 200), 110 + i * 24, small=True)
        self.center_text(surf, "Clique ou pressione ENTER para começar",
                         (100, 255, 130), 200, small=True)

    def overlay(self, surf, title, color, hint="R joga de novo  |  ESC sai"):
        """Overlay genérico de fim de jogo ou pausa."""
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 160))
        surf.blit(shade, (0, 0))
        self.center_text(surf, title, color, -60)
        if self.state != "paused":
            self.center_text(surf, f"Pontuação: {self.score}  |  Recorde: {self.record}",
                             (255, 255, 255), 5, small=True)
            self.center_text(surf, f"Onda: {self.wave}  |  Vagões destruídos: {self.cars_destroyed_session}",
                             (200, 200, 220), 35, small=True)
            if self.endless:
                self.center_text(surf, f"Chegou à onda {self.wave} no Endless!",
                                 (255, 200, 100), 65, small=True)
            # Novo recorde?
            if self.score >= self.record and self.score > 0:
                self.center_text(surf, "NOVO RECORDE!", (255, 230, 80), 95, small=True)
        self.center_text(surf, hint, (190, 190, 190), 130, small=True)


# ===========================================================================
# Loop principal
# ===========================================================================

def main():
    """Inicializa o Pygame e roda o loop principal do jogo."""
    pygame.init()
    try:
        pygame.mixer.init(22050, -16, 1)
    except pygame.error:
        pass   # continua sem áudio se o mixer falhar

    screen = pygame.display.set_mode((W, H))
    canvas = pygame.Surface((W, H))   # superfície intermediária (para aplicar o shake)
    pygame.display.set_caption("Jogo do Trem — Melhorado")
    clock = pygame.time.Clock()
    game = Game()

    while True:
        # Limita dt para evitar saltos grandes se o jogo travar
        dt = min(clock.tick(60) / 1000, 0.05)

        # --- eventos de entrada ---
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                pygame.quit()
                sys.exit()
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_r:
                    game.reset()
                if ev.key == pygame.K_p:
                    game.toggle_pause()
                # Seleção de dificuldade só no menu
                if game.state == "menu":
                    if ev.key in (pygame.K_1, pygame.K_KP1):
                        game.difficulty = 1
                        game.save_mgr.data["preferred_difficulty"] = 1
                        game.save_mgr.save()
                    elif ev.key in (pygame.K_2, pygame.K_KP2):
                        game.difficulty = 2
                        game.save_mgr.data["preferred_difficulty"] = 2
                        game.save_mgr.save()
                    elif ev.key in (pygame.K_3, pygame.K_KP3):
                        game.difficulty = 3
                        game.save_mgr.data["preferred_difficulty"] = 3
                        game.save_mgr.save()
                    elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                        game.reset()
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if game.state == "menu":
                    game.reset()
                else:
                    game.shoot()

        mouse = pygame.mouse.get_pos()
        # Segurar o botão mantém o fogo automático (respeitando cooldown)
        if game.state == "playing" and pygame.mouse.get_pressed()[0]:
            game.shoot()

        game.update(dt, mouse)
        game.draw(canvas, mouse)

        # Aplica o tremor de tela e exibe o frame
        screen.fill((0, 0, 0))
        screen.blit(canvas, game.shake_offset())
        pygame.display.flip()


if __name__ == "__main__":
    main()
