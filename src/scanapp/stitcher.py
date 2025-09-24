try:
    from PyQt5.QtGui import QImage
except ImportError:
    QImage = None
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageOps


@dataclass
class Cropbox:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def empty(self) -> bool:
        return self.right <= self.left or self.bottom <= self.top

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def extend_below(self, other: "Cropbox") -> tuple["Cropbox", tuple[int, int], tuple[int, int]]:
        return (
            Cropbox(
                min(self.left, other.left),
                self.top,
                max(self.right, other.right),
                self.bottom + other.height,
            ),
            (
                0 if self.left <= other.left else self.left - other.left,
                0,
            ),
            (
                0 if other.left <= self.left else other.left - self.left,
                self.height,
            ),
        )


class ScanCollector:
    MAX_HEIGHT = 8000
    PREVIEW_MARGIN = 3

    CALIBRATION_BG = Image.open(Path(__file__).parent / "calibration150_bg.png")
    CALIBRATION_WHITE = Image.open(Path(__file__).parent / "calibration150_white.png")
    CALIBRATION_GRAY = Image.open(Path(__file__).parent / "calibration150_gray.png")

    cur_img: Image.Image | None
    cur_cropbox: Cropbox
    imgs: list[bytes]
    preview_imgs: list[Image.Image]

    thumbnail_size: tuple[int, int]
    cur_thumbnail: Image.Image | None = None
    cur_thumbnail_x: int = 0
    cur_thumbnail_width: int = 0

    def __init__(self, thumbnail_size: tuple[int, int]):
        self.cur_img = None
        self.imgs = []
        self.preview_imgs = []
        self.thumbnail_size = thumbnail_size

    def can_continue(self) -> bool:
        return self.cur_img is not None

    def begin_next(self):
        if self.cur_img is not None:
            self._finalize_current()
        self.cur_img = None

    def get_all(self) -> list[bytes]:
        if self.cur_img is not None:
            self._finalize_current()
        return self.imgs

    def _cropbox(self, img: Image.Image) -> Cropbox | None:
        calib = self.CALIBRATION_BG.resize(img.size, resample=Image.Resampling.NEAREST)
        print(calib, img)
        diff = ImageChops.difference(img, calib)
        del calib
        diff = ImageOps.grayscale(diff)
        diff = Image.eval(diff, lambda c: 0 if c < 28 else 255)
        diffbox = diff.getbbox()
        if not diffbox:
            return None
        return Cropbox(*diffbox)

    # def _cropbox(self, img: Image.Image) -> Cropbox:
    #     # Compute the diff mask
    #     # [h, w, 3]
    #     diff = cv2.absdiff(np.asarray(img), np.broadcast_to(self.CALIBRATION, (img.height, img.width, 3)))
    #     # [h, w]
    #     mask = np.mean(diff, axis=-1) < 10
    #     mask_x = np.maximum.reduce(mask, axis=0)
    #     mask_y = np.maximum.reduce(mask, axis=1)
    #     left = mask_x.argmax()
    #     right = len(mask_x) - mask_x[::-1].argmax()
    #     top = mask_y.argmax()
    #     bottom = len(mask_y) - mask_y[::-1].argmax()

    #     # Get tight box
    #     return Cropbox(left, top, right, bottom)

    def apply_calibration(self, img: Image.Image, crop: tuple[int, int]) -> Image.Image:
        img = np.asarray(img, dtype=np.float16)
        white = np.asarray(self.CALIBRATION_WHITE.crop((crop[0], 0, crop[1], 1)), dtype=np.float16)
        gray = np.asarray(self.CALIBRATION_GRAY.crop((crop[0], 0, crop[1], 1)), dtype=np.float16)
        black = white - (white - gray) * 1.5
        res = (img - black) / ((white - black) / 255)
        # white = self.CALIBRATION_WHITE.crop((crop[0], 0, crop[2], 1))
        # white = white.resize(img.size)
        # diff = ImageChops.subtract(white - img)
        # gray = self.CALIBRATION_GRAY.crop((crop[0], 0, crop[2], 1))
        # gray = gray.resize(img.size)
        # relative_gray = ImageChops.subtract(gray - white)
        # (MAX - (white - img)) * ((MAX - (white - gray)) / MAX / 0.8)
        return Image.fromarray(res.clip(0, 255).astype(np.uint8), mode="RGB")

    def append(self, img_data: bytes | Image.Image):
        if isinstance(img_data, bytes):
            img = Image.open(io.BytesIO(img_data))
        else:
            assert isinstance(img_data, Image.Image)
            img = img_data
        cropbox = self._cropbox(img)
        if cropbox is None or cropbox.empty:
            print("Empty scan")
            return
        assert img.width == self.CALIBRATION_BG.width, "Calibration does not match the scanned size"
        img = img.crop((cropbox.left, cropbox.top, cropbox.right, cropbox.bottom))
        img = self.apply_calibration(img, (cropbox.left, cropbox.right))
        if self.cur_img is None:
            # New image
            print(f"New scan cropbox={cropbox} (w={cropbox.width}, h={cropbox.height})")
            self.cur_img = img
            self.cur_cropbox = cropbox
            self.cur_thumbnail_x += self.cur_thumbnail_width
            self.cur_thumbnail_width = 0
        elif self.cur_img.height + cropbox.height > self.MAX_HEIGHT or cropbox.top > 10:
            print(
                f"Has space, start new scan cropbox={cropbox} (w={cropbox.width}, h={cropbox.height})"
            )
            # Image too large; or not continuing, start new
            self._finalize_current()
            self.cur_img = img
            self.cur_cropbox = cropbox
            self.cur_thumbnail_x += self.cur_thumbnail_width
            self.cur_thumbnail_width = 0
        else:
            print(f"Extend last scan from cur_cropbox={self.cur_cropbox}, cropbox={cropbox}")
            # Extend current image
            new_cropbox, cur_offset, offset = self.cur_cropbox.extend_below(cropbox)
            print(
                f"New box: new_cropbox={new_cropbox} (w={new_cropbox.width}, h={new_cropbox.height}), cur_offset={cur_offset}, offset={offset}"
            )
            img_new = Image.new("RGB", (new_cropbox.width, new_cropbox.height), "white")
            img_new.paste(self.cur_img, cur_offset)
            img_new.paste(img, offset)
            self.cur_img = img_new
            self.cur_cropbox = new_cropbox
        if (
            self.thumbnail_size[1] / self.thumbnail_size[0]
            >= self.cur_img.height / self.cur_img.width
        ):
            print("Simple Thumbnail")
            # Limited by width
            th = self.cur_img.copy()
            th.thumbnail(self.thumbnail_size)
            self.cur_img_thumbnail = th
        else:
            print("Split Thumbnail")
            self.cur_img_thumbnail = Image.new("RGB", self.thumbnail_size, "black")
            th_tb = (self.thumbnail_size[1] - self.PREVIEW_MARGIN) // 2
            th_bt = (self.thumbnail_size[1] + self.PREVIEW_MARGIN) // 2
            th_bt_size = self.thumbnail_size[1] - th_bt
            img_tb = th_tb * self.cur_img.width // self.thumbnail_size[0]
            img_bt_size = th_bt_size * self.cur_img.width // self.thumbnail_size[0]
            img_bt = self.cur_img.height - img_bt_size
            self.cur_img_thumbnail.paste(
                self.cur_img.resize(
                    (self.thumbnail_size[0], th_tb),
                    resample=Image.Resampling.BOX,
                    box=(0, 0, self.cur_img.width, img_tb),
                ),
                box=(0, 0),
            )
            self.cur_img_thumbnail.paste(
                self.cur_img.resize(
                    (self.thumbnail_size[0], th_bt_size),
                    resample=Image.Resampling.BOX,
                    box=(0, img_bt, self.cur_img.width, self.cur_img.height),
                ),
                box=(0, th_bt),
            )
        if cropbox.bottom < img.height - 10:
            # There is empty space at the end, disconnect from next scan
            self._finalize_current()

    def _finalize_current(self):
        print("Finish current image")
        assert self.cur_img is not None
        dst = io.BytesIO()
        self.cur_img.save(dst, format="jpeg")
        self.cur_img = None
        self.imgs.append(dst.getvalue())

    def qthumbnail(self) -> QImage:
        data = self.cur_img_thumbnail.tobytes("raw", "RGB")
        return QImage(
            data,
            self.cur_img_thumbnail.width,
            self.cur_img_thumbnail.height,
            self.cur_img_thumbnail.width * 3,
            QImage.Format_RGB888,
        )


# class CropStitcher:
#     MAX_HEIGHT = 4000

#     CALIBRATION = Image.open(Path(__file__).parent / 'CALIBRATION100.png')

#     def __init__(self, img_data: bytes):
#         self.img = Image.open(io.BytesIO(img_data))
#         assert self.img.width == self.CALIBRATION.width, "CALIBRATION does not match the scanned size"

#     def can_append(self):
#         return self.img.height < self.MAX_HEIGHT

#     def append_image(self, img_data: bytes):
#         img = Image.open(io.BytesIO(img_data))
#         img_new = Image.new("RGB", (self.img.width, self.img.height + img.height), "white")
#         img_new.paste(self.img, (0, 0))
#         img_new.paste(img, (0, self.img.height))
#         self.img = img_new

#     def _crop(self) -> Image.Image:
#         calib = self.CALIBRATION.resize(self.img.size)
#         diff = ImageChops.difference(self.img, calib)
#         del calib
#         diff = ImageOps.grayscale(diff)
#         diff = Image.eval(diff, lambda c: 0 if c < 10 else 255)
#         bbox = diff.getbbox()
#         del diff
#         return self.img.crop(bbox)

#     def thumbnail(self, size: tuple[int, int]) -> QImage:
#         img = self._crop()
#         img.thumbnail(size)
#         data = img.tobytes("raw", "RGB")
#         return QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)

#     def get(self) -> bytes:
#         crop = self._crop()
#         dst = io.BytesIO()
#         crop.save(dst, format='jpeg')
#         return dst.getvalue()


def imshow(qimg):
    import sys

    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QPixmap
    from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow

    # Create the application and show the pin input window
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DisableHighDpiScaling, True)
    app = QApplication(sys.argv)
    main_window = QMainWindow()
    main_window.showFullScreen()
    main_window.setFixedSize(SCREEN_RESOLUTION_WIDTH, SCREEN_RESOLUTION_HEIGHT)
    label = QLabel(main_window)
    main_window.setCentralWidget(label)
    main_window.show()
    label.setPixmap(QPixmap.fromImage(qimg))
    # label.clicked.connect(lambda *_: main_window.close())
    sys.exit(app.exec_())


if __name__ == "__main__":
    from scanapp.env import SCREEN_RESOLUTION_HEIGHT, SCREEN_RESOLUTION_WIDTH

    sc = ScanCollector((SCREEN_RESOLUTION_WIDTH, SCREEN_RESOLUTION_HEIGHT))

    with open("last.jpg", "rb") as rf:
        sc.append(rf.read())

    # with open("last_0.png", "rb") as rf:
    #     sc.append(rf.read())
    # with open("last_1.png", "rb") as rf:
    #     sc.append(rf.read())

    assert len(sc.get_all()) == 1

    with open("last.jpg", "wb") as wf:
        wf.write(sc.get_all()[0])

    # imshow(sc.qthumbnail())
