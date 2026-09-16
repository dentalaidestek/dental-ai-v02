import unittest

from benchmark.vision48_gold.source_catalog import BLOCKED_FROM_GOLD, SOURCES, VISION48, coverage


class GoldBenchmarkContractTests(unittest.TestCase):
    def test_all_48_codes_have_a_coverage_slot(self):
        self.assertEqual(len(VISION48), 48)
        self.assertEqual(set(coverage()), set(VISION48))

    def test_gold_sources_are_never_training_sources(self):
        self.assertTrue(SOURCES)
        self.assertTrue(all(not s.allowed_for_training for s in SOURCES.values()))

    def test_known_leakage_sources_are_blocked(self):
        for name in ("DENTEX", "OralXrays-9", "kaggle31", "zenodo14"):
            self.assertIn(name, BLOCKED_FROM_GOLD)

    def test_hanoi_is_not_used_as_population_specificity_set(self):
        self.assertIn("positive-cohort", SOURCES["hanoi_periapical"].negative_coverage)

    def test_inredd_exact_mapping_is_conservative(self):
        exact = set(SOURCES["inredd_pan924"].exact_codes)
        self.assertIn("CARIES", exact)
        self.assertIn("ENDO_POST", exact)
        self.assertNotIn("FILLING", exact)


if __name__ == "__main__":
    unittest.main()
