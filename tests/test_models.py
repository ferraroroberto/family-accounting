import pytest

from family_accounting.models import Category, Expense


class TestCategory:
    def test_category_values(self):
        assert Category.FOOD == "food"
        assert Category.RENT == "rent"
        assert Category.UTILITIES == "utilities"
        assert Category.TRANSPORT == "transport"
        assert Category.ENTERTAINMENT == "entertainment"
        assert Category.HEALTH == "health"
        assert Category.EDUCATION == "education"
        assert Category.OTHER == "other"

    def test_category_is_str(self):
        assert isinstance(Category.FOOD, str)


class TestExpense:
    def test_basic_creation(self):
        expense = Expense(
            description="Groceries",
            amount=60.0,
            category=Category.FOOD,
            paid_by="Alice",
            shared_by=["Alice", "Bob"],
        )
        assert expense.description == "Groceries"
        assert expense.amount == 60.0
        assert expense.category == Category.FOOD
        assert expense.paid_by == "Alice"
        assert expense.shared_by == ["Alice", "Bob"]

    def test_share_per_person_equal_split(self):
        expense = Expense(
            description="Dinner",
            amount=90.0,
            category=Category.FOOD,
            paid_by="Alice",
            shared_by=["Alice", "Bob", "Carol"],
        )
        assert expense.share_per_person == 30.0

    def test_share_per_person_single(self):
        expense = Expense(
            description="Bus ticket",
            amount=10.0,
            category=Category.TRANSPORT,
            paid_by="Bob",
            shared_by=["Bob"],
        )
        assert expense.share_per_person == 10.0

    def test_amount_must_be_positive(self):
        with pytest.raises(ValueError, match="amount must be positive"):
            Expense(
                description="Bad",
                amount=0.0,
                category=Category.OTHER,
                paid_by="Alice",
                shared_by=["Alice"],
            )

    def test_negative_amount_raises(self):
        with pytest.raises(ValueError, match="amount must be positive"):
            Expense(
                description="Bad",
                amount=-5.0,
                category=Category.OTHER,
                paid_by="Alice",
                shared_by=["Alice"],
            )

    def test_paid_by_must_not_be_empty(self):
        with pytest.raises(ValueError, match="paid_by must not be empty"):
            Expense(
                description="Bad",
                amount=10.0,
                category=Category.OTHER,
                paid_by="",
                shared_by=["Alice"],
            )

    def test_shared_by_must_not_be_empty(self):
        with pytest.raises(ValueError, match="shared_by must not be empty"):
            Expense(
                description="Bad",
                amount=10.0,
                category=Category.OTHER,
                paid_by="Alice",
                shared_by=[],
            )

    def test_paid_by_must_be_in_shared_by(self):
        with pytest.raises(ValueError, match="paid_by must be included in shared_by"):
            Expense(
                description="Bad",
                amount=10.0,
                category=Category.OTHER,
                paid_by="Alice",
                shared_by=["Bob"],
            )
