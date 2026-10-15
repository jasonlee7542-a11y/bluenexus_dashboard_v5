"""Operator-facing evidence queue; recommendations are not dispatched."""
import hashlib
import pandas as pd
import streamlit as st
import plotly.express as px
from engineering import DEFAULTS, evaluate, dictionary, definition
from insights import group_incidents, compare_production, contextualize

def controls():
    with st.sidebar.expander('Engineering review settings'):
        st.caption('Assessment thresholds, not certified equipment limits.')
        t=st.number_input('Temperature review threshold (assumed °C)',value=120.,min_value=1.,step=5.)
        sec=st.number_input('SEC increase above prior median (%)',value=20.,min_value=1.,step=5.)
        persistence=st.number_input('Persistent change: consecutive days',value=3,min_value=2,max_value=30)
    return {**DEFAULTS,'temperature_review_c':t,'sec_increase_pct':sec,'persistence_days':int(persistence)}

def render(equipment,perf,plant,cfg):
    events,coverage=evaluate(equipment,perf,plant,cfg)
    comparison=compare_production(perf,sec_threshold_pct=cfg['sec_increase_pct'])
    events=contextualize(events,comparison)
    incidents=group_incidents(events)
    st.subheader('What needs attention?')
    latest=max(equipment.date.max(),perf.date.max())
    st.caption(f'Historical review · Latest available record: {latest:%d %b %Y} · No live connection to AquaxGo')
    st.write('Start with a high-priority event, read its evidence, then follow the remote checks. On-site attendance is conditional on verification; no action is sent automatically.')
    window=st.radio('Review period',['Latest 30 days','All available history'],horizontal=True)
    view=incidents.copy()
    if window=='Latest 30 days':view=view.loc[view.end>=latest-pd.Timedelta(days=29)]
    a,b,c,d=st.columns(4)
    a.metric('High-priority incidents',int(view.priority.eq('High').sum()))
    b.metric('Possible inefficiency incidents',int(view.category.eq('Possible inefficiency').sum()))
    c.metric('Data-quality incidents',int(view.category.eq('Data quality').sum()))
    d.metric('Unavailable / all-zero channels',int(coverage.status.ne('Available').sum()))
    st.caption('Repeated flags on consecutive calendar days are grouped by signal and rule. Incidents overlapping the selected period show their full history. Missing/unflagged days break a group. Last flagged date does not mean resolved; these are historical observations.')
    if window=='Latest 30 days' and (events.priority.eq('High')&events.date.lt(latest-pd.Timedelta(days=29))).any():
        st.warning('Earlier high-priority readings exist. Select All available history to review them, including historical temperature alerts.')
    options=sorted(view.category.unique())
    selected=st.multiselect('Show event types',options,default=options)
    view=view.loc[view.category.isin(selected)]
    row=None
    if view.empty:st.info('No events match this view. Check channel coverage and the equipment trends before drawing a conclusion.')
    else:
        st.markdown('#### Select an incident to investigate')
        st.info('👆 Select a row using the checkbox at its left to open the incident report below. Select another row to switch reports.')
        table=view[['start','end','flagged_days','priority','category','asset','title','min_value','max_value','unit']].reset_index(drop=True)
        # A new dataset/filter/settings view must not reuse an old row position.
        fingerprint=hashlib.sha256(pd.util.hash_pandas_object(view,index=True).values.tobytes()).hexdigest()[:16]
        selection=st.dataframe(table,hide_index=True,width='stretch',height=350,
            on_select='rerun',selection_mode='single-row',key=f'incident_table_{plant}_{fingerprint}',
            column_config={
                'start':st.column_config.DateColumn('First flagged',format='DD MMM YYYY'),
                'end':st.column_config.DateColumn('Last flagged',format='DD MMM YYYY'),
                'flagged_days':st.column_config.NumberColumn('Days',format='%d',width='small'),
                'priority':st.column_config.TextColumn('Priority',width='small'),
                'category':'Type','asset':'Equipment',
                'title':st.column_config.TextColumn('Incident — select row to open report',width='large'),
                'min_value':st.column_config.NumberColumn('Minimum',format='%.3f'),
                'max_value':st.column_config.NumberColumn('Maximum',format='%.3f'),
                'unit':'Unit'})
        positions=selection.selection.rows
        if positions and 0 <= positions[0] < len(view):
            row=view.iloc[positions[0]]
        if row is None:
            st.caption('No incident selected. Tick a row above to display its evidence, remote checks and on-site escalation guidance here.')
        else:
            st.markdown('#### Selected incident report')
            with st.container(border=True):
                st.markdown('### '+row.title)
                st.write(f'**Observed:** {row.start:%d %b %Y} to {row.end:%d %b %Y} · {row.flagged_days} consecutive flagged day(s) · range {row.min_value:.4g}–{row.max_value:.4g} {row.unit}')
                st.write('**Evidence from the last flagged day:** '+row.evidence)
                st.write('**Why flagged:** '+row.rule)
                st.write('**Possible explanations:** '+row.possible_causes)
                left,right=st.columns(2)
                with left:
                    st.markdown('**1. Check remotely**');st.write(row.remote_checks)
                with right:
                    st.markdown('**2. When to arrange a site visit**');st.write(row.onsite_condition)
                st.caption(f'Confidence: {row.confidence} · Original tag: {row.signal}')
                st.caption('AquaxGo may support remote investigation if the required readings/actions are available and approved. This prototype does not issue commands, adjust dosing or override interlocks.')
            if row.signal in equipment:
                info=definition(row.signal)
                trend=equipment[['date',row.signal]].copy();trend['Assumed value']=trend[row.signal]*info['scale']
                fig=px.line(trend,x='date',y='Assumed value',title=f'{info["label"]} · assumed {info["unit"]}')
                matching=events.loc[events.signal.eq(row.signal)]
                fig.add_scatter(x=matching.date,y=matching.value,mode='markers',name='Flagged reading',marker_color='#d94d4d')
                if info['kind']=='temperature':fig.add_hline(y=cfg['temperature_review_c'],line_dash='dash',annotation_text='Provisional review threshold')
                fig.add_vrect(x0=row.start,x1=row.end+pd.Timedelta(days=1),fillcolor='#e6a23c',opacity=.12,line_width=0)
                st.plotly_chart(fig,width='stretch')
            elif row.category=='Possible inefficiency':
                st.plotly_chart(px.line(perf,x='date',y='calculated_sec_kwh_m3',title='Plant electricity per m³ of product'),width='stretch')
    with st.expander('Daily evidence for the selected incident' if row is not None else 'All daily event evidence'):
        detail=events if row is None else events.loc[events.signal.eq(row.signal)&events.category.eq(row.category)&events.rule.eq(row.rule)&events.date.between(row.start,row.end)]
        st.dataframe(detail,hide_index=True,width='stretch')
    st.divider()
    st.subheader('Is energy intensity still high at similar production?')
    st.write('Each day is compared with earlier days producing within ±20% of its product volume, looking back up to 60 days. At least five comparable days are required. This controls for production level only; running, cleaning and standby modes remain unconfirmed.')
    st.dataframe(comparison[['date','production_m3','sec','peer_count','peer_median_sec','change_pct','status']],hide_index=True,width='stretch')
    st.plotly_chart(px.line(comparison,x='date',y=['sec','peer_median_sec'],labels={'value':'kWh/m³','variable':'Series'},title='Observed SEC and prior similar-production median'),width='stretch')
    st.caption('A missing reference line means insufficient comparison data. No high matched-output flag does not prove efficient operation.')
    st.divider()
    st.download_button('Download grouped incidents',incidents.to_csv(index=False).encode(),file_name='grouped_incidents.csv',mime='text/csv')
    st.download_button('Download similar-production evidence',comparison.to_csv(index=False).encode(),file_name='production_comparison.csv',mime='text/csv')
    with st.expander('Coverage: what could and could not be assessed'):
        st.dataframe(coverage,hide_index=True,width='stretch')
        st.write('Missing channels are not filled. Zero-only channels are retained but cannot establish operating condition. Absolute vibration severity, membrane pressure-drop/fouling diagnosis and automatic repair are not implemented. Daily averages cannot capture every brief excursion.')
    with st.expander('Assumed tag dictionary and calculation rules'):
        st.dataframe(dictionary(equipment),hide_index=True,width='stretch')
        st.write('Converted values appear in this action centre; the original investigation page keeps recorded values. Plant A electrical scaling is inconsistent, so its power/current are not used to calculate motor efficiency or SEC. Plant SEC uses the performance-file daily totals.')
        st.write('Temperature is checked from the first day. Rising vibration/turbidity uses a prior-only 14-calendar-day IQR baseline with at least 12 readings. SEC uses a prior-only median, requiring 12 valid days. Persistence counts consecutive calendar days and resets on missing/unflagged days. These are investigation rules, not failure predictions.')
        st.json(cfg)
    st.download_button('Download complete engineering event report',events.to_csv(index=False).encode(),file_name=f'{plant.replace(" ","_")}_engineering_events.csv',mime='text/csv')
    st.download_button('Download assumed tag dictionary',dictionary(equipment).to_csv(index=False).encode(),file_name=f'{plant.replace(" ","_")}_tag_dictionary.csv',mime='text/csv')
    st.download_button('Download channel coverage',coverage.to_csv(index=False).encode(),file_name='channel_coverage.csv',mime='text/csv')
    return events
