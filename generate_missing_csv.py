missing_symbols = [
    'BBBY', 'CALY', 'COLO', 'CRIT', 'DGS2:FRED', 'DX=F',
    'FKU', 'JPY=X', 'THS', '^DJI', '^GVZ', '^MOVE', '^NYXBT',
    '^OVX', '^VOLQ', '^VVIX', '^VXD', '^VXN'
]

# Known TOS mappings based on common conventions
tos_mappings = {
    'DGS2:FRED': '2-Year Treasury',
    'DX=F': 'DXY',
    '^DJI': '$INDU',
    '^GVZ': '$GVZ',
    '^MOVE': '$MOVE',
    '^OVX': '$OVX',
    '^VOLQ': '$VOLQ',
    '^VVIX': '$VVIX',
    '^VXD': '$VXD',
    '^VXN': '$VXN',
    'JPY=X': 'JPYUSD',
}

print("rr_name,y_ticker,tos_ticker,contracts")
for sym in missing_symbols:
    rr_name = ""
    y_ticker = sym
    tos_ticker = tos_mappings.get(sym, "")
    contracts = ""
    print(f'"{rr_name}","{y_ticker}","{tos_ticker}","{contracts}"')
