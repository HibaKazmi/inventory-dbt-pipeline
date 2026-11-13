# The pipeline as a story

## 1. The situation

An online shop has **two warehouses, W01 and W02**. Each warehouse sends the
operations team CSV files listing every stock movement: goods **received**,
goods **shipped**, and **adjustments** (corrections after a count).

The files are messy:

* the same movement is sometimes sent **twice**;
* some rows are **broken**: no product, a quantity of `2.5`, a timestamp that isn't a date;
* some movements arrive **late**: today's file contains something that happened two days ago.

The operations team wants one simple answer they can trust:

> For every product, in every warehouse, on every day: how much stock did we
> have, and did it go negative?

## 2. The rules

Before writing any SQL, I wrote down what "valid" means. Every row ends up as
**kept**, **rejected** (with a reason) or **duplicate**. Full list with examples:
[`rules.txt`](rules.txt).

## 3. Test data made on purpose

I hand-wrote a small set of rows where I already know the right answer: the
**correctness fixture** (the PDF's term). Each row tests one rule.

| Row | What it is | Expected |
|---|---|---|
| M001 receipt 20 | normal | kept |
| M002 shipment 5, **twice** | duplicate | first kept, second = duplicate |
| M004 shipment 30 | pushes stock below 0 | kept, day flagged negative |
| M005 with no product | broken | rejected: `missing_product_id` |
| M009 type `transfer` | broken | rejected: `invalid_movement_type` |
| M012 quantity `2.5` | broken | rejected: `non_integer_quantity` |
| M013 timestamp `not-a-timestamp` | broken | rejected: `unparseable_event_timestamp` |
| 03-02 for P102/W02 | no movements that day | still gets a row |
| *later file:* M015 dated 03-02 | late | changes 03-02 and every day after |
| *later file:* M002 again | re-sent | duplicate |

The expected results are written down **before** running anything
(`dbt_project/seeds/expected_*.csv`), and dbt tests compare the real output
with them.

## 4. Landing the files (Load)

`loader/load_raw.py` copies each CSV into the table `raw.raw_movements`
**exactly as received**, every column as text, plus the file name, row number
and a `load_id`. Nothing is cleaned yet, so a reviewer can always see the original row.

The loader also fingerprints each file (SHA-256). If the same file is offered
again, it is skipped. This is the first protection against counting twice.

## 5. Checking every row (Transform, step 1): `stg_movements`

Each row is tidied (spaces, case), converted to proper types (number, timestamp,
date), and checked against the rules. The first rule it breaks becomes its
`rejection_reason`. No row is removed here.

## 6. Sorting the rows (step 2): `int_movements_classified`

Every row gets one label: **accepted**, **rejected**, or **duplicate**
(a later copy of an accepted movement). Rows in = accepted + rejected + duplicate.

## 7. The two lists the team asked for (step 3)

* `clean_movements`: accepted rows, with a signed quantity (+ in, − out).
* `rejected_movements`: broken rows with the reason, for someone to follow up.

## 8. Counting stock per day (step 4): `int_daily_activity` → `daily_inventory`

1. Add up what came in, went out and was adjusted, per product, warehouse and day.
2. Lay out a calendar for each product and warehouse, from its first movement to
   the last date in the data, so quiet days are included.
3. Keep a running total like a bank balance: today's closing = yesterday's closing
   + today's movements. Flag any day below zero.

| date | opening | in | out | adj | closing |
|---|---|---|---|---|---|
| 03-01 | 0 | 20 | 5 | 0 | 15 |
| 03-02 | 15 | 0 | 0 | −2 | 13 |
| 03-03 | 13 | 0 | 30 | 0 | **−17** ⚑ |
| 03-04 | −17 | 0 | 0 | 0 | **−17** ⚑ |

## 9. Proving it (dbt tests)

Every build runs 53 checks, for example: no movement counted twice, no missing
days, closing = opening + in − out + adjustment, and the whole daily table equals
the hand-calculated answer.

## 10. Running it again, and late files

* **Same files again:** the loader skips them, and the tables are rebuilt from the
  same rows, so nothing changes.
* **Late file:** its movements land on their real date. Because the balance is a
  running total recalculated on every build, that day and every later day update.
  P101/W01 goes from 15, 13, −17, −17 to 15, **23, −7, −7**.

## 11. What I would do next

This version recalculates all history on every run. That is simple and always
correct, but slower as history grows. The next step is **incremental**
processing: only recalculate from the earliest date that changed.
