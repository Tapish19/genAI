import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def calculate():
    cfg = json.loads((ROOT / 'configs/cost_assumptions.json').read_text())
    rows = []
    record_bytes = cfg['dimension'] * cfg['bytes_per_float'] + cfg['id_bytes'] + cfg['metadata_and_text_bytes']
    for plan in cfg['self_host_plans']:
        n = plan['vectors']
        gb = n * record_bytes / 1e9
        ru = cfg['queries_per_month'] * max(.25, gb)
        wu = n * cfg['monthly_update_fraction'] * 2 * record_bytes / 1000
        recurring = gb * cfg['managed_storage_usd_per_gb_month'] + ru / 1e6 * cfg['managed_usd_per_million_read_units'] + wu / 1e6 * cfg['managed_usd_per_million_write_units']
        standard = max(cfg['managed_minimum_standard_usd'], recurring)
        if gb <= cfg['managed_free_storage_gb'] and ru <= 1e6 and wu <= 2e6:
            tier, managed = 'Starter', 0
        elif gb <= cfg['managed_builder_storage_gb'] and ru <= 2e6 and wu <= 5e6:
            tier, managed = 'Builder', cfg['managed_builder_usd']
        else:
            tier, managed = 'Standard', standard
        self_host = plan['usd_per_month'] * (1 + cfg['weekly_backup_fraction_of_vm'])
        rows.append({**plan, 'namespace_gb': gb, 'estimated_sqlite_disk_gb': gb * cfg['sqlite_disk_multiplier'],
                     'monthly_read_units': ru, 'monthly_write_units': wu,
                     'managed_metered_before_minimum_usd': recurring, 'managed_standard_usd': standard,
                     'managed_cheapest_tier': tier, 'managed_cheapest_usd': managed,
                     'self_host_with_weekly_backup_usd': self_host, 'savings_vs_cheapest_usd': managed - self_host,
                     'initial_managed_upsert_metered_usd': n * record_bytes / 1000 / 1e6 * cfg['managed_usd_per_million_write_units']})
    result = {'assumptions': cfg, 'record_bytes': record_bytes, 'rows': rows}
    (ROOT / 'artifacts/cost_comparison.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result

if __name__ == '__main__':
    print(json.dumps(calculate(), indent=2))
