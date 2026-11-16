"""Canonical upload budgets shared by web and native API adapters.

All values are binary MiB (1 MiB = 1,048,576 bytes). Keep the TypeScript
counterpart in mobile/src/uploadLimits.ts in sync; backend checks are final.
"""
MIB = 1024 * 1024

MAX_PATIENT_MEDIA_FILES = 12
MAX_PATIENT_MEDIA_FILE_BYTES = 12 * MIB
MAX_PATIENT_MEDIA_BATCH_BYTES = 96 * MIB

MAX_ANALYSIS_IMAGES = 4
MAX_ANALYSIS_IMAGE_BYTES = 25 * MIB
MAX_ANALYSIS_BATCH_BYTES = 80 * MIB

# Pillow decode work is separately bounded by pixel count in clinical_media.
MAX_CLINICAL_IMAGE_PIXELS = 40_000_000
