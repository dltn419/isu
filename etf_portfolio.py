"""One source of truth for ETF pricing weights and public look-through data."""

SECTORS = ('기술', '항공', '식품', '의료·제약', '미래사업')
WITHIN_SECTOR = (.35, .35, .15, .15)


def components(assets, sector='전체'):
    groups = SECTORS if sector == '전체' else (sector,)
    result = []
    for group in groups:
        stocks = [a for a in assets if a['type'] == 'stock' and a['sector'] == group]
        if len(stocks) != len(WITHIN_SECTOR):
            raise ValueError(f'ETF 구성 기업 수를 확인하세요: {group}')
        result.extend({'asset': a['id'], 'name': a['name'], 'sector': group,
                       'weight': w / len(groups)} for a, w in zip(stocks, WITHIN_SECTOR))
    return result


def index_return(returns, assets, sector='전체'):
    # Preserve the original sector-first arithmetic, as well as all price RNG calls.
    groups = SECTORS if sector == '전체' else (sector,)
    values = []
    for group in groups:
        stocks = [a for a in assets if a['type'] == 'stock' and a['sector'] == group]
        values.append(sum(returns[a['id']][1] * w for a, w in zip(stocks, WITHIN_SECTOR)))
    return sum(values) / len(values)


def attach(assets):
    for asset in assets:
        if asset['type'] != 'etf':
            continue
        multiplier = {'LEV2': 2, 'INV2': -2}.get(asset['id'], 1)
        holdings = components(assets, asset['sector'])
        asset['etf_composition'] = {
            'basis': 'daily_target_index_weights', 'multiplier': multiplier,
            'holdings': holdings,
            'sectors': [{'sector': sector,
                         'weight': sum(h['weight'] for h in holdings if h['sector'] == sector)}
                        for sector in SECTORS if any(h['sector'] == sector for h in holdings)],
            'company_count': len(holdings),
        }
