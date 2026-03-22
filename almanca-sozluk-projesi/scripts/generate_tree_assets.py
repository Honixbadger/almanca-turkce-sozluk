from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageEnhance, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = PROJECT_ROOT / "assets" / "trees"

PHOTO_SOURCES = {
    "hero_tree": {
        "download_url": "https://live.staticflickr.com/65535/51933137722_c74e431736_o.jpg",
        "focus": (0.55, 0.52),
    },
    "detail_tree": {
        "download_url": "https://upload.wikimedia.org/wikipedia/commons/d/d5/Pine_%28Unsplash%29.jpg",
        "focus": (0.52, 0.38),
    },
    "hero_tree_bg": {
        "download_url": "https://live.staticflickr.com/1823/43004489601_b298acb3a5_o.jpg",
        "focus": (0.52, 0.58),
    },
    "leaves_bg": {
        "download_url": "https://live.staticflickr.com/1521/25616690335_d3ddcd28d6_o.jpg",
        "focus": (0.5, 0.46),
    },
}

OUTPUT_SPECS = {
    "hero_tree.png": {"source": "hero_tree", "size": (2400, 1800)},
    "hero_tree_mirror.png": {"source": "hero_tree", "size": (2400, 1800), "mirror": True},
    "detail_tree.png": {"source": "detail_tree", "size": (2200, 1800)},
    "detail_tree_mirror.png": {"source": "detail_tree", "size": (2200, 1800), "mirror": True},
    "hero_tree_bg.png": {"source": "hero_tree_bg", "size": (3200, 1200)},
    "hero_tree_bg_mirror.png": {"source": "hero_tree_bg", "size": (3200, 1200), "mirror": True},
    "hero_tree_bg_warm.png": {"source": "hero_tree_bg", "size": (3200, 1200), "warm": True},
    "leaves_bg.png": {"source": "leaves_bg", "size": (2400, 1600)},
}


def fetch_image(url: str) -> Image.Image:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=90) as response:
        payload = response.read()
    image = Image.open(BytesIO(payload))
    return ImageOps.exif_transpose(image).convert("RGBA")


def crop_to_cover(image: Image.Image, target_size: tuple[int, int], focus: tuple[float, float]) -> Image.Image:
    target_width, target_height = target_size
    source_width, source_height = image.size
    source_ratio = source_width / source_height
    target_ratio = target_width / target_height

    if source_ratio > target_ratio:
        crop_height = source_height
        crop_width = int(round(crop_height * target_ratio))
    else:
        crop_width = source_width
        crop_height = int(round(crop_width / target_ratio))

    focus_x = max(0.0, min(1.0, focus[0]))
    focus_y = max(0.0, min(1.0, focus[1]))
    left = int(round((source_width - crop_width) * focus_x))
    top = int(round((source_height - crop_height) * focus_y))
    left = max(0, min(left, source_width - crop_width))
    top = max(0, min(top, source_height - crop_height))
    cropped = image.crop((left, top, left + crop_width, top + crop_height))
    return cropped.resize(target_size, Image.Resampling.LANCZOS)


def apply_warm_tint(image: Image.Image) -> Image.Image:
    base = image.convert("RGBA")
    r, g, b, a = base.split()
    r = ImageEnhance.Brightness(r).enhance(1.05)
    g = ImageEnhance.Brightness(g).enhance(0.99)
    b = ImageEnhance.Brightness(b).enhance(0.84)
    merged = Image.merge("RGBA", (r, g, b, a))
    overlay = Image.new("RGBA", merged.size, (218, 176, 112, 20))
    return Image.alpha_composite(merged, overlay)


def render_assets() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    image_cache: dict[str, Image.Image] = {}

    for source_key, source in PHOTO_SOURCES.items():
        image_cache[source_key] = fetch_image(source["download_url"])

    for filename, spec in OUTPUT_SPECS.items():
        source_key = spec["source"]
        source_image = image_cache[source_key]
        focus = PHOTO_SOURCES[source_key]["focus"]
        image = crop_to_cover(source_image, spec["size"], focus)
        if spec.get("mirror"):
            image = ImageOps.mirror(image)
        if spec.get("warm"):
            image = apply_warm_tint(image)
        image.save(ASSETS_DIR / filename, optimize=True)


if __name__ == "__main__":
    render_assets()
    for asset_path in sorted(ASSETS_DIR.glob("*.png")):
        with Image.open(asset_path) as image:
            print(f"{asset_path.name}\t{image.size[0]}x{image.size[1]}\t{asset_path.stat().st_size}")
