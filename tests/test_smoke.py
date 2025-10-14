"""Smoke tests for PostgreSQL migration validation.

Tests enrollment, balances, transactions, and data persistence
as required by Phase 1 of the migration plan.
"""
import datetime as dt
from decimal import Decimal

from sqlalchemy import text
from python.repository import Repository


def test_enroll_demo_user(repo):
    """Test user enrollment: create user and verify persistence."""
    user = repo.upsert_user(
        user_id="test_user_001",
        access_token="test_token_001",
        name="Demo User"
    )
    
    assert user.id == "test_user_001"
    assert user.access_token == "test_token_001"
    assert user.name == "Demo User"
    
    retrieved = repo.get_user_by_token("test_token_001")
    assert retrieved is not None
    assert retrieved.id == "test_user_001"


def test_account_creation(repo):
    """Test account creation and association with user."""
    user = repo.upsert_user(
        user_id="test_user_002",
        access_token="test_token_002",
        name="Account Test User"
    )
    
    account_payload = {
        "id": "acc_test_001",
        "name": "Test Checking Account",
        "institution": {"id": "chase", "name": "Chase"},
        "type": "depository",
        "subtype": "checking",
        "currency": "USD",
        "last_four": "1234"
    }
    
    account = repo.upsert_account(user, account_payload)
    
    assert account.id == "acc_test_001"
    assert account.name == "Test Checking Account"
    assert account.institution == "chase"
    assert account.type == "depository"
    assert account.currency == "USD"
    
    accounts = repo.list_accounts(user)
    assert len(accounts) == 1
    assert accounts[0].id == "acc_test_001"


def test_account_reassignment_on_reenroll(repo, session_factory):
    """Existing accounts should be re-linked when Teller issues a new user id."""

    first_user = repo.upsert_user(
        user_id="test_user_original",
        access_token="token_original",
        name="First User",
    )
    payload = {
        "id": "acc_reassign_001",
        "name": "Primary Checking",
        "type": "depository",
        "subtype": "checking",
        "currency": "USD",
    }
    account = repo.upsert_account(first_user, payload)
    repo.session.commit()

    # Simulate a subsequent Teller Connect session returning a different user id
    # for the same underlying accounts.
    second_user = repo.upsert_user(
        user_id="test_user_reenrolled",
        access_token="token_reenrolled",
        name="Second User",
    )
    repo.upsert_account(second_user, payload)
    repo.session.commit()

    # The existing account record should now belong to the newest user and be
    # hidden from the original user.
    repo.session.refresh(account)
    assert account.user_id == second_user.id

    # Verify visibility through a fresh session to mirror API behaviour.
    with session_factory() as new_session:
        fresh_repo = Repository(new_session)
        first_user_accounts = fresh_repo.list_accounts(first_user)
        reenrolled_accounts = fresh_repo.list_accounts(second_user)

    assert not first_user_accounts
    assert [acct.id for acct in reenrolled_accounts] == [account.id]


def test_balance_update(repo, session):
    """Test balance refresh and caching."""
    user = repo.upsert_user(
        user_id="test_user_003",
        access_token="test_token_003",
        name="Balance Test User"
    )
    
    account_payload = {
        "id": "acc_test_002",
        "name": "Test Savings",
        "type": "depository",
        "subtype": "savings",
        "currency": "USD"
    }
    account = repo.upsert_account(user, account_payload)
    
    balance_payload = {
        "available": "1234.56",
        "ledger": "1234.56",
        "currency": "USD"
    }
    
    balance = repo.update_balance(account, balance_payload)
    session.flush()
    
    assert balance.available == Decimal("1234.56")
    assert balance.ledger == Decimal("1234.56")
    assert balance.currency == "USD"
    assert balance.cached_at is not None
    
    result = session.execute(
        text("SELECT available, ledger FROM balances WHERE account_id = :account_id"),
        {"account_id": "acc_test_002"}
    ).fetchone()
    
    assert result is not None
    assert float(result[0]) == 1234.56
    assert float(result[1]) == 1234.56


def test_transaction_replacement(repo, session):
    """Test transaction refresh and replacement logic."""
    user = repo.upsert_user(
        user_id="test_user_004",
        access_token="test_token_004",
        name="Transaction Test User"
    )
    
    account_payload = {
        "id": "acc_test_003",
        "name": "Test Account",
        "type": "depository",
        "currency": "USD"
    }
    account = repo.upsert_account(user, account_payload)
    
    transactions_payload = [
        {
            "id": "txn_001",
            "description": "Coffee Shop",
            "amount": "-4.50",
            "date": "2025-10-10",
            "type": "card_payment",
            "running_balance": "1000.00"
        },
        {
            "id": "txn_002",
            "description": "Paycheck Deposit",
            "amount": "2500.00",
            "date": "2025-10-11",
            "type": "ach",
            "running_balance": "3500.00"
        }
    ]
    
    transactions = repo.replace_transactions(account, transactions_payload)
    session.flush()
    
    assert len(transactions) == 2
    assert transactions[0].id == "txn_001"
    assert transactions[0].description == "Coffee Shop"
    assert transactions[0].amount == Decimal("-4.50")
    
    count_result = session.execute(
        text("SELECT COUNT(*) FROM transactions WHERE account_id = :account_id"),
        {"account_id": "acc_test_003"}
    ).scalar()
    
    assert count_result == 2
    
    new_transactions_payload = [
        {
            "id": "txn_002",
            "description": "Paycheck Deposit",
            "amount": "2500.00",
            "date": "2025-10-11",
            "type": "ach",
            "running_balance": "3500.00"
        },
        {
            "id": "txn_003",
            "description": "Grocery Store",
            "amount": "-75.30",
            "date": "2025-10-12",
            "type": "card_payment",
            "running_balance": "3424.70"
        }
    ]
    
    transactions = repo.replace_transactions(account, new_transactions_payload)
    session.flush()
    
    count_result = session.execute(
        text("SELECT COUNT(*) FROM transactions WHERE account_id = :account_id"),
        {"account_id": "acc_test_003"}
    ).scalar()
    
    assert count_result == 2
    
    txn_001_exists = session.execute(
        text("SELECT COUNT(*) FROM transactions WHERE id = :id"),
        {"id": "txn_001"}
    ).scalar()
    
    assert txn_001_exists == 0


def test_data_persistence_across_sessions(session_factory, repo):
    """Test that data persists across database sessions."""
    user = repo.upsert_user(
        user_id="test_user_005",
        access_token="test_token_005",
        name="Persistence Test User"
    )
    repo.session.commit()
    
    new_session = session_factory()
    new_repo = Repository(new_session)
    
    try:
        retrieved_user = new_repo.get_user_by_token("test_token_005")
        
        assert retrieved_user is not None
        assert retrieved_user.id == "test_user_005"
        assert retrieved_user.name == "Persistence Test User"
    finally:
        new_session.close()


def test_sql_row_count_verification(session):
    """Test SQL queries for verifying row counts as per Phase 1 requirements."""
    user_count = session.execute(text("SELECT COUNT(*) FROM users")).scalar()
    account_count = session.execute(text("SELECT COUNT(*) FROM accounts")).scalar()
    balance_count = session.execute(text("SELECT COUNT(*) FROM balances")).scalar()
    transaction_count = session.execute(text("SELECT COUNT(*) FROM transactions")).scalar()
    
    assert user_count >= 5
    assert account_count >= 3
    assert balance_count >= 1
    assert transaction_count >= 2
