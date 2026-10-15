"""Screen every eligible signal consistently; rank statistical review workload."""
import pandas as pd
from detector import screen
from engineering import definition

COLUMNS=['rank','signal','name','flagged_days','scored_days','flag_rate_pct','upward_flags','downward_flags','unscored_days','last_flag','status']

def rank_signals(equipment,signals,days=14,multiplier=1.5,mode='Prior rolling window',period='All available history'):
    results={};rows=[]
    indexed=equipment.set_index('date').sort_index()
    cutoff=indexed.index.max()-pd.Timedelta(days=29) if period=='Latest 30 days' else indexed.index.min()
    for signal in signals:
        # Always calculate with full prior history, then restrict reporting period.
        full=screen(indexed[signal],days,multiplier,mode)
        r=full.loc[full.date>=cutoff].copy().reset_index(drop=True)
        results[signal]=r
        scored=r.status.isin(['Within statistical band','Statistical deviation'])
        flags=r.flag
        n=int(scored.sum());f=int(flags.sum());d=definition(signal)
        rows.append(dict(signal=signal,name=f'{d["asset"]} · {d["label"]}',flagged_days=f,scored_days=n,
            flag_rate_pct=100*f/n if n else float('nan'),upward_flags=int((flags&r.value.gt(r.upper_fence)).sum()),
            downward_flags=int((flags&r.value.lt(r.lower_fence)).sum()),unscored_days=int((~scored).sum()),
            last_flag=r.loc[flags,'date'].max(),status='Flags to investigate' if f else 'No statistical flags' if n else 'Unscored — insufficient / flat reference'))
    if not rows:return pd.DataFrame(columns=COLUMNS),results
    table=pd.DataFrame(rows).sort_values(['flagged_days','scored_days','signal'],ascending=[False,False,True]).reset_index(drop=True)
    table.insert(0,'rank',range(1,len(table)+1))
    return table[COLUMNS],results
