"""Guard the design-system color tokens against WCAG AA contrast regressions.

The token file scripts/qt-preview-tokens.json is the single source of truth for
the workbench style (see docs/design-system.md). Any token edit must keep the
pairs below readable: 4.5:1 for normal text, 2.5:1 floor for WCAG-exempt
disabled text. Runs without Qt.
"""
import json
import unittest
from pathlib import Path

TOKENS = json.loads((Path(__file__).resolve().parents[1] / 'scripts' / 'qt-preview-tokens.json').read_text('utf-8'))['aliases']['colors']


def luminance(hex_color):
    value = hex_color.lstrip('#')
    r, g, b = (int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
    def channel(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(fg, bg):
    a, b = luminance(fg), luminance(bg)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)


# Text pairs that must pass WCAG AA 4.5:1 in both themes.
# (label, foreground alias, background alias)
AA_PAIRS = [
    ('body on canvas', 'text_primary', 'canvas_background'),
    ('muted labels on canvas', 'text_secondary', 'canvas_background'),
    ('status bar text', 'text_secondary', 'surface_secondary'),
    ('timestamps and RX tag', 'text_tertiary', 'canvas_background'),
    ('TX tag / info state', 'brand_foreground', 'canvas_background'),
    ('WARN tag', 'warning_foreground', 'canvas_background'),
    ('ERROR tag', 'danger_foreground', 'canvas_background'),
    ('connected state', 'success_foreground', 'canvas_background'),
    ('pause badge', 'warning_foreground', 'warning_background'),
    ('checked filter chip', 'brand_foreground', 'brand_background_subtle'),
    ('primary button', 'text_on_brand', 'brand_background'),
    ('selected list row', 'text_primary', 'brand_background_subtle'),
]

# WCAG exempts disabled text; keep a legibility floor instead.
DISABLED_PAIRS = [
    ('disabled text', 'text_disabled', 'surface_disabled'),
]


class TokenContrastTests(unittest.TestCase):
    def test_normal_text_meets_aa(self):
        for theme in ('light', 'dark'):
            for label, fg, bg in AA_PAIRS:
                ratio = contrast(TOKENS[fg][theme], TOKENS[bg][theme])
                self.assertGreaterEqual(ratio, 4.5, f'{theme} {label}: {fg} on {bg} is {ratio:.2f}:1')

    def test_disabled_text_stays_legible(self):
        for theme in ('light', 'dark'):
            for label, fg, bg in DISABLED_PAIRS:
                ratio = contrast(TOKENS[fg][theme], TOKENS[bg][theme])
                self.assertGreaterEqual(ratio, 2.5, f'{theme} {label}: {fg} on {bg} is {ratio:.2f}:1')


if __name__ == '__main__':
    unittest.main()
