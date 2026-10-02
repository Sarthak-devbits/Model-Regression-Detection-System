"""The four support email categories. Used by the classifier and the golden dataset."""

from enum import StrEnum


class Category(StrEnum):
    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    GENERAL = "general"
