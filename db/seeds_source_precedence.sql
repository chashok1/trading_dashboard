-- =====================================================
-- seeds_source_precedence.sql — TASK_140: seed ref_source_precedence with
-- today's SOURCE_ORDER values (etl/derive_actionable.py) as static_rank.
-- This row set is the rollback anchor for 'static' mode — do not renumber
-- these without also updating SOURCE_ORDER, or the two will disagree.
-- Applied by db/init_db.py after baseline.sql creates the table.
-- Idempotent: ON CONFLICT DO NOTHING (existing customisations survive re-run).
-- =====================================================

INSERT INTO ref_source_precedence (source_code, static_rank) VALUES
    ('RTA',     1),
    ('TOP5',    2),
    ('SSSCHG',  3),
    ('PS',      4),
    ('ETF',     5),
    ('RR',      6),
    ('SSS',     7),
    ('II',      8),
    ('CALL',    9),
    ('RTAINFO', 10),
    ('MACROSHOW', 11)
ON CONFLICT (source_code) DO NOTHING;
