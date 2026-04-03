import pytest

from family_accounting.accounting import FamilyAccounting
from family_accounting.models import Category, Expense


@pytest.fixture
def ledger() -> FamilyAccounting:
    return FamilyAccounting()


@pytest.fixture
def three_person_ledger() -> FamilyAccounting:
    """Alice, Bob and Carol with a few shared expenses."""
    fa = FamilyAccounting()
    fa.add_expense(
        Expense("Rent", 900.0, Category.RENT, paid_by="Alice", shared_by=["Alice", "Bob", "Carol"])
    )
    fa.add_expense(
        Expense(
            "Groceries", 60.0, Category.FOOD, paid_by="Bob", shared_by=["Alice", "Bob", "Carol"]
        )
    )
    fa.add_expense(
        Expense(
            "Electricity",
            90.0,
            Category.UTILITIES,
            paid_by="Carol",
            shared_by=["Alice", "Bob", "Carol"],
        )
    )
    return fa


class TestAddExpense:
    def test_expenses_list_starts_empty(self, ledger: FamilyAccounting):
        assert ledger.expenses == []

    def test_add_single_expense(self, ledger: FamilyAccounting):
        expense = Expense("Lunch", 30.0, Category.FOOD, paid_by="Alice", shared_by=["Alice", "Bob"])
        ledger.add_expense(expense)
        assert len(ledger.expenses) == 1
        assert ledger.expenses[0] is expense

    def test_expenses_returns_copy(self, ledger: FamilyAccounting):
        ledger.add_expense(
            Expense("Lunch", 30.0, Category.FOOD, paid_by="Alice", shared_by=["Alice", "Bob"])
        )
        returned = ledger.expenses
        returned.clear()
        assert len(ledger.expenses) == 1


class TestGetExpensesByCategory:
    def test_filter_by_category(self, three_person_ledger: FamilyAccounting):
        food = three_person_ledger.get_expenses_by_category(Category.FOOD)
        assert len(food) == 1
        assert food[0].description == "Groceries"

    def test_empty_for_missing_category(self, three_person_ledger: FamilyAccounting):
        health = three_person_ledger.get_expenses_by_category(Category.HEALTH)
        assert health == []

    def test_multiple_expenses_in_category(self, ledger: FamilyAccounting):
        ledger.add_expense(
            Expense("Lunch", 20.0, Category.FOOD, paid_by="Alice", shared_by=["Alice", "Bob"])
        )
        ledger.add_expense(
            Expense("Dinner", 40.0, Category.FOOD, paid_by="Bob", shared_by=["Alice", "Bob"])
        )
        food = ledger.get_expenses_by_category(Category.FOOD)
        assert len(food) == 2


class TestGetTotalsByCategory:
    def test_totals_by_category(self, three_person_ledger: FamilyAccounting):
        totals = three_person_ledger.get_totals_by_category()
        assert totals[Category.RENT] == 900.0
        assert totals[Category.FOOD] == 60.0
        assert totals[Category.UTILITIES] == 90.0

    def test_empty_ledger_returns_empty_dict(self, ledger: FamilyAccounting):
        assert ledger.get_totals_by_category() == {}

    def test_accumulates_same_category(self, ledger: FamilyAccounting):
        ledger.add_expense(
            Expense("Lunch", 20.0, Category.FOOD, paid_by="Alice", shared_by=["Alice"])
        )
        ledger.add_expense(
            Expense("Dinner", 30.0, Category.FOOD, paid_by="Alice", shared_by=["Alice"])
        )
        totals = ledger.get_totals_by_category()
        assert totals[Category.FOOD] == 50.0


class TestComputeBalances:
    def test_single_expense_equal_split(self, ledger: FamilyAccounting):
        ledger.add_expense(
            Expense("Rent", 600.0, Category.RENT, paid_by="Alice", shared_by=["Alice", "Bob"])
        )
        balances = ledger.compute_balances()
        # Alice paid 600, owes 300 → net +300
        assert balances["Alice"] == pytest.approx(300.0)
        # Bob paid 0, owes 300 → net -300
        assert balances["Bob"] == pytest.approx(-300.0)

    def test_balanced_expenses(self, ledger: FamilyAccounting):
        ledger.add_expense(
            Expense("Rent", 200.0, Category.RENT, paid_by="Alice", shared_by=["Alice", "Bob"])
        )
        ledger.add_expense(
            Expense("Food", 200.0, Category.FOOD, paid_by="Bob", shared_by=["Alice", "Bob"])
        )
        balances = ledger.compute_balances()
        assert balances["Alice"] == pytest.approx(0.0)
        assert balances["Bob"] == pytest.approx(0.0)

    def test_three_person_balances(self, three_person_ledger: FamilyAccounting):
        balances = three_person_ledger.compute_balances()
        # Total paid: Alice 900, Bob 60, Carol 90 = 1050
        # Each owes: 1050 / 3 = 350
        assert balances["Alice"] == pytest.approx(900.0 - 350.0)   # +550
        assert balances["Bob"] == pytest.approx(60.0 - 350.0)      # -290
        assert balances["Carol"] == pytest.approx(90.0 - 350.0)    # -260

    def test_balances_sum_to_zero(self, three_person_ledger: FamilyAccounting):
        balances = three_person_ledger.compute_balances()
        assert sum(balances.values()) == pytest.approx(0.0)

    def test_empty_ledger_returns_empty_dict(self, ledger: FamilyAccounting):
        assert ledger.compute_balances() == {}


class TestComputeCompensations:
    def test_single_uneven_expense(self, ledger: FamilyAccounting):
        ledger.add_expense(
            Expense("Rent", 600.0, Category.RENT, paid_by="Alice", shared_by=["Alice", "Bob"])
        )
        compensations = ledger.compute_compensations()
        assert len(compensations) == 1
        assert compensations[0]["from"] == "Bob"
        assert compensations[0]["to"] == "Alice"
        assert compensations[0]["amount"] == pytest.approx(300.0)

    def test_already_balanced_no_compensations(self, ledger: FamilyAccounting):
        ledger.add_expense(
            Expense("Rent", 200.0, Category.RENT, paid_by="Alice", shared_by=["Alice", "Bob"])
        )
        ledger.add_expense(
            Expense("Food", 200.0, Category.FOOD, paid_by="Bob", shared_by=["Alice", "Bob"])
        )
        assert ledger.compute_compensations() == []

    def test_three_persons_two_transfers(self, three_person_ledger: FamilyAccounting):
        compensations = three_person_ledger.compute_compensations()
        # Alice is owed 550; Bob owes 290; Carol owes 260.
        # Optimal settlement: Bob → Alice 290, Carol → Alice 260
        assert len(compensations) == 2
        by_from = {c["from"]: c for c in compensations}
        assert by_from["Bob"]["to"] == "Alice"
        assert by_from["Bob"]["amount"] == pytest.approx(290.0)
        assert by_from["Carol"]["to"] == "Alice"
        assert by_from["Carol"]["amount"] == pytest.approx(260.0)

    def test_compensations_settle_all_debts(self, three_person_ledger: FamilyAccounting):
        balances = three_person_ledger.compute_balances()
        compensations = three_person_ledger.compute_compensations()
        # Apply compensations and verify everyone reaches 0.
        settled = dict(balances)
        for c in compensations:
            settled[c["from"]] += c["amount"]  # type: ignore[operator]
            settled[c["to"]] -= c["amount"]  # type: ignore[operator]
        for person, balance in settled.items():
            assert balance == pytest.approx(0.0), f"{person} is not settled: {balance}"

    def test_empty_ledger_no_compensations(self, ledger: FamilyAccounting):
        assert ledger.compute_compensations() == []

    def test_partial_sharing(self, ledger: FamilyAccounting):
        # Alice pays for herself and Bob only; Carol is not involved.
        ledger.add_expense(
            Expense(
                "Cinema", 30.0, Category.ENTERTAINMENT, paid_by="Alice", shared_by=["Alice", "Bob"]
            )
        )
        compensations = ledger.compute_compensations()
        assert len(compensations) == 1
        assert compensations[0]["from"] == "Bob"
        assert compensations[0]["to"] == "Alice"
        assert compensations[0]["amount"] == pytest.approx(15.0)
