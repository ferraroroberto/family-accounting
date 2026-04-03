from dataclasses import dataclass, field
from enum import Enum


class Category(str, Enum):
    FOOD = "food"
    RENT = "rent"
    UTILITIES = "utilities"
    TRANSPORT = "transport"
    ENTERTAINMENT = "entertainment"
    HEALTH = "health"
    EDUCATION = "education"
    OTHER = "other"


@dataclass
class Expense:
    description: str
    amount: float
    category: Category
    paid_by: str
    shared_by: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValueError("Expense amount must be positive")
        if not self.paid_by:
            raise ValueError("paid_by must not be empty")
        if not self.shared_by:
            raise ValueError("shared_by must not be empty")
        if self.paid_by not in self.shared_by:
            raise ValueError("paid_by must be included in shared_by")

    @property
    def share_per_person(self) -> float:
        return self.amount / len(self.shared_by)
