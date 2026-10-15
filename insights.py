"""Incident grouping and prior-only production-matched comparisons."""
import hashlib
import numpy as np
import pandas as pd

INCIDENT_COLUMNS=['incident_id','start','end','flagged_days','priority','category','asset','signal','title','min_value','max_value','unit','rule','possible_causes','remote_checks','onsite_condition','confidence','last_observation','evidence']

def group_incidents(events):
    rows=[]
    if events.empty:return pd.DataFrame(columns=INCIDENT_COLUMNS)
    for key,g in events.groupby(['plant','signal','category','rule'],sort=False):
        g=g.sort_values('date').drop_duplicates('date')
        groups=g.date.diff().ne(pd.Timedelta(days=1)).cumsum()
        for _,block in g.groupby(groups):
            first,last=block.iloc[0],block.iloc[-1]
            ident=hashlib.sha256(('|'.join(key)+'|'+str(first.date.date())).encode()).hexdigest()[:10]
            rows.append(dict(incident_id=ident,start=first.date,end=last.date,flagged_days=len(block),
                priority='High' if block.priority.eq('High').any() else 'Review',category=last.category,
                asset=last.asset,signal=last.signal,title=last.title,min_value=block.value.min(),max_value=block.value.max(),
                unit=last.unit,rule=last.rule,possible_causes=last.possible_causes,remote_checks=last.remote_checks,
                onsite_condition=last.onsite_condition,confidence=last.confidence,
                last_observation='Last flagged date; resolution is not confirmed',evidence=last.evidence))
    return pd.DataFrame(rows,columns=INCIDENT_COLUMNS).sort_values(['priority','end'],ascending=[True,False]).reset_index(drop=True)

def compare_production(perf,lookback_days=60,tolerance=.2,min_peers=5,sec_threshold_pct=20.):
    """Similar daily output is a proxy, not proof of the same operating mode."""
    p=perf.sort_values('date').copy()
    p['sec']=p.daily_electricity_kwh.div(p.effluent_volume_m3.where(p.effluent_volume_m3>0)).where(p.daily_electricity_kwh>=0)
    rows=[]
    for _,r in p.iterrows():
        valid=pd.notna(r.sec) and np.isfinite(r.sec)
        earlier=p.loc[(p.date<r.date)&(p.date>=r.date-pd.Timedelta(days=lookback_days))&p.sec.notna()]
        peers=earlier.loc[earlier.effluent_volume_m3.between(r.effluent_volume_m3*(1-tolerance),r.effluent_volume_m3*(1+tolerance))] if valid else earlier.iloc[:0]
        median=peers.sec.median() if len(peers)>=min_peers else np.nan
        change=(r.sec/median-1)*100 if pd.notna(median) and median>0 else np.nan
        status='Invalid / unavailable SEC' if not valid else 'Insufficient comparable history' if pd.isna(change) else 'Elevated at similar production' if change>sec_threshold_pct else 'No elevated SEC at similar production'
        rows.append(dict(date=r.date,production_m3=r.effluent_volume_m3,sec=r.sec,peer_count=len(peers),peer_median_sec=median,change_pct=change,status=status,
                         peer_dates=', '.join(peers.date.dt.strftime('%Y-%m-%d')),comparison='Prior 60 days; daily product volume ±20%; ≥5 peers; not matched for runtime, cleaning or feed quality'))
    return pd.DataFrame(rows)

def contextualize(events,comparison):
    events=events.copy()
    if events.empty:return events
    bydate=comparison.set_index('date')
    for i,r in events.loc[events.signal.eq('calculated_sec_kwh_m3')].iterrows():
        c=bydate.loc[r.date]
        evidence=f' Production-matched check: {c.status}; {c.peer_count} prior peer day(s).'
        if pd.notna(c.change_pct): evidence+=f' SEC is {c.change_pct:+.1f}% versus peer median {c.peer_median_sec:.3f} kWh/m³.'
        events.loc[i,'evidence']+=evidence
        if c.status=='Elevated at similar production':events.loc[i,'title']='SEC elevated even at similar production'
        elif c.status=='No elevated SEC at similar production':events.loc[i,'title']='High overall SEC; output-matched comparison is not elevated'
        else:events.loc[i,'title']='High SEC; insufficient similar-production history'
    return events


def case_studies(events,incidents,comparison):
    """Select three distinct, traceable cases where available; no invented cases."""
    cases=[]
    if incidents.empty:return cases
    temp=incidents[incidents.category.eq('Engineering')&incidents.title.eq('Extreme temperature reading')]
    vib=incidents[incidents.category.eq('Early indicator')]
    pool=temp if not temp.empty else vib
    if not pool.empty:
        r=pool.sort_values(['flagged_days','max_value'],ascending=False).iloc[0]
        cases.append(dict(title='Persistent extreme temperature' if not temp.empty else 'Persistent signal change',start=r.start,end=r.end,signal=r.signal,
            finding=f'{r.flagged_days} consecutive flagged day(s), {r.min_value:.3f}–{r.max_value:.3f} {r.unit}.',
            interpretation='A sustained extreme reading needs verification even when a statistical baseline adapts to it.' if not temp.empty else 'Repeated deviations are stronger investigation leads than an isolated excursion, but operating load may explain them.',
            action=r.remote_checks,onsite=r.onsite_condition,limit='Assumed sensor definition and unit; no verified failure label.'))
    sec=events[events.signal.eq('calculated_sec_kwh_m3')]
    if not sec.empty:
        r=sec.sort_values('value',ascending=False).iloc[0]
        cases.append(dict(title='Highest flagged energy intensity',start=r.date,end=r.date,signal=r.signal,finding=r.evidence,
            interpretation='More electricity per m³ is an efficiency concern; the matched-output comparison shows whether a different production level alone is a plausible explanation.',
            action=r.remote_checks,onsite=r.onsite_condition,limit='Production matching does not match run hours, cleaning state, feed temperature or salinity. No causal diagnosis.'))
    quality=incidents[incidents.category.eq('Data quality')]
    if not quality.empty:
        recovery=quality[quality.signal.isin(['ufhsl','rohsl','calculated_recovery'])]
        r=(recovery if not recovery.empty else quality).sort_values('flagged_days',ascending=False).iloc[0]
        cases.append(dict(title='Data consistency must precede diagnosis',start=r.start,end=r.end,signal=r.signal,
            finding=f'{r.flagged_days} consecutive flagged day(s). '+r.evidence,interpretation=r.possible_causes,
            action=r.remote_checks,onsite=r.onsite_condition,limit='A measurement inconsistency is not a confirmed mechanical fault or proof of inefficient operation.'))
    return cases
