"""Computershare parser."""

from __future__ import annotations

import copy
import csv
import datetime
from decimal import Decimal
from pathlib import Path

from cgt_calc.const import TICKER_RENAMES
from cgt_calc.exceptions import ParsingError, UnexpectedColumnCountError
from cgt_calc.model import ActionType, BrokerTransaction


def action_from_str(label: str) -> ActionType:
    """Convert string label to ActionType."""

    if label == "PAYROLL DEDUCTION":
        return ActionType.BUY
    if label == "DIVIDEND REINVESTMENT":
        return ActionType.REINVEST_DIVIDENDS
    if "SALE" in label:
        return ActionType.SELL

    raise ParsingError("computershare transactions", f"Unknown action: {label}")


class ComputershareTransaction(BrokerTransaction):
    """
    Represents a single computershare transaction.

    Example format:
    Transaction Date,Effective Date,Description,FMV,Amount,Share Price,Transaction Shares
    01/07/24,01/07/24,PAYROLL DEDUCTION,204.875,253.14,194.6312,1.3006
    30/04/24,30/04/24,DIVIDEND REINVESTMENT,193.315,43.66,193.315,0.2258
    """

    def __init__(
        self,
        row: list[str],
        file: str,
    ):
        """Create transaction from CSV row."""
        if len(row) != 7:
            raise UnexpectedColumnCountError(row, 7, file)

        date_str = row[0]
        date = datetime.datetime.strptime(date_str, "%d/%m/%y").date()

        action = action_from_str(row[2])
        symbol = "MYCOMPANY"

        if symbol is not None:
            symbol = TICKER_RENAMES.get(symbol, symbol)

        quantity = Decimal(row[6].replace(",", "")) if row[6] != "" else None
        price = Decimal(row[5]) if row[5] != "" else None
        fees = Decimal(0)

        if action in (ActionType.BUY, ActionType.REINVEST_DIVIDENDS):
            amount = -Decimal(row[4])
        else:
            amount = Decimal(row[4])

        if action == ActionType.SELL:
            if quantity is not None:
                quantity *= -quantity
            if quantity is not None and price is not None and amount is not None:
                fees = Decimal((quantity * price) - amount)

        currency = "USD"
        broker = "Computershare"

        super().__init__(
            date,
            action,
            symbol,
            "",
            quantity,
            price,
            fees,
            amount,
            currency,
            broker,
        )


def read_computershare_transactions(transactions_file: str) -> list[BrokerTransaction]:
    """Read Raw transactions from file."""
    try:
        with Path(transactions_file).open(encoding="utf-8") as csv_file:
            lines = list(csv.reader(csv_file))
    except FileNotFoundError:
        print(
            f"WARNING: Couldn't locate Computershare transactions file({transactions_file})"
        )
        return []

    transactions = [
        ComputershareTransaction(row, transactions_file) for row in lines[1:]
    ]

    transactions_with_balance: list[BrokerTransaction] = []

    for t in transactions:
        if t.action == ActionType.BUY:
            transaction_buy: ComputershareTransaction = copy.deepcopy(t)
            transaction_buy.action = ActionType.TRANSFER
            if transaction_buy.amount is not None:
                transaction_buy.amount *= -1

            transactions_with_balance += [transaction_buy, t]
        elif t.action == ActionType.REINVEST_DIVIDENDS:
            transaction_buy_reinvest: ComputershareTransaction = copy.deepcopy(t)
            transaction_buy_reinvest.action = ActionType.DIVIDEND
            if transaction_buy_reinvest.amount is not None:
                transaction_buy_reinvest.amount *= -1

            t.action = ActionType.BUY
            transactions_with_balance += [transaction_buy_reinvest, t]
        else:
            transactions_with_balance.append(t)

    return transactions_with_balance
