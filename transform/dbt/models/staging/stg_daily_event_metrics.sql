{{ config(materialized='view') }}

select
    metric as event_type,
    dt,
    events,
    amount_usd
from {{ source('lakehouse', 'daily_event_metrics') }}
