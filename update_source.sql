UPDATE ref_outlook_source SET source_table = 'hist_pk' WHERE source_table = 'hist_psrk';
SELECT COUNT(*) FROM ref_outlook_source WHERE source_table = 'hist_pk' AND source_code = 'PSRK';
