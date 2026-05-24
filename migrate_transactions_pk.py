"""
Migrate hist_cst and hist_ft to allow NULL
quantity/price by switching from a composite PK that includes those columns
to a surrogate `id BIGSERIAL` PK + a UNIQUE index on a COALESCE-d natural
key tuple.

WHY: Fidelity 401(k) "Exchange In/Out" rows have NULL quantity. Cash sweeps
and dividend rows have NULL price. Both were blocked by the composite PK's
implicit NOT NULL on every column.

Safe to re-run — checks current PK shape and only acts if it's the old form.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text
from etl.db import session_scope


TABLES = ["hist_cst", "hist_ft"]


def has_old_pk(s, table: str) -> bool:
    """True iff the current PK is the old composite form including 'quantity'."""
    rows = s.execute(text("""
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = :t AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
    """), {"t": table}).all()
    cols = [r[0] for r in rows]
    return "quantity" in cols


def migrate_table(s, table: str):
    print(f"\n=== {table} ===")
    if not has_old_pk(s, table):
        # Even when the composite PK is gone, the formerly-PK columns may
        # STILL have residual NOT NULL constraints (Postgres doesn't drop
        # them when the PK is dropped). Make sure they're nullable.
        print("  PK is already migrated. Ensuring formerly-PK columns are nullable ...")
        drop_null_constraints(s, table)
        return

    # 1. Drop the old composite PK
    print("  Dropping old composite PK ...")
    s.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT {table}_pkey"))

    # 2. CRITICAL: drop the residual NOT NULL on quantity and price.
    # Postgres leaves the implicit NOT NULL constraints in place when a PK
    # is dropped — they were added by the PK but aren't tied to it. Without
    # this step, NULL quantity (401(k) Exchange In/Out) still fails.
    print("  Dropping residual NOT NULL on quantity, price, symbol ...")
    drop_null_constraints(s, table)

    # 3. Add surrogate id PK (BIGSERIAL → auto-increment)
    print("  Adding surrogate id PK ...")
    s.execute(text(f"ALTER TABLE {table} ADD COLUMN id BIGSERIAL PRIMARY KEY"))

    # 4. Add a UNIQUE NULLS NOT DISTINCT constraint on the natural key.
    # NULLS NOT DISTINCT (PG 15+) treats NULL = NULL for uniqueness, so
    # rows with NULL quantity (401(k) Exchange In/Out) or NULL price
    # (dividends, cash sweeps) still dedup correctly on re-imports.
    print("  Adding UNIQUE NULLS NOT DISTINCT constraint on natural key ...")
    s.execute(text(f"""
        ALTER TABLE {table}
        ADD CONSTRAINT uq_{table}_natural
        UNIQUE NULLS NOT DISTINCT
        (account, trade_date, action, symbol, quantity, price)
    """))
    print(f"  ✓ {table} migrated")


def drop_null_constraints(s, table: str):
    """Drop residual NOT NULL constraints on columns that used to be part of
    a composite PK. Idempotent — skips columns that are already nullable.

    `symbol` keeps its DEFAULT '' (the loader coerces empty to '' on insert)
    but is allowed to be NULL since not every row has a ticker.
    """
    nullable_cols = ("quantity", "price", "symbol", "action")
    for col in nullable_cols:
        try:
            s.execute(text(
                f"ALTER TABLE {table} ALTER COLUMN {col} DROP NOT NULL"
            ))
            print(f"    {col} → nullable")
        except Exception as e:
            # If the column wasn't NOT NULL, PG raises — ignore.
            msg = str(e).lower()
            if "is not a not-null" not in msg and "does not exist" not in msg:
                print(f"    {col}: {e}")


def main():
    print("=" * 70)
    print("Migrating transactions tables PK: composite → surrogate id")
    print("=" * 70)

    with session_scope() as s:
        for tbl in TABLES:
            migrate_table(s, tbl)
        s.commit()

    # Confirm
    with session_scope() as s:
        for tbl in TABLES:
            rows = s.execute(text("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_name = :t AND tc.constraint_type = 'PRIMARY KEY'
                ORDER BY kcu.ordinal_position
            """), {"t": tbl}).all()
            pk_cols = [r[0] for r in rows]
            n = s.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            print(f"\n{tbl}: PK={pk_cols}, rows={n}")
    print("\n✓ Migration complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
