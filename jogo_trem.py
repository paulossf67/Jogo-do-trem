"""
Jogo do Trem (Arcade): controle uma torre e impeça o trem de atravessar o segundo túnel.

Controles:
  Mouse .......... mira a torre
  Clique / segurar atira
  P .............. pausa
  R .............. reinicia
  M .............. volta ao menu (na pausa ou no fim da partida)
  1/2/3 .......... escolha de dificuldade no menu / de melhoria entre ondas
  ESC ............ sai

Requer Python 3.13 e a biblioteca Arcade 3.x (veja requirements.txt).

Convenção de coordenadas: toda a lógica do jogo usa y crescendo PARA BAIXO (como na tela);
a conversão para o sistema do Arcade (y para cima) acontece só na hora de desenhar (função Y).
"""
import bisect
import io
import json
import math
import os
import random
import time
import wave
from array import array
from datetime import datetime

import arcade
import pyglet
from arcade import key
from arcade.shape_list import ShapeElementList, create_line_strip, create_triangles_filled_with_colors
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Constantes de tela e geometria da pista
# ---------------------------------------------------------------------------
W, H = 1000, 640                          # largura e altura da janela
HUD_H = 40                                # altura da barra superior
CX, CY = W // 2, 34 + (H - 34) // 2       # centro da tela (posição da torre)
TRACK_R = 200                             # raio base da pista (em pixels)
IN_ANG = math.radians(-50)                # ângulo do túnel de entrada (sentido horário)
OUT_ANG = math.radians(230)               # ângulo do túnel de saída
TUNNEL_LEN = 140                          # comprimento visual de cada túnel
TOTAL_WAVES = 5                           # ondas normais antes do modo Endless
START_LIVES = 3                           # vidas padrão (pode mudar pela dificuldade)
MAX_LIVES = 5                             # máximo de vidas (chefes derrubados dão +1)
BOSS_EVERY = 5                            # um chefe a cada N ondas (mais chefes nas ondas seguintes)


def Y(y):
    """Converte y do jogo (para baixo) para y do Arcade (para cima)."""
    return H - y


# ---------------------------------------------------------------------------
# Constantes de combate e power-ups
# ---------------------------------------------------------------------------
FIRE_DELAY = 0.25          # intervalo entre tiros normais (segundos)
FIRE_DELAY_RAPID = 0.10    # intervalo com power-up de rapidez
RAPID_TIME = 3.5           # duração do power-up "rapidez"
HEAVY_TIME = 5.5           # duração do power-up "pesado" (tiro com mais dano)
POWERUP_SPEED = 70         # velocidade com que o power-up voa até a torre (px/s)
COMBO_WINDOW = 2.2         # tempo máximo entre destruições para manter o combo
WEAPON_TIME = 8.0          # duração das armas perfurante e míssil
BLAST_R = 85               # raio da explosão do míssil (px)
AURA_R = 110               # alcance da habilidade do médico e do protetor (px)

# Melhorias escolhidas entre as ondas: nome -> (título, descrição, nível máximo)
UPGRADES = {
    "cadencia": ("Cadência", "Tiros 12% mais rápidos", 5),
    "dano": ("Munição pesada", "+1 de dano em todos os tiros", 2),
    "vida": ("Blindagem", "+1 vida máxima e recupera 1", 3),
    "escudo": ("Escudo reserva", "Ganha 1 escudo agora", 99),
    "duracao": ("Bônus longos", "Power-ups duram 25% mais", 3),
    "sorte": ("Sorte", "+6% de chance de bônus", 4),
}
UPGRADE_SHORT = {"cadencia": "CAD", "dano": "DANO", "vida": "VIDA", "escudo": "ESC", "duracao": "DUR", "sorte": "SORTE"}
UPGRADE_MAX_LIVES = 8      # teto de vidas com a melhoria "Blindagem"
SHOP_CARD_W, SHOP_CARD_H, SHOP_GAP, SHOP_TOP = 270, 190, 30, 230   # layout das cartas de melhoria

# tipo: (vida, pontos, largura, altura, cor RGB, nome exibido)
CAR_TYPES = {
    "locomotiva": (2, 50, 90, 50, (200, 40, 40), "Locomotiva"),
    "carga": (1, 10, 70, 44, (230, 140, 40), "Carga"),
    "tanque": (2, 15, 70, 44, (215, 175, 40), "Tanque"),
    "blindado": (3, 25, 70, 44, (130, 135, 145), "Blindado"),
    "passageiro": (1, 10, 70, 44, (60, 130, 210), "Passageiro"),
    "rapido": (1, 20, 58, 36, (40, 200, 180), "Rápido"),      # compacto: alvo menor, mais pontos
    "bomba": (2, 30, 64, 48, (180, 50, 20), "Bomba"),         # explode e danifica vizinhos
    "atirador": (2, 35, 68, 44, (160, 60, 200), "Atirador"),  # atira de volta na torre
    "chefe": (18, 400, 140, 68, (90, 30, 120), "Chefe"),       # boss da onda
    "medico": (2, 40, 66, 44, (235, 235, 240), "Médico"),      # cura os vizinhos feridos
    "protetor": (3, 45, 66, 44, (80, 90, 210), "Protetor"),    # dá barreira (absorve 1 dano) aos vizinhos
}
# Onda em que cada vagão de apoio aparece e o texto do aviso
NEW_CAR_INFO = {
    "medico": (4, "MÉDICO — cura os vizinhos"),
    "protetor": (6, "PROTETOR — barreira nos vizinhos"),
}
CAR_SPACING = 12  # espaço entre vagões na formação do trem

# Power-ups: (cor RGB, letra exibida no ícone)
POWERUPS = {
    "rapidez": ((60, 140, 255), "R"),      # aumenta cadência de tiro
    "pesado": ((230, 60, 60), "P"),        # tiros causam 2 de dano
    "escudo": ((60, 200, 90), "E"),        # bloqueia uma vida perdida
    "multitiros": ((255, 180, 40), "M"),   # dispara 3 tiros em leque
    "perfurante": ((60, 220, 220), "F"),   # o tiro atravessa os vagões
    "missil": ((200, 80, 220), "X"),       # explode em área
}
WEAPON_NAMES = {"multitiros": "MULTITIROS", "perfurante": "PERFURANTE", "missil": "MÍSSIL"}
# Onda em que cada bônus passa a poder cair (os demais caem desde a onda 1)
POWERUP_MIN_WAVE = {"multitiros": 2, "perfurante": 3, "missil": 4}

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
    "player_name": "",         # nome do jogador (vazio = ainda não registrado)
    "high_score": 0,           # maior pontuação de todos os tempos
    "best_wave": 0,            # maior onda alcançada (incluindo Endless)
    "preferred_difficulty": 2, # última dificuldade escolhida (1/2/3)
    "games_played": 0,         # total de partidas iniciadas
    "games_won": 0,            # partidas em que chegou ao Endless
    "cars_destroyed": 0,       # total de vagões destruídos
    "total_score": 0,          # soma de todas as pontuações (estatística)
    "last_played": None,       # data/hora da última partida (ISO)
    # Ranking local: lista de {name, score, wave, date} ordenada por score (máx. 10)
    "leaderboard": [],
}

# Limites e regras do nome do jogador
NAME_MIN_LEN = 1
NAME_MAX_LEN = 16
LEADERBOARD_SIZE = 10

# Caracteres permitidos no nome: letras, acentos do português, números, espaço, hífen e underscore
_NAME_ACCENTS = "áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇñÑ"
NAME_ALLOWED_CHARS = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    + _NAME_ACCENTS
    + " -_"
)


def is_name_char_allowed(ch):
    """Retorna True se o caractere pode fazer parte do nome do jogador."""
    return ch in NAME_ALLOWED_CHARS


def sanitize_player_name(name):
    """
    Limpa o nome: remove caracteres proibidos, colapsa repetições e corta no tamanho máximo.

    Retorna (nome_limpo, ok) onde ok=False se o nome ficou inválido.
    """
    if name is None:
        return "", False
    cleaned = "".join(ch for ch in name if is_name_char_allowed(ch))
    while "  " in cleaned:
        cleaned = cleaned.replace("  ", " ")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    cleaned = cleaned.strip(" -_")[:NAME_MAX_LEN]
    return cleaned, len(cleaned) >= NAME_MIN_LEN


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
    - Se save.json não existir (ou estiver corrompido), tenta migrar o recorde.txt antigo.
    - Campos faltantes são preenchidos com DEFAULT_SAVE.
    """
    data = dict(DEFAULT_SAVE)
    try:
        with open(SAVE_FILE, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data.update(loaded)
    except (OSError, ValueError, TypeError):   # ValueError cobre JSON inválido e UnicodeDecodeError
        old = _migrate_old_record()
        if old > 0:
            data["high_score"] = old
    return data


def write_save(data):
    """Grava o save de forma atômica: escreve num temporário e troca (não corrompe se travar)."""
    tmp = SAVE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, SAVE_FILE)
    except OSError:
        pass


class SaveManager:
    """Gerencia o save do jogador: carrega, atualiza estatísticas e grava em disco."""

    def __init__(self):
        self.data = load_save()
        if not isinstance(self.data.get("leaderboard"), list):
            self.data["leaderboard"] = []

    @property
    def high_score(self):
        return self.data.get("high_score", 0)

    @property
    def best_wave(self):
        return self.data.get("best_wave", 0)

    @property
    def preferred_difficulty(self):
        return self.data.get("preferred_difficulty", 2)

    @property
    def player_name(self):
        """Nome registrado do jogador (string vazia se ainda não definido)."""
        return (self.data.get("player_name") or "").strip()

    @property
    def has_name(self):
        return len(self.player_name) >= NAME_MIN_LEN

    def set_player_name(self, name):
        """Valida, define e grava o nome. Retorna True se o nome era válido."""
        cleaned, ok = sanitize_player_name(name)
        if not ok:
            return False
        self.data["player_name"] = cleaned
        self.save()
        return True

    def begin_game(self, difficulty):
        """Chamado ao iniciar uma partida: incrementa contador e salva preferência."""
        self.data["games_played"] = self.data.get("games_played", 0) + 1
        self.data["preferred_difficulty"] = difficulty
        self.data["last_played"] = datetime.now().isoformat(timespec="seconds")
        self.save()

    def end_game(self, score, wave, cars_destroyed, reached_endless):
        """Atualiza recordes, estatísticas e o ranking local ao fim (ou abandono) de uma partida."""
        self.data["total_score"] = self.data.get("total_score", 0) + score
        self.data["cars_destroyed"] = self.data.get("cars_destroyed", 0) + cars_destroyed
        if score > self.data.get("high_score", 0):
            self.data["high_score"] = score
        if wave > self.data.get("best_wave", 0):
            self.data["best_wave"] = wave
        if reached_endless:
            self.data["games_won"] = self.data.get("games_won", 0) + 1
        self._update_leaderboard(score, wave)
        self.data["last_played"] = datetime.now().isoformat(timespec="seconds")
        self.save()

    def _update_leaderboard(self, score, wave):
        """Adiciona a partida ao ranking local (top N por pontuação)."""
        if score <= 0:
            return
        board = list(self.data.get("leaderboard") or [])
        board.append({
            "name": self.player_name or "Anônimo",
            "score": score,
            "wave": wave,
            "date": datetime.now().isoformat(timespec="seconds"),
        })
        board.sort(key=lambda e: (e.get("score", 0), e.get("wave", 0)), reverse=True)
        self.data["leaderboard"] = board[:LEADERBOARD_SIZE]

    def save(self):
        write_save(self.data)


# ---------------------------------------------------------------------------
# Sons gerados por código (nenhum arquivo de áudio)
# ---------------------------------------------------------------------------
def make_sound(freq, dur, noise=0.0, slide=0.0, vol=0.35):
    """
    Gera um efeito sonoro (onda quadrada + ruído, com decaimento) e o carrega na memória.

    freq  – frequência inicial em Hz          dur   – duração em segundos
    noise – 0 = tom puro, 1 = só ruído       slide – variação de frequência ao longo do som (Hz)
    vol   – volume de 0 a 1
    """
    rate = 22050
    n = int(rate * dur)
    samples = array("h")
    phase = 0.0
    for i in range(n):
        k = 1 - i / n                                        # envelope de decaimento linear
        phase += (freq + slide * i / n) / rate
        square = 1.0 if (phase % 1) < 0.5 else -1.0
        samples.append(int(((1 - noise) * square + noise * random.uniform(-1, 1)) * k * vol * 32767))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    buf.seek(0)
    return pyglet.media.load("efeito.wav", file=buf, streaming=False)


# ---------------------------------------------------------------------------
# Pista: forma variável a cada onda
# ---------------------------------------------------------------------------
class Track:
    """
    Pista fechada em volta da torre; a forma muda a cada onda.

    O raio varia com o ângulo: rho = 1 + a*cos(k*ang + fase), com estiramento horizontal.
    O trem gira no sentido horário, do túnel de entrada ao de saída.
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
        self.cum = [0.0]                       # distância acumulada até cada ponto
        for (x0, y0), (x1, y1) in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + math.hypot(x1 - x0, y1 - y0))
        self.length = self.cum[-1]

    def point(self, s, radial=0.0):
        last = len(self.pts) - 2
        if s <= 0:                             # antes do túnel de entrada: prolonga o primeiro trecho
            i = 0
        elif s >= self.length:                 # dentro do túnel de saída: prolonga o último
            i = last
        else:
            i = min(bisect.bisect_right(self.cum, s) - 1, last)
        d = s - self.cum[i]
        (x0, y0), (x1, y1) = self.pts[i], self.pts[i + 1]
        seg = self.cum[i + 1] - self.cum[i]
        tx, ty = (x1 - x0) / seg, (y1 - y0) / seg
        nx, ny = ty, -tx                       # normal para fora da pista
        return (x0 + tx * d + nx * radial, y0 + ty * d + ny * radial,
                math.atan2(ty, tx) - math.pi / 2)


_track = Track(0, 2, 0.0, 1.0)     # onda 1: círculo
TRACK_LEN = _track.length          # comprimento da pista atual (atualizado por set_track)
_track_shapes = None               # formas do Arcade da pista atual (criadas sob demanda)


def set_track(wave):
    """Gera a pista da onda: a partir da onda 2 ela ganha curvas e fica mais esticada."""
    global _track, TRACK_LEN, _track_shapes
    if wave <= 1:
        _track = Track(0, 2, 0.0, 1.0)
    else:
        a = min(0.05 * (wave - 1), 0.22) * random.uniform(0.6, 1.0)
        k = random.choice([2, 3, 4] if wave < 6 else [2, 3, 4, 5])
        stretch = 1 + random.uniform(0.1, 0.2) * min(wave - 1, 3)
        _track = Track(a, k, random.uniform(0, math.tau), stretch)
    TRACK_LEN = _track.length
    _track_shapes = None


def track_point(s, radial=0.0):
    """
    Converte distância percorrida na pista (s) em coordenadas de tela (y para baixo).

    s      – distância ao longo da pista a partir do túnel de entrada
    radial – deslocamento para fora/dentro do trilho (útil para altura do vagão)

    Retorna (x, y, ângulo) em radianos.
    """
    return _track.point(s, radial)


def sprite_angle(ang):
    """Ângulo (graus, anti-horário, eixo y para cima) de um sprite alinhado à pista no ângulo 'ang'."""
    return math.degrees(math.atan2(-math.cos(ang), -math.sin(ang)))


def track_shapes():
    """Trilhos, dormentes e lastro da pista atual, montados uma vez por onda (desenho em lote)."""
    global _track_shapes
    if _track_shapes is None:
        n = int(TRACK_LEN / 5)

        def pt(off, i):
            x, y, _ = track_point(TRACK_LEN * i / n, off)
            return (x, Y(y))

        shapes = ShapeElementList()
        shapes.append(create_line_strip([pt(0, i) for i in range(n + 1)], (105, 80, 55, 255), 32))   # lastro
        quads = []                                                                                    # dormentes:
        for i in range(0, n + 1, 2):                                                                  # uma malha só
            (ax, ay), (bx, by) = pt(-15, i), pt(15, i)
            ln = math.hypot(bx - ax, by - ay) or 1.0
            nx, ny = -(by - ay) / ln * 2, (bx - ax) / ln * 2                                          # meia largura = 2 px
            quads += [(ax + nx, ay + ny), (ax - nx, ay - ny), (bx + nx, by + ny),
                      (ax - nx, ay - ny), (bx - nx, by - ny), (bx + nx, by + ny)]
        shapes.append(create_triangles_filled_with_colors(quads, [(70, 50, 30, 255)] * len(quads)))
        for off in (-9, 9):                                                                           # trilhos
            shapes.append(create_line_strip([pt(off, i) for i in range(n + 1)], (55, 55, 55, 255), 3))
        _track_shapes = shapes
    return _track_shapes


# ---------------------------------------------------------------------------
# Texturas desenhadas por código (Pillow) — vagões e túneis viram sprites na GPU
# ---------------------------------------------------------------------------
PAD = 30            # margem ao redor do vagão na textura (cabine, chaminé, rodas)
_SS = 3             # supersampling: desenha em 3x e reduz, para bordas suaves


class _Canvas:
    """Pequeno helper de desenho em coordenadas de sprite (y para baixo) com suavização."""

    def __init__(self, w, h):
        self.size = (w, h)
        self.img = Image.new("RGBA", (w * _SS, h * _SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def rrect(self, box, radius, fill, outline=None, width=1):
        x0, y0, x1, y1 = (v * _SS for v in box)
        self.d.rounded_rectangle([x0, y0, x1 - 1, y1 - 1], radius=radius * _SS, fill=fill,
                                 outline=outline, width=int(width * _SS))

    def rect(self, box, fill=None, outline=None, width=1):
        x0, y0, x1, y1 = (v * _SS for v in box)
        self.d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=fill, outline=outline, width=int(width * _SS))

    def ellipse(self, box, fill, outline=None, width=1):
        x0, y0, x1, y1 = (v * _SS for v in box)
        self.d.ellipse([x0, y0, x1, y1], fill=fill, outline=outline, width=int(width * _SS))

    def circle(self, cx, cy, r, fill, outline=None, width=1):
        self.ellipse((cx - r, cy - r, cx + r, cy + r), fill, outline, width)

    def line(self, p0, p1, fill, width=1):
        self.d.line([(p0[0] * _SS, p0[1] * _SS), (p1[0] * _SS, p1[1] * _SS)], fill=fill, width=int(width * _SS))

    def poly(self, pts, fill):
        self.d.polygon([(x * _SS, y * _SS) for x, y in pts], fill=fill)

    def texture(self):
        return arcade.Texture(self.img.resize(self.size, Image.LANCZOS))


_car_textures = {}


def car_texture(kind, flash):
    """
    Textura de um vagão na horizontal (frente à direita, topo para fora da pista).

    kind  – chave em CAR_TYPES
    flash – se True, o vagão fica branco (feedback de dano)
    """
    key_ = (kind, flash)
    if key_ in _car_textures:
        return _car_textures[key_]

    _, _, w, h, base, _ = CAR_TYPES[kind]
    cv = _Canvas(w + 2 * PAD, h + 2 * PAD)
    x0, y0, x1, y1 = PAD, PAD, PAD + w, PAD + h
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    cv.rrect((x0, y0, x1, y1), 6, (255, 255, 255) if flash else base, (30, 30, 30), 2)

    # Detalhes visuais por tipo de vagão
    if kind == "locomotiva":
        cv.rect((x0 + 50, y0 - 14, x0 + 82, y0), (150, 25, 25))          # cabine
        cv.rect((x0 + 56, y0 - 10, x0 + 76, y0 - 2), (200, 230, 255))    # janela
        cv.rect((x0 + 8, y0 - 12, x0 + 20, y0 + 2), (40, 40, 40))        # chaminé
        cv.circle(x1 - 4, y0 + 18, 5, (255, 240, 120))                    # farol
    elif kind == "tanque":
        cv.ellipse((x0 + 5, y0 + 6, x1 - 5, y1 - 6), (240, 205, 90), (30, 30, 30), 2)
    elif kind == "blindado":
        for i in range(3):
            cv.line((x0 + 8, y0 + 10 + i * 12), (x1 - 8, y0 + 10 + i * 12), (80, 85, 95), 3)
    elif kind == "passageiro":
        for i in range(3):
            cv.rect((x0 + 8 + i * 20, y0 + 8, x0 + 22 + i * 20, y0 + 22), (210, 235, 255))
    elif kind == "rapido":
        cv.poly([(x0 + 8, cy), (x0 + 28, y0 + 6), (x1 - 6, cy), (x0 + 28, y1 - 6)], (20, 140, 130))
        cv.circle(x1 - 10, cy, 4, (255, 255, 180))
    elif kind == "bomba":
        cv.circle(cx, cy, 16, (255, 80, 40), (40, 10, 5), 2)
        cv.line((cx, y0 + 4), (cx + 8, y0 - 6), (255, 200, 80), 3)        # pavio
    elif kind == "atirador":
        cv.rrect((x0 + 18, y0 - 10, x0 + 46, y0 + 2), 3, (100, 40, 140))  # torre de canhão
        cv.circle(cx, y0 + 8, 6, (255, 100, 255))
        for i in range(2):
            cv.rect((x0 + 12 + i * 28, y0 + 14, x0 + 28 + i * 28, y0 + 26), (220, 180, 255))
    elif kind == "chefe":
        for i in range(5):                                                # coroa de triângulos
            cv.poly([(x0 + 10 + i * 22, y1 - 4), (x0 + 22 + i * 22, y0 + 8), (x0 + 32 + i * 22, y1 - 4)],
                    (255, 210, 40))
        cv.circle(cx, y0 + 18, 10, (255, 60, 60))                         # olho
        cv.circle(cx, y0 + 18, 4, (20, 0, 0))
    elif kind == "medico":
        cv.rect((cx - 15, cy - 4, cx + 15, cy + 4), (220, 40, 40))        # cruz vermelha
        cv.rect((cx - 4, cy - 15, cx + 4, cy + 15), (220, 40, 40))
    elif kind == "protetor":
        cv.circle(cx, cy, 15, (170, 200, 255), (30, 30, 30), 2)           # domo do gerador de barreira
        cv.circle(cx, cy, 6, (60, 70, 170))
    elif kind == "carga":
        cv.line((cx, y0), (cx, y1), (150, 85, 20), 3)

    # Rodas (o chefe tem 4, os demais têm 3)
    wheels = (x0 + 14, x0 + 46, x1 - 46, x1 - 14) if kind == "chefe" else (x0 + 14, cx, x1 - 14)
    for wx in wheels:
        cv.circle(wx, y1 + 4, 7, (25, 25, 25))
        cv.circle(wx, y1 + 4, 3, (120, 120, 120))

    tex = cv.texture()
    _car_textures[key_] = tex
    return tex


_tunnel_texture = None


def tunnel_texture():
    """Textura do túnel (a mesma para entrada e saída)."""
    global _tunnel_texture
    if _tunnel_texture is None:
        cv = _Canvas(TUNNEL_LEN, 112)
        cv.rrect((0, 0, TUNNEL_LEN, 112), 16, (80, 75, 70))
        cv.rrect((10, 16, TUNNEL_LEN - 10, 102), 26, (12, 12, 12))
        for bx in range(4, TUNNEL_LEN - 8, 18):                            # tijolos decorativos
            cv.rect((bx, 4, bx + 14, 14), None, (95, 90, 85), 1)
        _tunnel_texture = cv.texture()
    return _tunnel_texture


# ---------------------------------------------------------------------------
# Texto e primitivas de desenho (coordenadas do jogo: y para baixo)
# ---------------------------------------------------------------------------
_text_cache = {}


def draw_text(text, x, y, color=(255, 255, 255), size=12, anchor_x="left", anchor_y="center", bold=False):
    """Desenha texto reaproveitando objetos arcade.Text (criar Text a cada frame seria caro)."""
    k = (text, size, color, bold, anchor_x, anchor_y)
    t = _text_cache.get(k)
    if t is None:
        if len(_text_cache) > 1500:
            _text_cache.clear()
        t = arcade.Text(text, 0, 0, color, size, anchor_x=anchor_x, anchor_y=anchor_y,
                        bold=bold, font_name=("Arial",))
        _text_cache[k] = t
    t.x, t.y = x, Y(y)
    t.draw()


def fill_circle(x, y, r, color):
    arcade.draw_circle_filled(x, Y(y), r, color)


def ring(x, y, r, color, width=1):
    arcade.draw_circle_outline(x, Y(y), r, color, width)


def fill_rect(x, y, w, h, color):
    """Retângulo preenchido com canto superior esquerdo em (x, y)."""
    arcade.draw_lbwh_rectangle_filled(x, Y(y) - h, w, h, color)


def frame_rect(x, y, w, h, color, width=1):
    arcade.draw_lbwh_rectangle_outline(x, Y(y) - h, w, h, color, width)


def draw_line(x1, y1, x2, y2, color, width=1):
    arcade.draw_line(x1, Y(y1), x2, Y(y2), color, width)


# ===========================================================================
# Quadtree — partição espacial para colisões
# ===========================================================================

class Quadtree:
    """
    Quadtree 2D para reduzir testes de colisão. Cada objeto precisa de get_bounds() → (x, y, w, h).

    Poda: MAX_DEPTH limita a profundidade e MIN_NODE_SIZE evita quadrantes minúsculos;
    nos limites, objetos extras ficam no próprio nó (folha saturada).
    """

    MAX_OBJECTS = 4     # quantos objetos cabem num nó antes de tentar subdividir
    MAX_DEPTH = 6       # profundidade máxima (raiz = 0)
    MIN_NODE_SIZE = 16  # lado mínimo do quadrante em pixels

    def __init__(self, depth, x, y, w, h, max_depth=None, min_node_size=None):
        self.depth = depth
        self.x, self.y, self.w, self.h = x, y, w, h
        self.max_depth = self.MAX_DEPTH if max_depth is None else max_depth
        self.min_node_size = self.MIN_NODE_SIZE if min_node_size is None else min_node_size
        self.objects = []       # objetos deste nó
        self.nodes = []         # 4 filhos (NE, NW, SW, SE) ou vazio se folha

    def _can_split(self):
        """True se ainda dá para subdividir (poda por profundidade e por tamanho mínimo)."""
        return (self.depth < self.max_depth
                and self.w >= self.min_node_size and self.h >= self.min_node_size)

    def _split(self):
        if not self._can_split() or self.nodes:
            return False
        hw, hh = self.w / 2, self.h / 2
        x, y, d = self.x, self.y, self.depth + 1
        md, mn = self.max_depth, self.min_node_size
        self.nodes = [
            Quadtree(d, x + hw, y, hw, hh, md, mn),        # NE
            Quadtree(d, x, y, hw, hh, md, mn),             # NW
            Quadtree(d, x, y + hh, hw, hh, md, mn),        # SW
            Quadtree(d, x + hw, y + hh, hw, hh, md, mn),   # SE
        ]
        return True

    def _index(self, bounds):
        """Subquadrante que contém bounds por completo, ou -1 se cruza a linha do meio."""
        if not self.nodes:
            return -1
        bx, by, bw, bh = bounds
        mid_x, mid_y = self.x + self.w / 2, self.y + self.h / 2
        top, bottom = by + bh <= mid_y, by >= mid_y
        left, right = bx + bw <= mid_x, bx >= mid_x
        if top and right:
            return 0
        if top and left:
            return 1
        if bottom and left:
            return 2
        if bottom and right:
            return 3
        return -1

    def insert(self, obj):
        """Insere um objeto; o nó se divide quando passa de MAX_OBJECTS (se a poda permitir)."""
        bounds = obj.get_bounds()
        if self.nodes:
            idx = self._index(bounds)
            if idx != -1:
                self.nodes[idx].insert(obj)
                return
        self.objects.append(obj)
        if len(self.objects) > self.MAX_OBJECTS and not self.nodes and self._split():
            remaining = []
            for o in self.objects:
                idx = self._index(o.get_bounds())
                if idx != -1:
                    self.nodes[idx].insert(o)
                else:
                    remaining.append(o)
            self.objects = remaining

    @staticmethod
    def _overlap(ax, ay, aw, ah, bx, by, bw, bh):
        return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by

    def query_rect(self, qx, qy, qw, qh):
        """Todos os objetos cujas bounds intersectam o retângulo."""
        result = []
        if not self._overlap(qx, qy, qw, qh, self.x, self.y, self.w, self.h):
            return result
        for obj in self.objects:
            bx, by, bw, bh = obj.get_bounds()
            if self._overlap(qx, qy, qw, qh, bx, by, bw, bh):
                result.append(obj)
        for node in self.nodes:
            result.extend(node.query_rect(qx, qy, qw, qh))
        return result

    def query_point(self, px, py, radius=8):
        """Candidatos perto do ponto (px, py), com 'radius' de margem."""
        return self.query_rect(px - radius, py - radius, radius * 2, radius * 2)

    def query_circle(self, cx, cy, radius):
        """Candidatos cuja AABB intersecta o círculo (cx, cy, radius)."""
        out = []
        for obj in self.query_point(cx, cy, radius):
            bx, by, bw, bh = obj.get_bounds()
            nx, ny = max(bx, min(cx, bx + bw)), max(by, min(cy, by + bh))   # ponto da AABB mais próximo
            if (cx - nx) ** 2 + (cy - ny) ** 2 <= radius * radius:
                out.append(obj)
        return out


# ===========================================================================
# Classes de entidades
# ===========================================================================

class Car:
    """Representa um vagão (ou locomotiva/chefe) do trem."""

    def __init__(self, kind, s, hp_mul=1.0, hp_bonus=0):
        self.kind = kind
        base_hp, self.points, self.w, self.h, self.color, _ = CAR_TYPES[kind]
        self.hp = max(1, int(base_hp * hp_mul)) + hp_bonus   # vida atual (dificuldade + bônus por onda)
        self.max_hp = self.hp
        self.s = s                                 # posição ao longo da pista (centro do vagão)
        self.flash = 0.0                           # tempo restante de flash branco (dano)
        self.shoot_cd = random.uniform(1.5, 3.0) if kind == "atirador" else 0.0   # só para "atirador"
        self._bounds = (0.0, 0.0, 0.0, 0.0)        # AABB para a quadtree (refresh_bounds)
        self._flash_shown = False
        self.ability_cd = random.uniform(1.0, 3.0)   # recarga da habilidade (médico cura, protetor cria barreira)
        self.barrier = False                          # barreira do protetor: absorve o próximo dano
        self.sprite = arcade.Sprite(car_texture(kind, False))

    def _center(self):
        """Retorna (x, y, ângulo) do centro do vagão na pista."""
        return track_point(self.s, self.h / 2 + 4)

    @property
    def pos(self):
        x, y, _ = self._center()
        return x, y

    @property
    def on_track(self):
        """True se o vagão já saiu do túnel de entrada e ainda não chegou ao de saída."""
        return self.s + self.w / 2 > 0 and self.s < TRACK_LEN

    def refresh_bounds(self):
        """Atualiza a AABB da quadtree, com a meia diagonal como margem para cobrir qualquer rotação."""
        cx, cy, _ = self._center()
        half = 0.5 * math.hypot(self.w, self.h) + 6
        self._bounds = (cx - half, cy - half, half * 2, half * 2)

    def get_bounds(self):
        return self._bounds

    def hit_test(self, px, py, margin=4):
        """Testa se o ponto colide com o vagão, nos eixos da pista (ao longo + perpendicular)."""
        cx, cy, ang = self._center()
        dx, dy = px - cx, py - cy
        along = -dx * math.sin(ang) + dy * math.cos(ang)
        radial = dx * math.cos(ang) + dy * math.sin(ang)
        return abs(along) <= self.w / 2 + margin and abs(radial) <= self.h / 2 + margin

    def sync_sprite(self):
        """Copia posição, rotação e flash para o sprite (chamado uma vez por frame)."""
        cx, cy, ang = self._center()
        sp = self.sprite
        sp.center_x, sp.center_y = cx, Y(cy)
        sp.angle = sprite_angle(ang)
        sp.visible = self.s + self.w / 2 > 0          # oculto enquanto está dentro do túnel de entrada
        flashing = self.flash > 0
        if flashing != self._flash_shown:
            self._flash_shown = flashing
            sp.texture = car_texture(self.kind, flashing)

    def life_bar(self):
        """Segmentos (fundo, vida) da barra acima do vagão; None se não deve aparecer (1 HP ou fora da pista)."""
        if self.max_hp <= 1 or not self.on_track:
            return None
        cx, cy = self.pos
        bw = self.w - 8
        y = Y(cy - self.h / 2 - 24)
        x0 = cx - bw / 2
        return ((x0, y), (x0 + bw, y)), ((x0, y), (x0 + bw * self.hp / self.max_hp, y))


class Bullet:
    """Projétil disparado pela torre (ou por um vagão atirador)."""

    def __init__(self, x, y, angle, damage, enemy=False, pierce=False, blast=False):
        self.x, self.y = x, y
        speed = 420 if enemy else 750          # tiros inimigos são mais lentos
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.damage = damage
        self.alive = True
        self.enemy = enemy                     # True = tiro do inimigo
        self.trail = []                        # posições recentes para desenhar rastro
        self.pierce = pierce                   # atravessa os vagões
        self.blast = blast                     # explode em área ao acertar
        self.hit = set()                       # vagões já atingidos (perfurante não repete dano)

    def update(self, dt):
        """Avança a posição e atualiza o rastro. Marca como morto se sair da tela."""
        self.trail.append((self.x, self.y))
        if len(self.trail) > 6:
            self.trail.pop(0)
        self.x += self.vx * dt
        self.y += self.vy * dt
        if not (-30 < self.x < W + 30 and -30 < self.y < H + 30):
            self.alive = False

    def draw(self):
        if self.enemy:
            color, r = (255, 80, 255), 5
        elif self.pierce:
            color, r = (60, 220, 220), 4
        elif self.blast:
            color, r = (200, 80, 220), 7
        else:
            color, r = ((255, 90, 60), 6) if self.damage > 1 else ((255, 230, 100), 4)
        if self.trail:
            arcade.draw_points([(tx, Y(ty)) for tx, ty in self.trail], color, max(2, r))
        fill_circle(self.x, self.y, r, color)


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
            self.color = random.choice([(80, 80, 80), (120, 120, 120), (60, 60, 60)])   # fumaça cinza
            self.vy -= 40
        else:
            self.color = random.choice([color, (255, 200, 60), (255, 120, 40), (255, 255, 200)])

    def update(self, dt):
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += (80 if self.smoke else 280) * dt   # gravidade (fumaça é mais leve)
        self.vx *= 0.98                                 # atrito leve

    def draw_size(self):
        k = max(self.life / self.max_life, 0)
        if self.smoke:
            return max(int(self.size * (1.2 - k * 0.5)), 2)
        return max(int(self.size * k), 1)


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

    def hit_by(self, b):
        """True se o tiro toca o ícone (caixa de 32×32 contra o tiro de 8×8)."""
        return abs(b.x - self.x) < 20 and abs(b.y - self.y) < 20

    def draw(self):
        color, letter = POWERUPS[self.kind]
        r = 16 + 2.5 * math.sin(self.t * 9)   # efeito de "pulsar"
        fill_circle(self.x, self.y, r, color)
        ring(self.x, self.y, r, (255, 255, 255), 2)
        draw_text(letter, self.x, self.y, (255, 255, 255), 15, "center", "center", True)


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

    def draw(self):
        if self.life > 0:
            alpha = int(max(self.life, 0) * 5) * 51        # 5 níveis: 255, 204, 153, 102, 51
            draw_text(self.text, self.x, self.y, (*self.color[:3], alpha), 12, "center", "center")


# ===========================================================================
# Classe principal do jogo (lógica + desenho; a janela só repassa eventos)
# ===========================================================================

class Game:
    """Controla todo o estado, lógica e desenho do jogo."""

    def __init__(self):
        # Sistema de save (recorde, estatísticas, preferências, nome)
        self.save_mgr = SaveManager()
        self.record = self.save_mgr.high_score
        self.difficulty = self.save_mgr.preferred_difficulty  # restaura última dificuldade

        # Entrada de nome do jogador
        self.name_input = self.save_mgr.player_name  # texto sendo digitado
        self.name_cursor_t = 0.0                     # relógio do cursor piscante
        self.name_error = ""                         # mensagem de erro (nome inválido)

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
        except Exception:
            pass   # se o áudio falhar, o jogo continua sem som

        self.reset(from_menu=False)   # prepara estado interno, mas não conta como partida
        # Se ainda não tem nome, começa na tela de registro; senão, no menu
        self.state = "name_entry" if not self.save_mgr.has_name else "menu"

    # ---------------------------------------------------------------- nome do jogador
    def start_name_entry(self):
        """Abre a tela de registro/edição do nome (a partir do menu)."""
        self.name_input = self.save_mgr.player_name
        self.name_error = ""
        self.state = "name_entry"

    def confirm_name(self):
        """Tenta salvar o nome digitado. Se válido vai para o menu; se inválido mostra o erro."""
        cleaned, ok = sanitize_player_name(self.name_input)
        if not ok:
            has_special = any(ch and not is_name_char_allowed(ch) for ch in (self.name_input or ""))
            if has_special and not cleaned:
                self.name_error = "Só letras, números, espaço, - e _"
            else:
                self.name_error = f"Digite um nome ({NAME_MIN_LEN}–{NAME_MAX_LEN} caracteres)"
            self.play("lose")
            return
        if self.save_mgr.set_player_name(self.name_input):
            self.name_input = cleaned
            self.name_error = ""
            self.state = "menu"
            self.play("power")
        else:
            self.name_error = f"Digite um nome ({NAME_MIN_LEN}–{NAME_MAX_LEN} caracteres)"
            self.play("lose")

    def handle_name_key(self, symbol):
        """Teclas especiais na tela de nome (Enter, Esc, Backspace). O texto vem de handle_text."""
        if symbol in (key.RETURN, key.ENTER, key.NUM_ENTER):
            self.confirm_name()
        elif symbol == key.ESCAPE:
            if self.save_mgr.has_name:       # só cancela se já existir um nome salvo
                self.state = "menu"
        elif symbol == key.BACKSPACE:
            self.name_input = self.name_input[:-1]
            self.name_error = ""

    def handle_text(self, text):
        """Caracteres digitados na tela de nome (suporta acentos)."""
        if self.state != "name_entry":
            return
        for ch in text:
            if not ch.isprintable():         # ignora Enter/Backspace/Tab que chegam como texto
                continue
            if len(self.name_input) >= NAME_MAX_LEN:
                self.name_error = f"Máximo {NAME_MAX_LEN} caracteres"
                break
            if is_name_char_allowed(ch):
                self.name_input += ch
                self.name_error = ""
            else:
                self.name_error = "Caractere não permitido"

    # ---------------------------------------------------------------- som, partida e save
    def play(self, name):
        """Toca um efeito sonoro pelo nome (ignora se não existir ou se o áudio falhar)."""
        snd = self.sfx.get(name)
        if snd:
            try:
                snd.play()
            except Exception:
                pass

    def finish(self, state):
        """Finaliza a partida (derrota) e grava estatísticas e recorde."""
        self.state = state
        self._record_game()

    def _record_game(self):
        """Grava a partida no save (no máximo uma vez), inclusive se ela for abandonada."""
        if getattr(self, "_recorded", True):
            return
        self._recorded = True
        self.save_mgr.end_game(
            score=self.score,
            wave=self.wave,
            cars_destroyed=self.cars_destroyed_session,
            reached_endless=self.endless,
        )
        self.record = self.save_mgr.high_score   # atualiza o recorde exibido

    def go_menu(self):
        """Volta ao menu (permite trocar dificuldade e nome). A partida atual é gravada."""
        self._record_game()
        self.state = "menu"

    def set_difficulty(self, d):
        """Escolhe a dificuldade no menu e já grava a preferência."""
        self.difficulty = d
        self.save_mgr.data["preferred_difficulty"] = d
        self.save_mgr.save()

    def reset(self, from_menu=True):
        """
        Reinicia todos os valores para uma nova partida com a dificuldade atual.

        from_menu=True  → conta como partida iniciada e salva a preferência de dificuldade.
        from_menu=False → só prepara o estado (usado no __init__).
        """
        if from_menu:
            self._record_game()   # se a partida anterior foi abandonada (R no meio), grava antes
            self.save_mgr.begin_game(self.difficulty)

        diff = DIFFICULTIES[self.difficulty]
        self.wave = 0
        self.score = 0
        self.lives = diff["lives"]
        self.max_lives = MAX_LIVES
        self.state = "playing"
        self.aim = -math.pi / 2          # mira inicial apontando para cima
        self.bullets = []
        self.particles = []
        self.powerups = []
        self.cars = []
        self.car_list = arcade.SpriteList()      # sprites dos vagões (desenho em lote na GPU)
        self.tunnel_list = arcade.SpriteList()
        self.enemy_bullets = []
        self.cooldown = 0.0              # tempo até poder atirar de novo
        self.rapid = 0.0                 # tempo restante de power-up rapidez
        self.heavy = 0.0                 # tempo restante de power-up pesado
        self.multi = 0.0                 # tempo restante de multitiros
        self.weapon = None               # arma temporária: "perfurante" ou "missil"
        self.upgrades = {}               # melhorias escolhidas entre ondas: nome -> nível
        self.shop_choices = []           # cartas oferecidas na tela de melhorias
        self.weapon_t = 0.0
        self.banner_notes = []           # linhas exibidas no banner da onda
        self.combo = 0
        self.combo_t = 0.0
        self.shake = 0.0                 # tempo restante do tremor de tela
        self.shields = 0
        self.banner_t = 0.0
        self.flash_t = 0.0               # tempo restante de flash branco na tela
        self.float_texts = []
        self.endless = False             # True depois de completar as 5 ondas normais
        self.cars_destroyed_session = 0  # contador de vagões destruídos nesta partida
        self._quadtree = None            # reconstruída a cada frame em update()
        self._recorded = not from_menu   # só partidas iniciadas pelo menu contam no save
        self.next_wave()

    # ---------------------------------------------------------------- ondas
    def next_wave(self):
        """Prepara a próxima onda: trem maior, mais rápido, mais resistente e em nova pista."""
        self.wave += 1
        w = self.wave
        diff = DIFFICULTIES[self.difficulty]
        if w > TOTAL_WAVES:
            self.endless = True

        n = 7 + 3 * (w - 1)                      # a composição sempre cresce

        # Tipos disponíveis aumentam conforme a onda avança
        kinds = ["carga", "tanque", "passageiro"]
        if w >= 2:
            kinds += ["blindado", "rapido"]
        if w >= 3:
            kinds += ["blindado", "tanque", "bomba"]
        if w >= 4:
            kinds += ["atirador", "rapido", "bomba"]
        if w >= 6:
            kinds += ["atirador", "blindado", "bomba"]
        if w >= NEW_CAR_INFO["medico"][0]:
            kinds += ["medico"]
        if w >= NEW_CAR_INFO["protetor"][0]:
            kinds += ["protetor", "medico"]

        self.speed = (38 + 11 * min(w, 16)) * diff["speed_mul"]
        hp_bonus = (w - 1) // 4                  # vagões ganham vida com o tempo
        set_track(w)                             # cada onda tem um trajeto novo

        # Monta o trem: locomotiva na frente + vagões aleatórios
        self.cars = [Car("locomotiva", 0, diff["hp_mul"], hp_bonus)]
        for _ in range(n - 1):
            self.cars.append(Car(random.choice(kinds), 0, diff["hp_mul"], hp_bonus))

        # Chefes logo atrás da locomotiva: 1 na onda 5, 2 na 10, 3 a partir da 15
        bosses = min(w // BOSS_EVERY, 3) if w % BOSS_EVERY == 0 else 0
        for i in range(bosses):
            self.cars[1 + i] = Car("chefe", 0, diff["hp_mul"], 5 * (w // BOSS_EVERY - 1))

        # Posiciona os vagões enfileirados dentro do túnel de entrada
        pos = 0.0
        for c in self.cars:
            c.s = pos - c.w / 2
            pos -= c.w + CAR_SPACING

        self.car_list = arcade.SpriteList()
        for c in self.cars:
            self.car_list.append(c.sprite)
        self.tunnel_list = arcade.SpriteList()
        for s in (-TUNNEL_LEN / 2, TRACK_LEN + TUNNEL_LEN / 2):       # túnel de entrada e de saída
            x, y, ang = track_point(s, 22)
            self.tunnel_list.append(arcade.Sprite(tunnel_texture(), center_x=x, center_y=Y(y),
                                                  angle=sprite_angle(ang)))

        notes = []
        if w >= 2:
            notes.append(("NOVO TRAJETO!", (255, 220, 100)))
        for kind, first in POWERUP_MIN_WAVE.items():
            if first == w:
                notes.append((f"Novo bônus: {WEAPON_NAMES[kind]} ({POWERUPS[kind][1]})", POWERUPS[kind][0]))
        for info_wave, text in NEW_CAR_INFO.values():
            if info_wave == w:
                notes.append((f"Novo vagão: {text}", (255, 255, 255)))
        if bosses:
            notes.append(("CHEFE À VISTA!" if bosses == 1 else f"{bosses} CHEFES À VISTA!", (255, 100, 120)))
        notes.append((f"{n} vagões", (220, 220, 220)))
        self.banner_notes = notes

        self.bullets.clear()
        self.enemy_bullets.clear()
        self.banner_t = 2.5          # mostra o banner da onda por 2,5 segundos
        self.state = "banner"
        self.sync_sprites()

    @property
    def muzzle(self):
        """Posição da ponta do canhão da torre."""
        return (CX + math.cos(self.aim) * 56, CY + math.sin(self.aim) * 56)

    def shoot(self):
        """Dispara um (ou três) projéteis a partir da torre, respeitando o cooldown."""
        if self.state != "playing" or self.cooldown > 0:
            return
        mx, my = self.muzzle
        dmg = (2 if self.heavy > 0 else 1) + self.upgrade_level("dano")
        offsets = (-0.18, 0.0, 0.18) if self.multi > 0 else (0.0,)   # multitiros = leque de 3
        for off in offsets:
            self.bullets.append(Bullet(mx, my, self.aim + off, dmg,
                                       pierce=self.weapon == "perfurante", blast=self.weapon == "missil"))
        base = FIRE_DELAY_RAPID if self.rapid > 0 else FIRE_DELAY
        self.cooldown = base * 0.88 ** self.upgrade_level("cadencia")
        self.play("shot")

    def explode(self, x, y, color, big=False, smoke=False):
        """Cria um conjunto de partículas de explosão (e fumaça se big=True)."""
        for _ in range(55 if big else 22):
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

    def sync_sprites(self):
        for c in self.cars:
            c.sync_sprite()

    # ---------------------------------------------------------------- atualização
    def update(self, dt, mouse):
        """
        Atualiza toda a lógica do jogo a cada frame.

        dt    – tempo decorrido desde o último frame (segundos)
        mouse – posição do mouse em coordenadas do jogo (x, y para baixo)
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
        self.name_cursor_t += dt

        if self.state in ("menu", "name_entry"):
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
        if self.weapon:
            self.weapon_t -= dt
            if self.weapon_t <= 0:
                self.weapon = None
        self.shake = max(0.0, self.shake - dt)
        if self.combo_t > 0:
            self.combo_t -= dt
            if self.combo_t <= 0:
                self.combo = 0

        # --- movimento dos vagões ---
        for c in self.cars:
            c.s += self.speed * dt
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

            # Médico e protetor usam a habilidade de tempos em tempos
            if c.kind in ("medico", "protetor") and c.on_track:
                c.ability_cd -= dt
                if c.ability_cd <= 0:
                    self._use_ability(c)

        # --- atualiza projéteis e power-ups ---
        for b in self.bullets:
            b.update(dt)
        for b in self.enemy_bullets:
            b.update(dt)
        for p in self.powerups:
            p.update(dt)
        # Remove power-ups que chegaram até a torre sem serem coletados
        self.powerups = [p for p in self.powerups if math.hypot(p.x - CX, p.y - CY) > 34]

        # --- monta quadtree com os vagões na pista ---
        qt = Quadtree(0, -40, -40, W + 80, H + 80)
        for c in self.cars:
            if c.on_track and c.hp > 0:
                c.refresh_bounds()
                qt.insert(c)
        self._quadtree = qt   # reaproveitada na explosão de bomba/míssil

        # --- colisão: tiros do jogador × vagões (via quadtree) ---
        for b in self.bullets:
            if not b.alive:
                continue
            for c in qt.query_point(b.x, b.y, radius=20):
                if c.hp <= 0 or id(c) in b.hit or not c.hit_test(b.x, b.y):
                    continue
                b.hit.add(id(c))
                self.hurt(c, b.damage, b.x, b.y)
                if b.blast:
                    self._blast(b, c, qt)
                if not b.pierce:          # o tiro perfurante segue em frente
                    b.alive = False
                    break
            if b.alive:
                # Se o tiro continua vivo, tenta acertar um power-up (coleta)
                for pu in self.powerups[:]:
                    if pu.hit_by(b):
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
        self._drop_dead_cars()

        # --- vagões que atravessaram o túnel de saída ---
        for c in self.cars[:]:
            if c.s - c.w / 2 >= TRACK_LEN:
                self.cars.remove(c)
                c.sprite.remove_from_sprite_lists()
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
            self.play("wave")
            self.open_shop()
            return

        self.sync_sprites()

    def _use_ability(self, c):
        """Médico cura 1 HP dos vizinhos feridos; protetor dá barreira aos vizinhos que ainda não têm."""
        cx, cy = c.pos
        helped = 0
        for o in self.cars:
            if o is c or o.hp <= 0 or not o.on_track:
                continue
            ox, oy = o.pos
            if math.hypot(ox - cx, oy - cy) > AURA_R:
                continue
            if c.kind == "medico" and o.hp < o.max_hp:
                o.hp += 1
                helped += 1
                self.add_float(ox, oy - 20, "+1", (90, 255, 140))
            elif c.kind == "protetor" and not o.barrier:
                o.barrier = True
                helped += 1
        if helped:
            self.explode(cx, cy, (90, 255, 140) if c.kind == "medico" else (120, 220, 255), False)
        # sem ninguém para ajudar, tenta de novo logo
        c.ability_cd = (3.0 if c.kind == "medico" else 5.0) if helped else 1.0

    # ---------------------------------------------------------------- melhorias entre ondas
    def upgrade_level(self, name):
        return self.upgrades.get(name, 0)

    def open_shop(self):
        """Abre a escolha de melhoria: 3 cartas sorteadas entre as que ainda não chegaram ao nível máximo."""
        avail = [k for k, (_, _, top) in UPGRADES.items()
                 if self.upgrade_level(k) < top and not (k == "vida" and self.max_lives >= UPGRADE_MAX_LIVES)]
        self.shop_choices = random.sample(avail, min(3, len(avail)))
        self.bullets.clear()
        self.enemy_bullets.clear()
        self.state = "shop"

    def choose_upgrade(self, i):
        """Aplica a melhoria da carta i e começa a próxima onda."""
        if self.state != "shop" or not 0 <= i < len(self.shop_choices):
            return
        name = self.shop_choices[i]
        self.upgrades[name] = self.upgrade_level(name) + 1
        if name == "vida":
            self.max_lives = min(self.max_lives + 1, UPGRADE_MAX_LIVES)
            self.lives = min(self.lives + 1, self.max_lives)
        elif name == "escudo":
            self.shields += 1
        self.add_float(CX, CY - 80, UPGRADES[name][0].upper(), (255, 220, 100))
        self.play("power")
        self.next_wave()

    @staticmethod
    def shop_card_rect(i, n):
        """Retângulo (x, y, w, h) da carta i entre n cartas, em coordenadas do jogo."""
        total = n * SHOP_CARD_W + (n - 1) * SHOP_GAP
        return (W - total) / 2 + i * (SHOP_CARD_W + SHOP_GAP), SHOP_TOP, SHOP_CARD_W, SHOP_CARD_H

    def click_shop(self, x, y):
        """Clique do mouse na tela de melhorias: escolhe a carta sob o cursor."""
        n = len(self.shop_choices)
        for i in range(n):
            rx, ry, rw, rh = self.shop_card_rect(i, n)
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self.choose_upgrade(i)
                return

    def _drop_dead_cars(self):
        """Tira da lista (e do desenho) os vagões sem vida."""
        for c in self.cars:
            if c.hp <= 0:
                c.sprite.remove_from_sprite_lists()
        self.cars = [c for c in self.cars if c.hp > 0]

    def hurt(self, c, dmg, x, y):
        """Aplica dano a um vagão (com feedback visual/sonoro) e o destrói se a vida acabar."""
        if c.barrier:                           # a barreira do protetor absorve este golpe
            c.barrier = False
            c.flash = 0.09
            self.explode(x, y, (120, 220, 255), False)
            self.play("hit")
            return
        c.hp -= dmg
        c.flash = 0.09
        self.explode(x, y, c.color, False)
        self.play("hit")
        if c.hp <= 0:
            self._destroy_car(c)

    def _blast(self, b, hit_car, qt):
        """Explosão do míssil: causa o mesmo dano aos vagões num raio de BLAST_R."""
        self.explode(b.x, b.y, (255, 150, 40), True)
        self.shake = max(self.shake, 0.15)
        for o in qt.query_circle(b.x, b.y, BLAST_R):
            if o is hit_car or o.hp <= 0:
                continue
            ox, oy = o.pos
            if math.hypot(ox - b.x, oy - b.y) < BLAST_R:
                self.hurt(o, b.damage, ox, oy)

    def powerup_pool(self):
        """Bônus que já podem cair na onda atual."""
        return [k for k in POWERUPS if POWERUP_MIN_WAVE.get(k, 1) <= self.wave]

    def _destroy_car(self, c):
        """
        Processa a destruição de um vagão:
        soma pontos (com combo), cria explosão, danifica vizinhos se for bomba,
        dá vida extra se for chefe e sorteia um power-up.
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
        if c.kind == "chefe":                       # recompensa por derrubar um chefe
            self.lives = min(self.lives + 1, self.max_lives)
            self.add_float(cx, cy - 45, "+1 VIDA", (255, 120, 140))

        # Efeito em cadeia da bomba — vizinhos via quadtree (raio 90 px)
        if c.kind == "bomba":
            qt = self._quadtree
            neighbors = qt.query_circle(cx, cy, 90) if qt is not None else self.cars
            for other in neighbors:
                if other is not c and other.hp > 0:
                    ox, oy = other.pos
                    if math.hypot(ox - cx, oy - cy) < 90:
                        other.hp -= 1
                        other.flash = 0.12
                        if other.hp <= 0:
                            self._destroy_car(other)

        # Drop de power-up
        chance = DIFFICULTIES[self.difficulty]["power_chance"] + 0.06 * self.upgrade_level("sorte")
        if c.kind == "chefe" or random.random() < chance:
            self.powerups.append(PowerUp(random.choice(self.powerup_pool()), cx, cy))

    @property
    def multiplier(self):
        """Multiplicador de pontos baseado no combo atual (máx. x6)."""
        return min(1 + self.combo // 3, 6)

    def shake_offset(self):
        """Deslocamento aleatório da câmera para o efeito de tremor de tela."""
        if self.shake <= 0:
            return (0, 0)
        amp = 12 * self.shake / 0.4
        return (random.randint(-int(amp), int(amp)), random.randint(-int(amp), int(amp)))

    def collect(self, pu):
        """Aplica o efeito do power-up coletado."""
        self.play("power")
        self.add_float(pu.x, pu.y - 25, pu.kind.upper(), POWERUPS[pu.kind][0])
        longer = 1 + 0.25 * self.upgrade_level("duracao")     # melhoria "Bônus longos"
        if pu.kind == "rapidez":
            self.rapid = RAPID_TIME * longer
        elif pu.kind == "pesado":
            self.heavy = HEAVY_TIME * longer
        elif pu.kind == "multitiros":
            self.multi = 4.0 * longer
        elif pu.kind in ("perfurante", "missil"):
            self.weapon = pu.kind
            self.weapon_t = WEAPON_TIME * longer
        else:   # escudo
            self.shields += 1

    # ---------------------------------------------------------------- desenho do mundo
    def draw_world(self):
        """Cenário, pista, trem, projéteis e torre (a câmera com tremor já está ativa)."""
        # Fundo: gramado com leve gradiente vertical (faixas horizontais)
        for k in range(5):
            shade = max(0, 20 - k * 5)
            fill_rect(0, k * 130, W, 130, (78 + shade, 145 + shade // 2, 70))

        track_shapes().draw()
        self.car_list.draw()
        back, front = [], []                 # barras de vida de todos os vagões em 2 chamadas de desenho
        for c in self.cars:
            bar = c.life_bar()
            if bar:
                back.extend(bar[0])
                front.extend(bar[1])
        if back:
            arcade.draw_lines(back, (60, 0, 0), 4)
            arcade.draw_lines(front, (80, 230, 80), 4)
        for c in self.cars:                  # anel azul nos vagões com barreira do protetor
            if c.barrier and c.on_track:
                bx, by = c.pos
                ring(bx, by, max(c.w, c.h) / 2 + 6, (120, 220, 255), 2)
        self.tunnel_list.draw()          # túneis por cima dos vagões: eles "entram" e "saem" deles

        for pu in self.powerups:
            pu.draw()
        for b in self.bullets:
            b.draw()
        for b in self.enemy_bullets:
            b.draw()

        # Partículas agrupadas por (cor, tamanho): uma chamada de desenho por grupo
        groups = {}
        for p in self.particles:
            groups.setdefault((p.color, p.draw_size()), []).append((p.x, Y(p.y)))
        for (color, size), pts in groups.items():
            arcade.draw_points(pts, color, size * 2)

        for ft in self.float_texts:
            ft.draw()
        if self.state in ("playing", "banner", "paused", "shop"):
            self.draw_tower()

    def draw_tower(self):
        """Desenha a torre central e o canhão."""
        fill_circle(CX + 3, CY + 4, 48, (50, 90, 50))     # sombra e base
        fill_circle(CX, CY, 46, (55, 105, 55))
        for side in (-30, 30):                             # esteiras laterais
            fill_rect(CX + side - 8, CY - 30, 16, 60, (32, 38, 32))
        fill_rect(CX - 36, CY - 26, 72, 52, (50, 70, 50))
        frame_rect(CX - 36, CY - 26, 72, 52, (22, 32, 22), 2)
        mx, my = self.muzzle                               # canhão
        draw_line(CX, CY, mx, my, (45, 55, 45), 14)
        draw_line(CX, CY, mx, my, (20, 25, 20), 5)
        fill_circle(CX, CY, 22, (65, 90, 65))
        ring(CX, CY, 22, (22, 32, 22), 2)
        if self.shields:                                   # escudo (círculo pulsante)
            pulse = 2 * math.sin(time.time() * 8)
            ring(CX, CY, 60 + pulse, (60, 210, 95), 3)
            if self.shields > 1:
                ring(CX, CY, 68 + pulse, (40, 180, 80), 2)

    # ---------------------------------------------------------------- desenho da interface
    def draw_ui(self, mouse):
        """HUD, mira, flash de tela e telas de estado (sem tremor de câmera)."""
        if self.state in ("playing", "banner", "paused", "shop"):
            self.draw_crosshair(mouse)
        self.draw_hud()

        if self.flash_t > 0:                               # flash branco (dano / chefe morto)
            fill_rect(0, 0, W, H, (255, 255, 255, int(90 * (self.flash_t / 0.2))))

        if self.state == "name_entry":
            self.overlay_name_entry()
        elif self.state == "menu":
            self.overlay_menu()
        elif self.state == "shop":
            self.overlay_shop(mouse)
        elif self.state == "paused":
            self.overlay("PAUSADO", (255, 255, 255), "P continua  |  R reinicia  |  M menu  |  ESC sai")
        elif self.state == "banner":
            label = f"ONDA {self.wave}" if not self.endless else f"ENDLESS {self.wave}"
            self.center_text(label, (255, 255, 255), -50, "big")
            for i, (txt, col) in enumerate(self.banner_notes):
                self.center_text(txt, col, 10 + i * 28)
        elif self.state == "lost":
            self.overlay("O TREM PASSOU!", (255, 100, 100))

    def draw_crosshair(self, mouse):
        mx, my = mouse
        ring(mx, my, 11, (255, 255, 255), 2)
        draw_line(mx - 16, my, mx + 16, my, (255, 255, 255))
        draw_line(mx, my - 16, mx, my + 16, (255, 255, 255))

    def draw_hud(self):
        """Barra superior (pontos, onda, vidas) e indicadores de bônus no canto inferior."""
        fill_rect(0, 0, W, HUD_H, (18, 22, 32))

        # Pontos (linha 1) e nome + recorde (linha 2, fonte menor para não invadir o centro)
        pname = self.save_mgr.player_name or "Anônimo"
        draw_text(f"Pontos: {self.score}", 12, 12, (255, 255, 255), 14, bold=True)
        draw_text(f"{pname}  |  Recorde: {self.record}", 12, 30, (180, 180, 200), 10)

        # Número da onda
        wave_label = f"Endless {self.wave}" if self.endless else f"Onda {self.wave}/{TOTAL_WAVES}"
        draw_text(wave_label, W // 2 + 40, 20, (255, 220, 120) if self.endless else (255, 255, 255),
                  14, "center", bold=True)

        # Vidas (círculos vermelhos)
        for i in range(self.max_lives):
            x = W - 28 - i * 28
            fill_circle(x, 20, 9, (255, 75, 75) if i < self.lives else (55, 45, 45))
            ring(x, 20, 9, (30, 20, 20), 1)

        # Combo (topo, à esquerda do número da onda)
        if self.multiplier > 1:
            draw_text(f"COMBO x{self.multiplier}", W // 2 - 110, 20, (255, 220, 80), 14, "center", bold=True)

        # Indicadores de bônus ativos (canto inferior esquerdo, sobre uma faixa escura)
        active = [
            ("RAPIDEZ", self.rapid, POWERUPS["rapidez"][0]),
            ("PESADO", self.heavy, POWERUPS["pesado"][0]),
            ("MULTI", self.multi, POWERUPS["multitiros"][0]),
        ]
        if self.weapon:
            active.append((WEAPON_NAMES[self.weapon], self.weapon_t, POWERUPS[self.weapon][0]))
        if self.shields or self.upgrades or any(t > 0 for _, t, _ in active):
            fill_rect(0, H - 30, W, 30, (10, 14, 22, 170))
        x = 12
        for label, t, col in active:
            if t > 0:
                draw_text(f"{label} {math.ceil(t)}s", x, H - 15, col, 11)
                x += 135
        if self.shields:
            draw_text(f"ESCUDO x{self.shields}", x, H - 15, POWERUPS["escudo"][0], 11)
        if self.upgrades:                                         # resumo das melhorias, à direita
            resumo = " · ".join(f"{UPGRADE_SHORT[k]} {v}" for k, v in self.upgrades.items())
            draw_text(f"Melhorias: {resumo}", W - 12, H - 15, (190, 200, 220), 11, "right")

    def center_text(self, text, color, dy, size="small"):
        """Texto centralizado na tela, com deslocamento vertical dy."""
        pt, bold = {"big": (42, True), "med": (21, True), "small": (15, True)}[size]
        draw_text(text, W // 2, H // 2 + dy, color, pt, "center", "center", bold)

    def overlay_shop(self, mouse):
        """Tela de melhorias entre ondas: três cartas, escolha por 1/2/3 ou clique."""
        fill_rect(0, 0, W, H, (0, 0, 0, 175))
        self.center_text(f"ONDA {self.wave} CONCLUÍDA!", (120, 255, 160), -200, "big")
        self.center_text("Escolha uma melhoria  (teclas 1, 2, 3 ou clique)", (230, 230, 230), -150)
        n = len(self.shop_choices)
        for i, name in enumerate(self.shop_choices):
            rx, ry, rw, rh = self.shop_card_rect(i, n)
            hover = rx <= mouse[0] <= rx + rw and ry <= mouse[1] <= ry + rh
            fill_rect(rx, ry, rw, rh, (60, 80, 110) if hover else (40, 50, 70))
            frame_rect(rx, ry, rw, rh, (120, 200, 255) if hover else (90, 110, 140), 3 if hover else 2)
            title, desc, top = UPGRADES[name]
            lvl = self.upgrade_level(name)
            draw_text(f"[{i + 1}]", rx + 16, ry + 24, (255, 220, 100), 16, bold=True)
            draw_text(title, rx + rw / 2, ry + 62, (255, 255, 255), 17, "center", "center", True)
            draw_text(desc, rx + rw / 2, ry + 105, (200, 210, 225), 12, "center")
            nivel = f"Nível {lvl} → {lvl + 1}" + (f"  (máx. {top})" if top < 99 else "")
            draw_text(nivel, rx + rw / 2, ry + 150, (150, 255, 170), 12, "center")
        self.center_text(f"Próxima: onda {self.wave + 1}", (170, 170, 190), 190)

    def overlay_name_entry(self):
        """Tela para registrar ou editar o nome do jogador."""
        fill_rect(0, 0, W, H, (0, 0, 0, 190))
        title = "QUAL É O SEU NOME?" if not self.save_mgr.has_name else "EDITAR NOME"
        self.center_text(title, (255, 220, 90), -120, "big")
        self.center_text(f"Letras, números, espaço, - e _  |  máx. {NAME_MAX_LEN}", (180, 180, 180), -70)

        box_w, box_h = 360, 48                                   # caixa de texto
        box_x, box_y = W // 2 - box_w // 2, H // 2 - 20
        fill_rect(box_x, box_y, box_w, box_h, (30, 35, 50))
        frame_rect(box_x, box_y, box_w, box_h, (100, 180, 255), 2)
        cursor = "|" if int(self.name_cursor_t * 2) % 2 == 0 else " "   # cursor piscante
        draw_text(self.name_input + cursor, W // 2, box_y + box_h // 2, (255, 255, 255), 21, "center", "center", True)

        if self.name_error:
            self.center_text(self.name_error, (255, 100, 100), 50)
        self.center_text("ENTER confirma  |  BACKSPACE apaga", (190, 190, 200), 100)
        if self.save_mgr.has_name:
            self.center_text("ESC cancela", (160, 160, 170), 130)
        else:
            self.center_text("O nome aparece no ranking e no placar", (160, 160, 170), 130)

    def overlay_menu(self):
        """Tela de menu inicial com nome, dificuldade, estatísticas e ranking."""
        fill_rect(0, 0, W, H, (0, 0, 0, 175))
        self.center_text("JOGO DO TREM", (255, 220, 90), -190, "big")
        pname = self.save_mgr.player_name or "Anônimo"
        self.center_text(f"Jogador: {pname}   (N para alterar)", (180, 220, 255), -145)
        self.center_text("Destrua os vagões antes que atravessem o túnel!", (230, 230, 230), -115)

        for d, info in DIFFICULTIES.items():                     # lista de dificuldades
            selected = self.difficulty == d
            col = (120, 255, 140) if selected else (200, 200, 200)
            prefix = "▶ " if selected else "  "
            self.center_text(f"{prefix}{d} - {info['name']}", col, -70 + (d - 1) * 26)

        sd = self.save_mgr.data                                  # estatísticas do save
        stats_lines = [
            f"Recorde: {sd.get('high_score', 0)}   |   Melhor onda: {sd.get('best_wave', 0)}",
            f"Partidas: {sd.get('games_played', 0)}   |   Endless: {sd.get('games_won', 0)}   |   Vagões: {sd.get('cars_destroyed', 0)}",
        ]
        for i, line in enumerate(stats_lines):
            self.center_text(line, (180, 210, 255), 25 + i * 22)

        board = sd.get("leaderboard") or []                      # mini ranking (top 5)
        if board:
            self.center_text("— Ranking local —", (255, 200, 100), 80)
            for i, entry in enumerate(board[:5]):
                self.center_text(f"{i + 1}. {entry.get('name', '?')}  —  {entry.get('score', 0)} pts  "
                                 f"(onda {entry.get('wave', 0)})", (200, 200, 210), 105 + i * 20)
        else:
            for i, line in enumerate([
                "Mouse: mira  |  Clique: atira  |  P: pausa",
                "Bônus: R rapidez · P pesado · E escudo · M multitiros · F perfurante · X míssil",
            ]):
                self.center_text(line, (190, 190, 200), 90 + i * 22)

        self.center_text("Clique ou ENTER para começar  |  N editar nome", (100, 255, 130), 220)

    def overlay(self, title, color, hint="R joga de novo  |  M menu  |  ESC sai"):
        """Overlay genérico de fim de jogo ou pausa."""
        fill_rect(0, 0, W, H, (0, 0, 0, 160))
        self.center_text(title, color, -70, "big")
        if self.state != "paused":
            pname = self.save_mgr.player_name or "Anônimo"
            self.center_text(f"{pname}  —  Pontuação: {self.score}  |  Recorde: {self.record}", (255, 255, 255), -5)
            self.center_text(f"Onda: {self.wave}  |  Vagões destruídos: {self.cars_destroyed_session}",
                             (200, 200, 220), 25)
            if self.endless:
                self.center_text(f"Chegou à onda {self.wave} no Endless!", (255, 200, 100), 55)
            if self.score >= self.record and self.score > 0:
                self.center_text("NOVO RECORDE!", (255, 230, 80), 85)
        self.center_text(hint, (190, 190, 190), 125)


# ===========================================================================
# Janela do Arcade: repassa eventos ao jogo e desenha
# ===========================================================================

class TrainWindow(arcade.Window):
    """Janela do jogo. A lógica fica em Game; aqui só entrada, câmera e ciclo de desenho."""

    def __init__(self, visible=True):
        super().__init__(W, H, "Jogo do Trem — Arcade", update_rate=1 / 60, vsync=True, visible=visible)
        self.background_color = (78, 145, 70)
        self.game = Game()
        self.camera = arcade.Camera2D()                 # câmera do mundo (recebe o tremor de tela)
        self.mouse = (CX, CY - 150)                     # posição do mouse em coordenadas do jogo
        self.mouse_down = False

    # ---------------------------------------------------------------- ciclo principal
    def on_update(self, delta_time):
        dt = min(delta_time, 0.05)                      # evita saltos grandes se o jogo travar
        g = self.game
        if g.state == "playing" and self.mouse_down:
            g.shoot()                                   # segurar o botão mantém o fogo (respeita o cooldown)
        g.update(dt, self.mouse)

    def on_draw(self):
        self.clear()
        g = self.game
        dx, dy = g.shake_offset()
        self.camera.position = (W / 2 + dx, H / 2 + dy)
        self.camera.use()
        g.draw_world()
        self.default_camera.use()
        g.draw_ui(self.mouse)

    # ---------------------------------------------------------------- entrada
    def on_mouse_motion(self, x, y, dx, dy):
        self.mouse = (x, H - y)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        self.mouse = (x, H - y)

    def on_mouse_press(self, x, y, button, modifiers):
        self.mouse = (x, H - y)
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        self.mouse_down = True
        if self.game.state == "menu":
            self.game.reset()
        elif self.game.state == "shop":
            self.game.click_shop(*self.mouse)
        elif self.game.state == "playing":
            self.game.shoot()

    def on_mouse_release(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.mouse_down = False

    def on_text(self, text):
        self.game.handle_text(text)                     # digitação do nome (com acentos)

    def on_key_press(self, symbol, modifiers):
        g = self.game
        if g.state == "name_entry":                     # tela de nome: teclas especiais
            if not (symbol == key.ESCAPE and not g.save_mgr.has_name):   # 1ª vez: não deixa sair sem nome
                g.handle_name_key(symbol)
            return
        if symbol == key.ESCAPE:
            self.on_close()
            return
        if symbol == key.R and g.state != "menu":
            g.reset()
        elif symbol == key.P:
            g.toggle_pause()
        elif symbol == key.M and g.state in ("paused", "lost"):
            g.go_menu()
        elif g.state == "shop":                         # entre ondas: escolhe a melhoria 1, 2 ou 3
            for i, keys in enumerate(((key.KEY_1, key.NUM_1), (key.KEY_2, key.NUM_2), (key.KEY_3, key.NUM_3))):
                if symbol in keys:
                    g.choose_upgrade(i)
        elif g.state == "menu":                         # menu: dificuldade, nome e começar
            if symbol in (key.KEY_1, key.NUM_1):
                g.set_difficulty(1)
            elif symbol in (key.KEY_2, key.NUM_2):
                g.set_difficulty(2)
            elif symbol in (key.KEY_3, key.NUM_3):
                g.set_difficulty(3)
            elif symbol == key.N:
                g.start_name_entry()
            elif symbol in (key.RETURN, key.ENTER, key.SPACE):
                g.reset()

    def on_close(self):
        """Fecha a janela gravando a partida em andamento (o recorde não se perde)."""
        self.game._record_game()
        super().on_close()


def main():
    """Cria a janela e roda o loop principal do Arcade."""
    TrainWindow()
    arcade.run()


if __name__ == "__main__":
    main()
