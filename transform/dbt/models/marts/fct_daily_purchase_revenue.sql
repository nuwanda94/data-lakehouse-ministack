{{ config(materialized='view') }}

select
    dt,
    events,
    amount_usd as gmv_usd
from {{ ref('stg_daily_event_metrics') }}
where event_type = 'purchase'
