import unittest

import cv2
import numpy as np

from vision_service.cv_signals import root_filling_score


class RootFillingRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.image = np.full((220, 220), 105, np.uint8)
        cv2.ellipse(self.image, (110, 105), (26, 78), 0, 0, 360, 145, -1)
        self.tooth = {"fdi": 21, "bbox": [82, 25, 138, 185]}

    def test_long_narrow_root_line_is_accepted(self):
        treated = self.image.copy()
        cv2.line(treated, (110, 34), (110, 118), 245, 3)
        self.assertGreaterEqual(root_filling_score(treated, self.tooth), 0.58)

    def test_plain_root_and_wide_radiopacity_are_rejected(self):
        self.assertLess(root_filling_score(self.image, self.tooth), 0.58)
        wide = self.image.copy()
        cv2.rectangle(wide, (90, 35), (130, 115), 245, -1)
        self.assertLess(root_filling_score(wide, self.tooth), 0.58)


if __name__ == "__main__":
    unittest.main()
