from family_accounting.models import Category, Expense


class FamilyAccounting:
    """Tracks family expenses and computes per-person balances and compensations."""

    def __init__(self) -> None:
        self._expenses: list[Expense] = []

    def add_expense(self, expense: Expense) -> None:
        """Add an expense to the ledger."""
        self._expenses.append(expense)

    @property
    def expenses(self) -> list[Expense]:
        """Return all recorded expenses."""
        return list(self._expenses)

    def get_expenses_by_category(self, category: Category) -> list[Expense]:
        """Return all expenses belonging to *category*."""
        return [e for e in self._expenses if e.category == category]

    def get_totals_by_category(self) -> dict[Category, float]:
        """Return the total amount spent per category."""
        totals: dict[Category, float] = {}
        for expense in self._expenses:
            totals[expense.category] = totals.get(expense.category, 0.0) + expense.amount
        return totals

    def compute_balances(self) -> dict[str, float]:
        """Return the net balance for each person.

        A positive balance means the person is owed money; a negative balance
        means the person owes money to others.
        """
        balances: dict[str, float] = {}
        for expense in self._expenses:
            share = expense.share_per_person
            # The payer is credited the full amount they paid.
            balances[expense.paid_by] = balances.get(expense.paid_by, 0.0) + expense.amount
            # Each participant is debited their share.
            for person in expense.shared_by:
                balances[person] = balances.get(person, 0.0) - share
        return balances

    def compute_compensations(self) -> list[dict[str, object]]:
        """Return the minimal list of transfers needed to settle all debts.

        Each entry is a dict ``{"from": str, "to": str, "amount": float}``
        indicating that *from* should pay *amount* to *to*.
        """
        balances = self.compute_balances()

        # Separate into creditors (owed money) and debtors (owe money).
        creditors = sorted(
            [(person, amount) for person, amount in balances.items() if amount > 0.005],
            key=lambda x: x[1],
            reverse=True,
        )
        debtors = sorted(
            [(person, -amount) for person, amount in balances.items() if amount < -0.005],
            key=lambda x: x[1],
            reverse=True,
        )

        transactions: list[dict[str, object]] = []
        ci, di = 0, 0

        while ci < len(creditors) and di < len(debtors):
            creditor, credit = creditors[ci]
            debtor, debt = debtors[di]

            amount = min(credit, debt)
            transactions.append({"from": debtor, "to": creditor, "amount": round(amount, 2)})

            credit -= amount
            debt -= amount
            creditors[ci] = (creditor, credit)
            debtors[di] = (debtor, debt)

            if credit < 0.005:
                ci += 1
            if debt < 0.005:
                di += 1

        return transactions
