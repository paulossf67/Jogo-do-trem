"""Gera instalador/icone.ico (tanque no centro de uma pista com um trem) usando só o Pillow."""
import math
import os

from PIL import Image, ImageDraw

AQUI = os.path.dirname(os.path.abspath(__file__))
S = 1024                                     # desenha grande e reduz (bordas suaves)


def gerar():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=190, fill=(78, 145, 70, 255))            # gramado
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=190, outline=(40, 90, 45, 255), width=22)

    cx = cy = S / 2
    r = 340
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(105, 80, 55, 255), width=78)           # lastro
    d.ellipse([cx - r - 26, cy - r - 26, cx + r + 26, cy + r + 26], outline=(60, 60, 60, 255), width=10)
    d.ellipse([cx - r + 26, cy - r + 26, cx + r - 26, cy + r - 26], outline=(60, 60, 60, 255), width=10)

    def vagao(ang_graus, comprimento, cor, largura=92):
        """Retângulo tangente à pista, centrado no ângulo dado."""
        a = math.radians(ang_graus)
        rc = r - 39                                            # o contorno do círculo cresce para dentro
        px, py = cx + math.cos(a) * rc, cy + math.sin(a) * rc
        tx, ty = -math.sin(a), math.cos(a)                     # tangente
        nx, ny = math.cos(a), math.sin(a)                      # normal
        h, w = comprimento / 2, largura / 2
        pts = [(px + tx * h + nx * w, py + ty * h + ny * w), (px + tx * h - nx * w, py + ty * h - ny * w),
               (px - tx * h - nx * w, py - ty * h - ny * w), (px - tx * h + nx * w, py - ty * h + ny * w)]
        d.polygon(pts, fill=cor, outline=(30, 30, 30, 255))

    vagao(-35, 150, (200, 40, 40, 255), 104)                   # locomotiva
    vagao(-8, 120, (230, 140, 40, 255))
    vagao(17, 120, (60, 130, 210, 255))
    vagao(42, 120, (215, 175, 40, 255))

    d.rounded_rectangle([cx - 105, cy - 78, cx + 105, cy + 78], radius=28, fill=(50, 70, 50, 255),
                        outline=(22, 32, 22, 255), width=10)                                    # casco do tanque
    a = math.radians(-50)                                                                       # canhão
    d.line([(cx, cy), (cx + math.cos(a) * 190, cy + math.sin(a) * 190)], fill=(20, 25, 20, 255), width=44)
    d.ellipse([cx - 62, cy - 62, cx + 62, cy + 62], fill=(65, 90, 65, 255), outline=(22, 32, 22, 255), width=9)

    saida = os.path.join(AQUI, "icone.ico")
    img.save(saida, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(AQUI, "icone_previa.png"))
    print("ícone gerado:", saida)


if __name__ == "__main__":
    gerar()
