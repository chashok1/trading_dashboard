"""
compare_excel.py — compare drv_cat_atomic_input + drv_stks composite scores
against Excel-exported values for a given symbol and date.

Usage:
  python compare_excel.py AAPL 2026-06-01 [excel_indicator_values.txt] [excel_trig_values.txt]

If no files given, reads from stdin in two sections separated by a blank line:
  Section 1: tab-separated indicator values (header row + data row)
  Section 2: tab-separated composite codes + scores

Or pass indicator values inline on the command line.
"""
import sys, re, json, argparse
sys.path.insert(0, '.')
from config.settings import Settings
from sqlalchemy import create_engine, text
from collections import Counter

COL_MAP = {
    'MACDH Direction':'macdh_direction','MACD Direction':'macd_direction',
    'BB Direction':'bb_direction','BB Threshold':'bb_threshold',
    'BBThresh CO Days':'bbthresh_co_days','BBThresh_CO_Days2':'bbthresh_co_days2',
    'Trade Cross Over':'trade_cross_over','Trade-Rule':'trade_rule','!Trade Rule':'not_trade_rule',
    'Trend Cross Over':'trend_cross_over','Trend-Rule':'trend_rule','!Trend Rule':'not_trend_rule',
    'Trend Trade Dep Rule':'trend_trade_dep_rule','TrTn Relation':'trtn_relation',
    '!TrTn Relation':'not_trtn_relation','Trade Trend SD Rule':'trade_trend_sd_rule',
    'BRR% Rule':'brrpct_rule','BRR% LRR':'brrpct_lrr','BRR% R2':'brrpct_r2',
    'BRR% LRR2':'brrpct_lrr2','BRR% TRR':'brrpct_trr',
    'BRR% Puts':'brrpct_puts','BRR% TRR Puts':'brrpct_trr_puts','BRR% Dir':'brrpct_dir',
    'High TRR':'high_trr','Low LRR':'low_lrr','Trend below TRR':'trend_below_trr',
    'LRR above Trade':'lrr_above_trade','TRR_Idx':'trr_idx','MRR_Idx':'mrr_idx','LRR_Idx':'lrr_idx',
    'HVAbsolute':'hvabsolute','IVAbsolute':'ivabsolute',
    'IVPercentile':'ivpercentile','IVPercentile Puts':'ivpercentile_puts',
    'HVPercentile':'hvpercentile','HVPercentile Puts':'hvpercentile_puts',
    'IVHV':'ivhv','IVHV Puts':'ivhv_puts','IVRule':'ivrule',
    'RSI Rule':'rsi_rule','RSI Top':'rsi_top','RSI Puts':'rsi_puts',
    '3m-Low-Rule':'3m_low_rule','3m-Low-Days Rule':'3m_low_days_rule',
    '3mn-High-Rule':'3mn_high_rule','3mn-High-Days Rule':'3mn_high_days_rule','3m-Long':'3m_long',
    'Perf3mn SD Rule':'perf3mn_sd_rule','Perf2M SD Rule':'perf2m_sd_rule',
    'Perf3WK SD Rule':'perf3wk_sd_rule','Perf2WK SD Rule':'perf2wk_sd_rule',
    'Perf3D SD Rule':'perf3d_sd_rule','Perf1D SD Rule':'perf1d_sd_rule',
    '!Perf1D_sd':'not_perf1d_sd','Perf3D_sd_1off':'perf3d_sd_1off',
    'Perf SD Rule':'perf_sd_rule','!Perf SD Rule':'not_perf_sd_rule','!Perf3D Rule':'not_perf3d_rule',
    'BBHighLow_SD Rule':'bbhighlow_sd_rule','BBHighLow Days Rule':'bbhighlow_days_rule',
    'BBStreak Rule':'bbstreak_rule','BBStreakRule1':'bbstreakrule1','BBStreak Rule2':'bbstreak_rule2',
    'BBStreak Days Rule':'bbstreak_days_rule','BBStreak Days Rule2':'bbstreak_days_rule2',
    'BBStreak Days Rule3':'bbstreak_days_rule3','BBStreak Days Rule4':'bbstreak_days_rule4',
    'BB Bull Rule':'bb_bull_rule','BB Bull Puts':'bb_bull_puts',
    'BBHighDays':'bbhighdays','BBLowDays':'bblowdays',
    'MACD Rule':'macd_rule','MACDH Rule':'macdh_rule',
    'MACD and H Rule':'macd_and_h_rule','MACD_BRR Puts':'macd_brr_puts',
    'MACDH_BRR Puts':'macdh_brr_puts','MACD and H Rule Puts':'macd_and_h_rule_puts',
    'MACDH Days':'macdh_days','MACDH Days2':'macdh_days2',
    'Overbought':'overbought','!Overbought':'not_overbought',
    '3mn Outlook':'3mn_outlook','3mn Outlook Days':'3mn_outlook_days',
    '3wk Outlook':'3wk_outlook','3wk Outlook Days':'3wk_outlook_days',
    '!3wk ol':'not_3wk_ol','!3wk ol days':'not_3wk_ol_days',
    'BULL':'bull','!BULL':'not_bull','PerfOrBull':'perforbull','!PerfOrBull':'not_perforbull',
    '50-DMA-Rule':'50_dma_rule','50-DMA-Crossover':'50_dma_crossover',
    '200-DMA-Rule':'200_dma_rule','200-DMA-Crossover':'200_dma_crossover',
    '52-Wk Low Rule':'52_wk_low_rule','52-Wk High Rule':'52_wk_high_rule',
    'BRRTrade':'brrtrade','TRRTrade':'trrtrade',
    'Up Resistance':'up_resistance','Down Resistance':'down_resistance','Earnings':'earnings',
    'VS Price':'vs_price','VS Volume Spike':'vs_volume_spike',
    'VS Volatility':'vs_volatility','VS Days':'vs_days','VS LT Outlook Rule':'vs_lt_outlook_rule',
    'Current Price SD Rule':'current_price_sd_rule',
    'Current Volume Rule':'current_volume_rule','Current Volatility Rule':'current_volatility_rule',
    'Short Term Oulook (If LT Bullish)':'short_term_oulook_if_lt_bullish',
    'Short Term Oulook (If LT Bearish)':'short_term_oulook_if_lt_bearish',
}

def q(col):
    return '"'+col+'"' if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col) else col

def compare_indicators(eng, sym, date, xl_headers, xl_vals):
    """Compare indicator values (drv_cat_atomic_input) against Excel."""
    xl = {xl_headers[i]: xl_vals[i] for i in range(len(xl_headers))
          if xl_headers[i] not in ('Symbol','Begin','End')}
    db_cols = list(set(COL_MAP.values()))
    sel = ', '.join(q(c) for c in db_cols)
    with eng.connect() as c:
        row = c.execute(text(
            'SELECT '+sel+' FROM drv_cat_atomic_input WHERE tos_symbol=:s AND as_of_date=:d'
        ), {'s':sym,'d':date}).mappings().first()
    if not row:
        print('  [INDICATORS] No drv_cat_atomic_input row for %s on %s' % (sym, date))
        return
    db = dict(row)
    mismatches = []; ok = 0
    for hdr, dc in COL_MAP.items():
        if hdr not in xl: continue
        xv = xl[hdr]; dv = db.get(dc)
        try: xn = float(xv)
        except: xn = None
        try: dn = float(dv) if dv is not None else None
        except: dn = None
        if xn is None and dn is None: ok += 1
        elif xn is None or dn is None: mismatches.append((hdr, xv, dv, 'null'))
        elif abs(xn-dn) < 0.001: ok += 1
        else: mismatches.append((hdr, xv, dv, 'diff'))
    print('\n=== INDICATORS: %d OK, %d MISMATCH ===' % (ok, len(mismatches)))
    for hdr, xv, dv, t in mismatches:
        print('  %-35s  XL=%6s  DB=%6s' % (hdr[:35], xv, dv))

def compare_composites(eng, sym, date, xl_comp):
    """Compare composite scores (drv_stks) against Excel."""
    with eng.connect() as c:
        row = c.execute(text(
            'SELECT triggered_composite_ids FROM drv_stks WHERE tos_symbol=:s AND as_of_date=:d'
        ), {'s':sym,'d':date}).first()
    if not row or not row[0]:
        print('\n[COMPOSITES] No drv_stks row for %s on %s' % (sym, date))
        return
    comps = row[0] if isinstance(row[0], list) else json.loads(row[0])
    db_scores = {c['rule_id']: c['score'] for c in comps}
    all_codes = set(xl_comp.keys()) | set(db_scores.keys())
    mismatches = []; ok = 0; xl_only = []; db_only = []
    for code in sorted(all_codes):
        xl = xl_comp.get(code); db = db_scores.get(code)
        if xl is None: db_only.append((code, db))
        elif db is None: xl_only.append((code, xl))
        elif abs(float(xl)-float(db)) < 0.001: ok += 1
        else: mismatches.append((code, xl, db))
    print('\n=== COMPOSITES: %d OK, %d MISMATCH, %d XL-only, %d DB-only ===' % (
        ok, len(mismatches), len(xl_only), len(db_only)))
    for code, xl, db in mismatches:
        print('  %-45s  XL=%6s  DB=%6s' % (code[:45], xl, db))
    if xl_only:
        print('  XL-only (not in DB): %s' % ', '.join(c for c,_ in xl_only))
    if db_only:
        print('  DB-only (not in XL): %s' % ', '.join(c for c,_ in db_only))

def parse_tab_row(line):
    """Parse tab-separated values, stripping blanks from ends."""
    return [v.strip() for v in line.split('\t')]

def main():
    parser = argparse.ArgumentParser(description='Compare Excel vs DB for a symbol')
    parser.add_argument('symbol', help='Stock symbol e.g. AAPL')
    parser.add_argument('date', help='Date YYYY-MM-DD')
    parser.add_argument('input_file', nargs='?', help='Tab-separated Excel export file (optional)')
    args = parser.parse_args()

    sym = args.symbol.upper().strip()
    date = args.date.strip()
    eng = create_engine(Settings().sqlalchemy_url)

    print('Comparing %s on %s' % (sym, date))

    if args.input_file:
        lines = open(args.input_file, encoding='utf-8').read().strip().split('\n')
    else:
        print('Paste Excel data (headers tab then values tab, composites after End), Ctrl+D when done:')
        lines = sys.stdin.read().strip().split('\n')

    # Parse: find header row (has 'Begin' and 'End'), data row, and composite rows
    header_row = None
    data_row = None
    comp_rows = {}

    for i, line in enumerate(lines):
        parts = parse_tab_row(line)
        if 'Begin' in parts and 'End' in parts:
            header_row = parts
            # Next non-empty line is data
            for j in range(i+1, len(lines)):
                dp = parse_tab_row(lines[j])
                if any(v.strip() for v in dp):
                    data_row = dp
                    # After 'End' position, rest are composite codes
                    end_idx = header_row.index('End') if 'End' in header_row else len(header_row)
                    # Composite codes: headers after End
                    comp_headers = header_row[end_idx+1:]
                    comp_vals = dp[end_idx+1:] if len(dp) > end_idx+1 else []
                    for k, code in enumerate(comp_headers):
                        if code.strip() and k < len(comp_vals) and comp_vals[k].strip():
                            try:
                                comp_rows[code.strip()] = float(comp_vals[k].strip())
                            except ValueError:
                                pass
                    break
            break

    if header_row is None or data_row is None:
        print('Could not parse input. Expecting tab-separated rows with Begin/End markers.')
        sys.exit(1)

    # Indicators: between Begin and End
    begin_idx = header_row.index('Begin') if 'Begin' in header_row else 0
    end_idx = header_row.index('End') if 'End' in header_row else len(header_row)
    ind_headers = header_row[begin_idx:end_idx+1]
    ind_vals = data_row[begin_idx:end_idx+1] if len(data_row) > begin_idx else []

    # Parse indicator XL values
    xl_ind = {}
    for k, hdr in enumerate(ind_headers):
        if hdr.strip() in ('Begin', 'End', ''): continue
        if k < len(ind_vals) and ind_vals[k].strip():
            try:
                xl_ind[hdr.strip()] = float(ind_vals[k].strip())
            except ValueError:
                pass

    if xl_ind:
        compare_indicators(eng, sym, date, list(xl_ind.keys()), list(xl_ind.values()))
    if comp_rows:
        compare_composites(eng, sym, date, comp_rows)

    print()

if __name__ == '__main__':
    main()
