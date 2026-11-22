"""Check the public gallery's uniform, uncropped, metadata-free images.

Run with: python3 -m unittest discover -s tests -p 'test_bird_gallery_images.py'
Requires Pillow.
"""
from pathlib import Path
import re
import unittest

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]


class BirdGalleryTest(unittest.TestCase):
    def test_gallery_images(self):
        gallery = ROOT / 'docs/BIRD_GALLERY.md'
        entries = re.findall(r'!\[([^]]+)\]\((images/gallery/[^)]+)\)', gallery.read_text())
        self.assertEqual(len(entries), 8)
        self.assertEqual(len({path for _, path in entries}), 8)
        for alt, relative in entries:
            with self.subTest(image=relative):
                self.assertTrue(alt)
                display = gallery.parent / relative
                self.assertTrue(display.name.endswith('-display.jpg'))
                original = display.with_name(display.name.replace('-display.jpg', '.jpg'))
                with Image.open(original) as source, Image.open(display) as result:
                    self.assertEqual(result.size, (1200, 900))
                    self.assertFalse(result.getexif())
                    self.assertFalse(set(result.info) - {'jfif', 'jfif_version', 'jfif_unit', 'jfif_density'})
                    source = source.convert('RGB')
                    source.thumbnail((1200, 900), Image.Resampling.LANCZOS)
                    x = (1200 - source.width) // 2
                    y = (900 - source.height) // 2
                    actual = result.crop((x, y, x + source.width, y + source.height)).convert('RGB')
                    mean_error = sum(ImageStat.Stat(ImageChops.difference(source, actual)).mean) / 3
                    self.assertLess(mean_error, 3, 'source image must remain centered and uncropped')


if __name__ == '__main__':
    unittest.main()
