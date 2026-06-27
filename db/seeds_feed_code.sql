-- Seeds for the feed catalog (TASK_97). Idempotent — safe to re-run.
-- Assigns one canonical feed_code per logical feed on both registries, so
-- v_feed_catalog can join a feed's filename recognizer (ref_load_files) to its
-- subject recognizer (ref_hedgeye_email_type). Apply after db/baseline.sql.

-- The 5 feeds that arrive BOTH as a file and as a Hedgeye email — one code each.
UPDATE ref_load_files SET feed_code='RISK_RANGE'          WHERE UPPER(file_type)='RR';
UPDATE ref_load_files SET feed_code='INVESTING_IDEAS'     WHERE UPPER(file_type)='IICHANGE';
UPDATE ref_load_files SET feed_code='ETF_CHANGES'         WHERE UPPER(file_type)='ETFCHANGE';
UPDATE ref_load_files SET feed_code='PORTFOLIO_SOLUTIONS' WHERE UPPER(file_type)='PS';
UPDATE ref_load_files SET feed_code='THE_CALL'            WHERE UPPER(file_type)='CALL';

UPDATE ref_hedgeye_email_type SET feed_code='RISK_RANGE'          WHERE email_type='risk_range';
UPDATE ref_hedgeye_email_type SET feed_code='INVESTING_IDEAS'     WHERE email_type='investing_ideas';
UPDATE ref_hedgeye_email_type SET feed_code='ETF_CHANGES'         WHERE email_type='etf_changes';
UPDATE ref_hedgeye_email_type SET feed_code='PORTFOLIO_SOLUTIONS' WHERE email_type='portfolio_solutions';
UPDATE ref_hedgeye_email_type SET feed_code='THE_CALL'            WHERE email_type='the_call';

-- Every remaining file-only / email-only feed gets a derived canonical code
-- (uppercased identifier). Run last so the explicit overlaps above win.
UPDATE ref_load_files         SET feed_code=UPPER(file_type)  WHERE feed_code IS NULL;
UPDATE ref_hedgeye_email_type SET feed_code=UPPER(email_type) WHERE feed_code IS NULL;
