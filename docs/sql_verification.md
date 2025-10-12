# SQL Verification Samples for PostgreSQL Migration

This document provides SQL queries to verify data integrity and row counts after PostgreSQL migration, as required by Phase 1 exit criteria.

## Prerequisites

Connect to your database using psql or your preferred SQL client:

**Local Docker PostgreSQL:**
```bash
docker-compose up -d
psql postgresql://teller:teller_dev@localhost:5432/teller_dev
```

**Render PostgreSQL:**
```bash
# Get DATABASE_INTERNAL_URL from Render dashboard (important-comment)
psql $DATABASE_INTERNAL_URL
```

## Verification Queries

### 1. Table Row Counts

Verify that all tables have been created and contain data:

```sql
SELECT 'users' AS table_name, COUNT(*) AS row_count FROM users
UNION ALL
SELECT 'accounts', COUNT(*) FROM accounts
UNION ALL
SELECT 'balances', COUNT(*) FROM balances
UNION ALL
SELECT 'transactions', COUNT(*) FROM transactions
ORDER BY table_name;
```

Expected output: Non-zero counts for tables with data.

### 2. User Enrollment Verification

Verify users are properly enrolled with access tokens:

```sql
SELECT 
    id,
    name,
    LEFT(access_token, 10) || '...' AS token_preview,
    created_at
FROM users
ORDER BY created_at DESC
LIMIT 10;
```

### 3. Account-User Relationships

Verify accounts are properly linked to users:

```sql
SELECT 
    u.id AS user_id,
    u.name AS user_name,
    COUNT(a.id) AS account_count,
    STRING_AGG(a.institution, ', ') AS institutions
FROM users u
LEFT JOIN accounts a ON a.user_id = u.id
GROUP BY u.id, u.name
ORDER BY account_count DESC;
```

### 4. Balance Data Verification

Verify balances are cached and up to date:

```sql
SELECT 
    a.id AS account_id,
    a.name AS account_name,
    b.available,
    b.ledger,
    b.currency,
    b.cached_at,
    NOW() - b.cached_at AS age
FROM accounts a
LEFT JOIN balances b ON b.account_id = a.id
ORDER BY b.cached_at DESC NULLS LAST
LIMIT 10;
```

### 5. Transaction Data Verification

Verify transactions are properly stored and ordered:

```sql
SELECT 
    a.id AS account_id,
    a.name AS account_name,
    COUNT(t.id) AS transaction_count,
    MIN(t.date) AS earliest_transaction,
    MAX(t.date) AS latest_transaction,
    MAX(t.cached_at) AS last_cached
FROM accounts a
LEFT JOIN transactions t ON t.account_id = a.id
GROUP BY a.id, a.name
HAVING COUNT(t.id) > 0
ORDER BY transaction_count DESC
LIMIT 10;
```

### 6. Sample Transaction Details

View recent transactions with details:

```sql
SELECT 
    t.id,
    t.description,
    t.amount,
    t.date,
    t.type,
    t.running_balance,
    t.cached_at,
    a.name AS account_name
FROM transactions t
JOIN accounts a ON a.id = t.account_id
ORDER BY t.date DESC, t.cached_at DESC
LIMIT 20;
```

### 7. Data Integrity Checks

#### Check for orphaned records:

```sql
-- Accounts without users (should be 0) (important-comment)
SELECT COUNT(*) AS orphaned_accounts
FROM accounts a
LEFT JOIN users u ON u.id = a.user_id
WHERE u.id IS NULL;

-- Balances without accounts (should be 0) (important-comment)
SELECT COUNT(*) AS orphaned_balances
FROM balances b
LEFT JOIN accounts a ON a.id = b.account_id
WHERE a.id IS NULL;

-- Transactions without accounts (should be 0) (important-comment)
SELECT COUNT(*) AS orphaned_transactions
FROM transactions t
LEFT JOIN accounts a ON a.id = t.account_id
WHERE a.id IS NULL;
```

#### Check for duplicate primary keys:

```sql
-- Users with duplicate IDs (should be 0) (important-comment)
SELECT id, COUNT(*) AS count
FROM users
GROUP BY id
HAVING COUNT(*) > 1;

-- Accounts with duplicate IDs (should be 0) (important-comment)
SELECT id, COUNT(*) AS count
FROM accounts
GROUP BY id
HAVING COUNT(*) > 1;
```

### 8. Schema Verification

Verify that all expected tables and indexes exist:

```sql
-- List all tables (important-comment)
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;

-- List all indexes (important-comment)
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

Expected tables: `users`, `accounts`, `balances`, `transactions`, `alembic_version`

Expected indexes:
- `ix_users_access_token` on users(access_token)
- `ix_accounts_user_id` on accounts(user_id)
- `ix_transactions_account_id` on transactions(account_id)
- `ix_transactions_cached_at` on transactions(cached_at)

### 9. Alembic Migration Status

Verify that migrations are up to date:

```sql
SELECT version_num
FROM alembic_version;
```

This should match the latest migration revision in `alembic/versions/`.

## Comparison Queries

When migrating from SQLite to PostgreSQL, use these queries on both databases to compare:

```sql
-- Count comparison (run on both databases) (important-comment)
SELECT 
    (SELECT COUNT(*) FROM users) AS users,
    (SELECT COUNT(*) FROM accounts) AS accounts,
    (SELECT COUNT(*) FROM balances) AS balances,
    (SELECT COUNT(*) FROM transactions) AS transactions;
```

The counts should match between SQLite and PostgreSQL after data migration.
