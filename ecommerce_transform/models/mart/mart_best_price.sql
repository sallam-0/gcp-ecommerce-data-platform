{{ config(
    materialized='incremental',
    unique_key='product_url',
    on_schema_change='sync'
) }}

WITH new_staging_data AS (
    SELECT * FROM {{ ref('stg_raw_scrapes') }}
    
    -- This magic block ensures we only process data that arrived AFTER our last dbt run
    {% if is_incremental() %}
        WHERE published_at > (SELECT MAX(published_at) FROM {{ this }})
    {% endif %}
),

-- Deduplicate: If the scraper accidentally scraped the exact same URL 3 times 
-- in the last 15 minutes, keep only the absolute most recent one.
deduplicated_new_data AS (
    SELECT * EXCEPT(row_num)
    FROM (
        SELECT 
            *,
            ROW_NUMBER() OVER (
                PARTITION BY product_url 
                ORDER BY published_at DESC
            ) as row_num
        FROM new_staging_data
    )
    WHERE row_num = 1
)

SELECT 
    product_id,
    product_url,
    product_name,
    site,
    current_price,
    rating,
    published_at,
    job_id
FROM deduplicated_new_data