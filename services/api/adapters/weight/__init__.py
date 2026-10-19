"""Weight adapter: side-view frame to a kilogram range (PRD Section 4.3)."""

from .formulas import ellipse_girth, weight_from_image, weight_from_tape_girth
from .measure import estimate_weight, find_landmarks, marker_px_per_cm, segment_cow
