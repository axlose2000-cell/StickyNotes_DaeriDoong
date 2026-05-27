from PIL import Image, ImageDraw


def create_tray_image():
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 56, 56), radius=10, fill="#f4d55f", outline="#8a6f1d", width=3)
    draw.line((20, 24, 44, 24), fill="#6a5520", width=3)
    draw.line((20, 33, 44, 33), fill="#6a5520", width=3)
    draw.line((20, 42, 38, 42), fill="#6a5520", width=3)
    return image
