{{ config(materialized='view') }}

select
    event_type,
    dt,
    events,
    amount_usd
from {{ ref('stg_daily_event_metrics') }}
