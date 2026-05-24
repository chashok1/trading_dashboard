-- Rule Groups: Hierarchical composition of composite rules and other groups
-- Enables nesting and AND/OR logic for complex rule combinations

CREATE TABLE IF NOT EXISTS ref_trig_rule_group (
    rule_group_code VARCHAR(50) PRIMARY KEY,
    group_type VARCHAR(20) NOT NULL DEFAULT 'action',  -- 'action' or 'logical'
    action_label VARCHAR(20),                           -- SA, BM, HOLD, etc (null if logical)
    priority INT,                                       -- lower = higher priority (from parm AR)
    category VARCHAR(50),
    intent_text TEXT,
    deprecated_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT action_label_check CHECK (
        (group_type = 'action' AND action_label IS NOT NULL) OR
        (group_type = 'logical' AND action_label IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS ref_trig_group_member (
    rule_group_code VARCHAR(50) NOT NULL,
    member_code VARCHAR(50) NOT NULL,                   -- composite_rule_code or rule_group_code
    member_type VARCHAR(20) NOT NULL,                   -- 'composite' or 'group'
    logic_operator VARCHAR(5) NOT NULL DEFAULT 'AND',  -- AND or OR
    sequence INT NOT NULL,
    FOREIGN KEY (rule_group_code) REFERENCES ref_trig_rule_group(rule_group_code) ON DELETE CASCADE,
    PRIMARY KEY (rule_group_code, member_code, sequence),
    CONSTRAINT logic_operator_check CHECK (logic_operator IN ('AND', 'OR'))
);

-- Priority mapping: action_label -> priority (from Parm table AR column)
-- Sell All = 1 (highest), Sell To Market = 2, Sell Short = 3, Buy More = 4, Hold = 5 (lowest)

-- Example groups (commented out — user creates via UI)
-- INSERT INTO ref_trig_rule_group VALUES
-- ('SA-Strong-Signal', 'action', 'SA', 1, 'Multi-Signal', 'Trend AND Trade both confirm sell', NULL, now())
-- ON CONFLICT DO NOTHING;
--
-- INSERT INTO ref_trig_group_member VALUES
-- ('SA-Strong-Signal', '899-SA-Trend-Breaks', 'composite', 'AND', 1),
-- ('SA-Strong-Signal', '888-SA-Trade-Breaks', 'composite', 'AND', 2)
-- ON CONFLICT DO NOTHING;
