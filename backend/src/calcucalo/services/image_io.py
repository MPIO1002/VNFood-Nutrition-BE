from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import TypeAlias

import numpy as np
from PIL import Image, ImageOps

ImageInput: TypeAlias = str | Path | bytes | bytearray | Image.Image | np.ndarray


def load_rgb_image(source: ImageInput) -> np.ndarray:
    """Load an image, apply EXIF orientation and return contiguous uint8 RGB."""
    if isinstance(source, np.ndarray):
        array = source
        if array.ndim == 2:
            array = np.repeat(array[..., None], 3, axis=2)
        if array.ndim != 3 or array.shape[2] not in (3, 4):
            raise ValueError("NumPy image must have shape HxWx3 or HxWx4")
        if array.shape[2] == 4:
            array = array[:, :, :3]
        if array.dtype != np.uint8:
            if np.issubdtype(array.dtype, np.floating) and array.max(initial=0) <= 1.0:
                array = array * 255.0
            array = np.clip(array, 0, 255).astype(np.uint8)
        return np.ascontiguousarray(array)

    if isinstance(source, (bytes, bytearray)):
        image = Image.open(BytesIO(source))
    elif isinstance(source, Image.Image):
        image = source
    else:
        image = Image.open(Path(source))

    image = ImageOps.exif_transpose(image).convert("RGB")
    return np.ascontiguousarray(np.asarray(image, dtype=np.uint8))

