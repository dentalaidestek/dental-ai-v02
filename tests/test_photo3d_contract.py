import unittest

from vision_service.photo3d import Photo3DError, reconstruct


class Photo3DContractTests(unittest.TestCase):
    def test_empty_input_is_rejected(self):
        with self.assertRaises(Photo3DError):
            reconstruct([])


if __name__ == "__main__":
    unittest.main()
