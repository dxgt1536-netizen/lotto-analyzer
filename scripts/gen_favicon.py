"""8볼 스타일 파비콘을 여러 크기의 PNG/ICO로 생성한다 (구글 검색결과 아이콘 요구사항 대응).

한 번 실행해서 static/에 결과물만 남기면 되는 빌드 스크립트라, 서버에 Pillow를
상시 설치할 필요 없이 로컬에서만 실행한다.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).parent.parent / "static"
BLACK = (17, 17, 17, 255)
WHITE = (255, 255, 255, 255)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\seguisb.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw_eightball(size: int) -> Image.Image:
    scale = 4  # 안티에일리어싱을 위해 크게 그린 뒤 축소
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.ellipse((0, 0, s - 1, s - 1), fill=BLACK)

    circle_r = s * 0.34
    cx, cy = s / 2, s * 0.46
    draw.ellipse(
        (cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r), fill=WHITE
    )

    font = _load_font(int(circle_r * 1.5))
    text = "8"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), text, fill=BLACK, font=font)

    return img.resize((size, size), Image.LANCZOS)


def main():
    sizes_png = {16: "favicon-16.png", 32: "favicon-32.png", 48: "favicon-48.png",
                 96: "favicon-96.png", 180: "favicon-180.png"}
    images = {}
    for size, filename in sizes_png.items():
        img = draw_eightball(size)
        images[size] = img
        img.save(OUT_DIR / filename)
        print("saved", filename)

    ico_sizes = [16, 32, 48]
    images[ico_sizes[0]].save(
        OUT_DIR / "favicon.ico",
        format="ICO",
        sizes=[(s, s) for s in ico_sizes],
        append_images=[images[s] for s in ico_sizes[1:]],
    )
    print("saved favicon.ico")


if __name__ == "__main__":
    main()
