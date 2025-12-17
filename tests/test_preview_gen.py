from PIL import Image, ImageDraw, ImageFont
import textwrap
import os

title = "اموزش پایتون مقدماتی"
font_path = "src/fonts/Vazir-Bold.ttf"
width, height = 1920, 1080
background_color = (0, 0, 0)
text_color = (255, 255, 255)

img = Image.new('RGB', (width, height), color=background_color)
draw = ImageDraw.Draw(img)

try:
    font = ImageFont.truetype(font_path, 120)
except:
    font = ImageFont.load_default()

text_width = draw.textlength(title, font=font)
current_x = (width - text_width) // 2
current_y = (height - 180) // 2

draw.text((current_x, current_y), title, font=font, fill=text_color)
img.save("title_preview.png")
print("Title preview saved to title_preview.png")
