{{ config(materialized='view') }}

WITH source AS (
    SELECT * FROM {{ source('raw_data', 'raw_scrapes') }}
)

SELECT
    -- 1. Keep the tracking metadata
    job_id,
    site,
    CAST(published_at AS TIMESTAMP) AS published_at,
    
    -- 2. Extract and cast the JSON fields
    -- (Update '$.name', '$.price', etc., to match exactly what your Python scraper outputs)
    JSON_EXTRACT_SCALAR(raw_payload, '$.product_id') AS product_id,
    COALESCE(
        JSON_EXTRACT_SCALAR(raw_payload, '$.product_name'),
        JSON_EXTRACT_SCALAR(raw_payload, '$.title'),
        JSON_EXTRACT_SCALAR(raw_payload, '$.title_raw')
    ) AS product_name,
    COALESCE(
        JSON_EXTRACT_SCALAR(raw_payload, '$.product_url'),
        JSON_EXTRACT_SCALAR(raw_payload, '$.url')
    ) AS product_url,
    
    -- Clean the price (e.g., if it comes as "EGP 450", you might need to use REPLACE to remove "EGP")
    CAST(JSON_EXTRACT_SCALAR(raw_payload, '$.price') AS FLOAT64) AS current_price,
    CAST(JSON_EXTRACT_SCALAR(raw_payload, '$.rating') AS FLOAT64) AS rating
    
FROM source
-- Filter out any corrupted records where the URL is missing
WHERE COALESCE(
    JSON_EXTRACT_SCALAR(raw_payload, '$.product_url'),
    JSON_EXTRACT_SCALAR(raw_payload, '$.url')
) IS NOT NULL
