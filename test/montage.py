import sys
from PIL import Image
out, files = sys.argv[1], sys.argv[2:]
ims = [Image.open(f).convert("RGB").resize((320, 240)) for f in files]
cols = min(4, len(ims)); rows = (len(ims) + cols - 1) // cols
m = Image.new("RGB", (cols * 324, rows * 244), (255, 0, 255))
for i, im in enumerate(ims):
    m.paste(im, ((i % cols) * 324, (i // cols) * 244))
m.save(out)
