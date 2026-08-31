{{ config(materialized='view') }}

select
    event_type,
    case event_type
        when 'page_view' then 'Page view'
        when 'add_to_cart' then 'Add to cart'
        when 'purchase' then 'Purchase'
        when 'refund' then 'Refund'
    end as event_type_name
from {{ ref('stg_daily_event_metrics') }}
group by event_type
