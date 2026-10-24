"""Audited, one-time settlement of the three user-approved practice markets.

Run without --apply to inspect the plan. A receipt prevents accidental reruns.
This maintenance script stops on errors; partial failures require reconciliation.
"""
import json
import sys
import uuid
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from resolve_market import resolve_market

CONFIG = dict(line.strip().split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
              if '=' in line and not line.startswith('#'))
BASE = CONFIG['SUPABASE_URL'].strip('"').rstrip('/') + '/rest/v1/'
KEY = CONFIG['SUPABASE_KEY'].strip('"')
RECEIPT = ROOT / 'practice_settlement_receipt.json'
MARKETS = {
    'b3b67f76-15bd-4321-81eb-71fb81d791f0': 'yes',
    'aa3657a1-dc3b-4f8a-882a-21e052389e87': 'yes',
    '5bca5239-c64f-46a3-9763-da0402e2f6b7': 'yes',
}
USERS = {'21eb7702-f65f-4c1b-9c2f-3e994410e32c', 'f4c80b09-1275-44f5-8681-4c07c5383ddd'}

def api(table, method='GET', query=None, body=None):
    url = BASE + table + ('?' + urlencode(query) if query else '')
    req = Request(url, method=method, data=None if body is None else json.dumps(body).encode(), headers={
        'apikey': KEY, 'Authorization': 'Bearer ' + KEY, 'User-Agent': 'PredictIN-Backend/1.0',
        'Content-Type': 'application/json', 'Prefer': 'return=representation',
    })
    with urlopen(req, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else None

def save(receipt):
    RECEIPT.write_text(json.dumps(receipt, indent=2))

def main():
    if RECEIPT.exists():
        raise RuntimeError('Receipt already exists. Inspect it before any further action; no automatic retry.')
    plan = []
    credits = {user: 0 for user in USERS}
    revenue = 0
    for mid, outcome in MARKETS.items():
        market = api('markets', query={'id': 'eq.' + mid})[0]
        assert market['description'].startswith('[PRACTICE]') and market['status'] in ('open', 'closed')
        orders = api('orders', query={'market_id': 'eq.' + mid, 'order': 'created_at.asc'})
        assert orders and all(o['status'] == 'active' and o['user_id'] in USERS for o in orders)
        assert sum(o['stake'] for o in orders if o['side'] == 'yes') == market['yes_pool']
        assert sum(o['stake'] for o in orders if o['side'] == 'no') == market['no_pool']
        result = resolve_market(outcome, orders)
        winners = orders if result['void'] else [o for o in orders if o['side'] == outcome]
        amounts = {o['id']: p['payout'] for o, p in zip(winners, result['payouts'])}
        for order in orders:
            credits[order['user_id']] += amounts.get(order['id'], 0)
        revenue += result['platform_revenue']
        plan.append({'market': market, 'orders': orders, 'amounts': amounts, 'outcome': outcome, 'void': result['void']})
    users = [api('users', query={'id': 'eq.' + uid, 'select': 'id,email,wallet_balance'})[0] for uid in sorted(USERS)]
    platform = api('platform_wallet', query={'id': 'eq.1'})[0]
    assert round(sum(credits.values()) + revenue, 2) == sum(p['market']['total_volume'] for p in plan)
    print(json.dumps({'credits': credits, 'platform_credit': revenue, 'markets': [p['market']['title'] for p in plan]}))
    if '--apply' not in sys.argv:
        return
    receipt = {'state': 'in_progress', 'plan': plan, 'users_before': users, 'platform_before': platform, 'steps': []}
    save(receipt)
    def step(name):
        receipt['steps'].append(name)
        save(receipt)
    # Freeze all targets, then verify no order arrived while preparing the plan.
    for p in plan:
        mid = p['market']['id']
        assert len(api('markets', 'PATCH', {'id': 'eq.' + mid, 'status': 'eq.' + p['market']['status']}, {'status': 'closed'})) == 1
        step('closed:' + mid)
        assert api('orders', query={'market_id': 'eq.' + mid, 'order': 'created_at.asc'}) == p['orders']
    for user in users:
        assert len(api('users', 'PATCH', {'id': 'eq.' + user['id'], 'wallet_balance': 'eq.' + str(user['wallet_balance'])},
                       {'wallet_balance': round(user['wallet_balance'] + credits[user['id']], 2)})) == 1
        step('credited:' + user['id'])
    assert len(api('platform_wallet', 'PATCH', {'id': 'eq.1', 'total_revenue': 'eq.' + str(platform['total_revenue'])},
                   {'total_revenue': round(platform['total_revenue'] + revenue, 2)})) == 1
    step('platform_credited')
    for p in plan:
        for order in p['orders']:
            amount = p['amounts'].get(order['id'], 0)
            status = 'refunded' if p['void'] else ('won' if order['side'] == p['outcome'] else 'lost')
            assert len(api('orders', 'PATCH', {'id': 'eq.' + order['id'], 'status': 'eq.active'}, {'status': status, 'payout': amount})) == 1
            step('order:' + order['id'])
            if amount:
                api('transactions', 'POST', body={
                    'id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'practice-settlement:' + order['id'])),
                    'user_id': order['user_id'], 'type': 'refund' if p['void'] else 'payout', 'amount': amount,
                    'status': 'completed', 'notes': 'Practice test-credit settlement: ' + p['market']['title'] + ' / order ' + order['id'],
                })
                step('transaction:' + order['id'])
        assert len(api('markets', 'PATCH', {'id': 'eq.' + p['market']['id'], 'status': 'eq.closed'},
                       {'status': 'voided' if p['void'] else 'resolved', 'outcome': None if p['void'] else p['outcome']})) == 1
        step('finished:' + p['market']['id'])
    users_after = [api('users', query={'id': 'eq.' + u['id'], 'select': 'id,email,wallet_balance'})[0] for u in users]
    for before, after in zip(users, users_after):
        assert after['wallet_balance'] == round(before['wallet_balance'] + credits[before['id']], 2)
    receipt['users_after'] = users_after
    receipt['state'] = 'complete'
    save(receipt)
    print(json.dumps({'state': 'complete', 'users': users_after, 'platform_credit': revenue}))

if __name__ == '__main__':
    main()
