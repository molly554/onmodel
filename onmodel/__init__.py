"""onmodel: check whether an AI-generated on-model product photo still shows your product.

    from onmodel import score, check_pair
    card = score(checklist)                      # points, veto and "Verified" from a reviewer's nine answers
    record = check_pair(product, result, vlm=...)  # one product photo + one result photo -> a judgment record
"""

__version__ = "0.1.0"

from .scoring import ChecklistError, Scorecard, score  # noqa: E402
from .check import check_pair  # noqa: E402

__all__ = ["__version__", "ChecklistError", "Scorecard", "score", "check_pair"]
