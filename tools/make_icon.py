from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw

GREEN = (34, 197, 94)
GREEN_DARK = (21, 128, 61)
WHITE = (255, 255, 255)
GREY = (203, 213, 225)

def draw(size):
    scale = 8
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=GREEN)
    d.rounded_rectangle([int(s * 0.035)] * 2 + [s - int(s * 0.035)] * 2,
                        radius=int(s * 0.19), outline=GREEN_DARK, width=int(s * 0.012))
    # trash bin
    d.rectangle([int(s*0.28), int(s*0.32), int(s*0.72), int(s*0.78)], fill=WHITE)
    d.rectangle([int(s*0.34), int(s*0.24), int(s*0.66), int(s*0.32)], fill=GREY)
    d.rectangle([int(s*0.40), int(s*0.20), int(s*0.60), int(s*0.26)], fill=GREY)
    return img.resize((size, size), Image.LANCZOS)

def main():
    root = Path(__file__).resolve().parent.parent
    assets = root / "assets"
    assets.mkdir(exist_ok=True)
    master = draw(1024)
    master.save(assets / "emptyclean.ico", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    (root / "docs").mkdir(exist_ok=True)
    master.resize((256,256), Image.LANCZOS).save(root / "docs" / "icon.png")
    print("icon written")

if __name__ == "__main__":
    main()
