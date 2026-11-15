"""Do not cache/serve an image merely because its HTTP header says image/*."""
import io
import struct
import hashlib
from PIL import Image


# Confirmed 2026-11-15: CTX level 8, rows 92..94, columns 116..118
# return different PNG encodings of exactly this SAME detailed crater image.
# Reject this ambiguous upstream response rather than inventing its location.
BAD_CTX_PIXEL_HASHES={"95a2493faaca6595906ea74317987a1c02bd81fc3845038578d5308a7bc0b12d"}


def valid_tile(content, size, layer=None):
    try:
        with Image.open(io.BytesIO(content), formats=["PNG","JPEG"]) as image:
            if image.size != (size,size):
                return False
            image.verify()
        # verify checks PNG structure/CRC; load checks the compressed pixels.
        with Image.open(io.BytesIO(content), formats=["PNG","JPEG"]) as image:
            image.load()
            if layer=="ctx-global" and hashlib.sha256(image.convert("RGB").tobytes()).hexdigest() in BAD_CTX_PIXEL_HASHES:
                return False
        return True
    except (OSError,ValueError,SyntaxError,struct.error,Image.DecompressionBombError):
        return False
