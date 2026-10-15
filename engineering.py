"""Transparent assessment rules. Provisional units; no automatic plant control."""
import re
import numpy as np
import pandas as pd
from detector import screen

DEFAULTS = dict(temperature_review_c=120., sec_increase_pct=20., persistence_days=3,
                prior_days=14, iqr_multiplier=1.5, minimum_reference_fraction=.8)
EVENT_FIELDS = ['date','plant','priority','category','asset','signal','title','value','unit',
                'rule','evidence','possible_causes','remote_checks','onsite_condition',
                'route','confidence','consecutive_days']

def definition(tag):
    """Mapping is explicit and exportable; unknown tags stay in recorded units."""
    name,unit,scale,confidence,kind=tag,'recorded units',1.,'Unmapped','other'
    if 'qz_temp' in tag: name,unit,confidence,kind='Front bearing temperature','°C','Medium','temperature'
    elif 'hz_temp' in tag: name,unit,confidence,kind='Rear bearing temperature','°C','Medium','temperature'
    elif tag.endswith('_wd'): name,unit,confidence,kind='Pump temperature (location unconfirmed)','°C','Medium','temperature'
    elif '_tt_zjs_' in tag: name,unit,confidence,kind='RO common feedwater temperature','°C','Medium','temperature'
    elif tag.endswith('_cz_o'): name,unit,confidence,kind='Vertical vibration velocity','mm/s','Medium-low','vibration'
    elif re.search(r'_[xyz]sd$',tag): name,unit,confidence,kind=f'{tag[-3].upper()} vibration velocity','mm/s','Medium','vibration'
    elif re.search(r'_[xyz]wy$',tag): name,unit,confidence,kind=f'{tag[-3].upper()} vibration displacement','µm','Medium','vibration'
    elif 'tur_zcs' in tag: name,unit,confidence,kind='UF product turbidity','NTU','Medium','turbidity'
    elif tag in ['rohsl','ufhsl']: name,unit,confidence,kind=f'{tag[:2].upper()} recovery','%','High','recovery'
    elif 'fluxf' in tag: name,unit,confidence,kind='UF membrane flux (flow is an alternative)','L/m²/h','Low','flux'
    elif 'cumulative' in tag: name,unit,confidence,kind='Cumulative runtime','h','Medium','counter'
    elif tag.startswith('advancedtags_') and tag.endswith('_lj'): name,unit,confidence,kind='Cumulative electrical energy','kWh','Medium','counter'
    elif tag.endswith('_ep'): name,unit,scale,confidence,kind='Cumulative electrical energy','kWh',.001,'Low','counter'
    elif tag.endswith('_costheta'): name,unit,scale,confidence,kind='Power factor','1',.001,'High','power_factor'
    elif re.search(r'_u[abc]$',tag): name,unit,scale,confidence,kind='Phase voltage','V',.1,'Medium','voltage'
    elif re.search(r'_i[abc]$',tag): name,unit,scale,confidence,kind='Phase current','A',.1,'Low','current'
    elif tag.endswith('_power'): name,unit,confidence,kind='Active electrical power','kW','Low','power'
    elif any(t in tag for t in ['frequency_feedback','fre_out','fr_out','pumpll']): name,unit,confidence,kind='Motor frequency / requested frequency','Hz','Medium','frequency'
    elif 'current_feedback' in tag or tag.endswith('_a_out'): name,unit,confidence,kind='Motor current feedback','A','Medium','current'
    elif tag.startswith('wg_'):
        suffix=tag.rsplit('_',1)[-1]
        if suffix in ['a1','a2','a3']: name,unit,confidence,kind='Phase voltage','V','High','voltage'
        elif suffix in ['a7','a8','a9']: name,unit,confidence,kind='Phase current','A','High','current'
        elif suffix=='a13': name,unit,confidence,kind='Three-phase active power','kW','High','power'
        elif suffix=='a58': name,unit,confidence,kind='Power factor','1','High','power_factor'
    elif tag.endswith('_fault_count'): name,unit,confidence,kind='Fault count','count','Medium','counter'
    elif re.search(r'_(bt_start|bt_stop|fault|output|rfb|run|start|stop)$',tag):
        name,unit,confidence,kind=tag.rsplit('_',1)[-1].replace('rfb','Running feedback'),'0/1','Medium','binary'
    asset='Plant / meter'
    m=re.search(r'(?:^|zz_|p_)([12])_rohigh_pressure',tag)
    b=re.search(r'ro([1-4])_high_pressure',tag)
    if m: asset='Pump '+m.group(1)
    elif b: asset='RO pump '+b.group(1)
    elif tag.startswith('wg_'): asset=tag.rsplit('_',1)[0]+' (asset association unconfirmed)'
    return dict(tag=tag,label=name,unit=unit,scale=scale,confidence=confidence,kind=kind,asset=asset,
                basis='Assessment assumption from tag context and ranges; not OEM verified')

def dictionary(df):
    return pd.DataFrame([definition(c) for c in df if c not in ['date','plant'] and '__' not in c and not c.startswith('pump_')])

def evaluate(equipment, perf, plant, config=None):
    cfg={**DEFAULTS,**(config or {})}; records=[]; coverage=[]
    e=equipment.set_index('date').sort_index()
    def emit(date,tag,title,category,value,rule,causes,remote,onsite,priority='Review',evidence='',streak=1):
        d=definition(tag)
        records.append(dict(zip(EVENT_FIELDS,[pd.Timestamp(date),plant,priority,category,d['asset'],tag,title,float(value),d['unit'],rule,evidence or f'{value:.4g} {d["unit"]}',causes,remote,onsite,
            'Prompt verification' if priority=='High' else 'Remote review first',d['confidence'],streak])))
    for tag in e.select_dtypes('number'):
        if '__' in tag or tag.startswith('pump_'): continue
        d=definition(tag);s=e[tag]*d['scale'];kind=d['kind']
        coverage.append(dict(signal=tag,meaning=d['label'],unit=d['unit'],observations=int(s.notna().sum()),
            missing=int(s.isna().sum()),status='Unavailable' if s.notna().sum()==0 else 'All zero: verify channel' if s.dropna().eq(0).all() else 'Available',
            engineering_check=kind in ['temperature','recovery','power_factor','binary','counter','frequency','current','voltage','vibration','turbidity','flux']))
        if kind=='temperature':
            for date,value in s[s>cfg['temperature_review_c']].items():
                emit(date,tag,'Extreme temperature reading','Engineering',value,f'> {cfg["temperature_review_c"]:g} °C; provisional assessment threshold',
                    'Real overheating; sensor/scaling fault; incorrect sensor assignment.',
                    'Check latest live value, units/scaling and available related current/vibration signals. Check existing alarms.',
                    'If the current high temperature is confirmed, or cannot be reliably verified remotely, escalate promptly to the site team under the plant SOP.',priority='High')
        bad=pd.Series(False,index=s.index)
        if kind=='temperature':bad=s < -273.15
        elif kind=='recovery':bad=(s<0)|(s>100)
        elif kind=='power_factor':bad=s.abs()>1
        elif kind=='binary':bad=s.notna()&~s.isin([0,1])
        elif kind in ['frequency','current','voltage','vibration','turbidity','flux','counter']:bad=s<0
        for date,value in s[bad].items():
            emit(date,tag,'Value inconsistent with assumed definition','Data quality',value,
                 'Temperature ≥ −273.15°C; recovery 0–100%; |power factor| ≤ 1; binary 0/1; nonnegative magnitude/counter',
                 'Scaling, tag mapping or measurement issue; recovery can also reflect unmatched periods or tank storage.',
                 'Check source units, signal mapping, measurement period and calculation boundaries.',
                 'Arrange instrument verification if remote configuration checks do not resolve the inconsistency.')
        if kind=='counter':
            for date,value in s[s.diff()<0].items():
                emit(date,tag,'Counter decreased','Data quality',value,'Current counter < previous recorded counter',
                     'Reset, rollover or invalid/stale measurement.','Check reset history. Do not calculate consumption across this interval.',
                     'Only if meter/reset behaviour cannot be explained remotely.')
        if kind in ['vibration','turbidity'] and s.notna().sum()>=12:
            result=screen(s,cfg['prior_days'],cfg['iqr_multiplier'])
            high=result['flag']&result.value.gt(result.upper_fence)
            # Missing calendar days break persistence.
            streak=high.groupby((~high).cumsum()).cumsum()
            for i,row in result.loc[high].iterrows():
                persistent=int(streak.loc[i])>=cfg['persistence_days']
                emit(row.date,tag,'Persistent upward deviation' if persistent else 'Upward deviation to investigate','Early indicator',row.value,
                     f'Above prior {cfg["prior_days"]}-day Q3 + {cfg["iqr_multiplier"]}×IQR',
                     'Changed operating load/speed; sensor issue; possible mechanical deterioration.' if kind=='vibration' else 'Changed feedwater conditions; filtration change; turbidity sensor issue.',
                     'Compare load, speed, cleaning state and related measurements on the flagged dates. A statistical change alone does not diagnose failure.',
                     'Inspection recommended if the change persists at comparable load and is corroborated by another signal or operating complaint.',
                     evidence=f'Value {row.value:.4g}; prior upper fence {row.upper_fence:.4g}; {int(streak.loc[i])} consecutive calendar day(s).',streak=int(streak.loc[i]))
    for k in ([1,2] if plant=='Plant A' else [1,2,3,4]):
        f=f'{k}_rohigh_pressure_pump_frequency_feedback_o' if plant=='Plant A' else f'c_m_ro{k}_high_pressure_pump_fre_out'
        p=f'zz_{k}_rohigh_pressure_pump_power' if plant=='Plant A' else f'c_m_ro{k}_high_pressure_pump_a_out'
        if f in e and p in e:
            for date in e.index[e[f].eq(0)&e[p].gt(0)]:
                emit(date,f,'Stopped-frequency signal conflicts with electrical reading','Data quality',0,'Frequency = 0 and paired electrical reading > 0',
                     'Daily aggregation mismatch; different asset mapping; stale measurement.',
                     'Compare timestamps, daily aggregation definitions and actual running feedback. This is not proof of wasted energy.',
                     'Only if live readings remain contradictory after remote checks.',evidence=f'{f}=0; {p}={e.loc[date,p]:.4g} recorded units')
    if not perf.empty:
        p=perf.set_index('date').sort_index().reindex(pd.date_range(perf.date.min(),perf.date.max()))
        vol=p['effluent_volume_m3'];energy=p['daily_electricity_kwh'];feed=p['influent_volume_m3']
        sec=(energy/vol.where(vol>0)).where(energy>=0)
        w=cfg['prior_days'];minimum=max(3,int(np.ceil(w*cfg['minimum_reference_fraction'])))
        baseline=sec.shift(1).rolling(w,min_periods=minimum).median()
        basevol=vol.where(vol>0).shift(1).rolling(w,min_periods=minimum).median()
        hit=sec.gt(baseline*(1+cfg['sec_increase_pct']/100))&baseline.gt(0)
        streak=hit.groupby((~hit).cumsum()).cumsum()
        for date in p.index[hit]:
            low=vol.loc[date]<basevol.loc[date]*.8
            emit(date,'calculated_sec_kwh_m3','High energy per m³ with reduced output' if low else 'High energy per m³','Possible inefficiency',sec.loc[date],
                 f'SEC > prior {w}-day median by {cfg["sec_increase_pct"]:g}% (assessment heuristic)',
                 'Lower throughput while fixed loads continue; downtime/cleaning; demand changes.' if low else 'Changed feed conditions, runtime or pumping demand; possible hydraulic resistance; meter issue.',
                 'Check production demand, run hours, cleaning logs, feed conductivity/temperature and meter coverage. Compare similar operating loads before changing settings.',
                 'Send a technician if elevated SEC persists under comparable conditions and local pressure/flow checks or equipment inspection are needed.',
                 evidence=f'SEC {sec.loc[date]:.3f} kWh/m³ vs prior median {baseline.loc[date]:.3f}; output {vol.loc[date]:.1f} m³; electricity {energy.loc[date]:.1f} kWh.',streak=int(streak.loc[date]))
            records[-1].update(unit='kWh/m³',confidence='High for ratio; cause unconfirmed',asset='Whole plant')
        for col in ['effluent_volume_m3','influent_volume_m3','daily_electricity_kwh']:
            for date,value in p.loc[p[col]<0,col].items():
                emit(date,col,'Negative daily total','Data quality',value,'Daily volume / consumption must be nonnegative under the stated definition','Counter/reset or calculation issue.','Check source totals and period boundaries.','Meter inspection only if unresolved remotely.')
        for date in p.index[(vol>feed)&feed.gt(0)]:
            emit(date,'calculated_recovery','Product exceeds feed volume','Data quality',100*vol.loc[date]/feed.loc[date],'Apparent recovery >100%',
                 'Tank inventory changes; mismatched periods or flowmeters; calculation issue.','Check water balance, tank storage and aligned meter periods.','Verify flowmeters on site if reconciliation fails.')
            records[-1].update(unit='%',asset='Whole plant')
        for date in p.index[vol.eq(0)&energy.gt(0)]:
            emit(date,'daily_electricity_kwh','Electricity recorded with zero product','Possible inefficiency',energy.loc[date],'Product = 0; electricity > 0; SEC not calculated',
                 'Cleaning, standby, shutdown loads or missing production measurement.','Check cleaning schedule and meter validity before inferring waste.','Only if unplanned consumption cannot be explained remotely.')
            records[-1].update(unit='kWh',asset='Whole plant')
    out=pd.DataFrame(records,columns=EVENT_FIELDS)
    if not out.empty:
        for _, group in out.groupby(['signal','category','rule']):
            ordered=group.sort_values('date')
            runs=ordered.date.diff().ne(pd.Timedelta(days=1)).cumsum()
            out.loc[ordered.index,'consecutive_days']=ordered.groupby(runs).cumcount().add(1).to_numpy()
        out=out.sort_values(['priority','date'],ascending=[True,False]).reset_index(drop=True)
    return out,pd.DataFrame(coverage)
