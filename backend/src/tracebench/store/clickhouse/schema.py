"""ClickHouse DDL.

`spans` is the source of truth, sorted by (service_name, start_time, trace_id) so the
common dashboard scan (one service, a time window) reads a contiguous range. Three
materialized views maintain pre-aggregated rollups on insert:

* trace_summaries: one row per trace keyed by trace_id, used for the trace list and to
  bound the time range when fetching a single trace's spans from `spans`.
* span_rollup_1m: per-minute latency digests, tokens and cost by service/operation/model.
* tool_rollup_1h: hourly tool call and failure counts for the heatmap.
* trace_index: (hour, trace_id) pairs sorted by hour, so the trace list can narrow
  trace_summaries (sorted by trace_id) to a time window before grouping.
"""


def statements(database: str, ttl_days: int) -> list[str]:
    db = database
    return [
        f"CREATE DATABASE IF NOT EXISTS {db}",
        f"""
        CREATE TABLE IF NOT EXISTS {db}.spans
        (
            trace_id String CODEC(ZSTD(1)),
            span_id String CODEC(ZSTD(1)),
            parent_span_id String CODEC(ZSTD(1)),
            service_name LowCardinality(String),
            name LowCardinality(String),
            kind LowCardinality(String),
            start_time DateTime64(9, 'UTC') CODEC(Delta, ZSTD(1)),
            end_time DateTime64(9, 'UTC') CODEC(Delta, ZSTD(1)),
            duration_ms Float64,
            status_code LowCardinality(String),
            status_message String,
            operation LowCardinality(String),
            provider LowCardinality(String),
            request_model LowCardinality(String),
            response_model LowCardinality(String),
            input_tokens UInt32,
            output_tokens UInt32,
            cache_read_tokens UInt32,
            cache_write_tokens UInt32,
            cost_usd Decimal(18, 9),
            price_version UInt32,
            tool_name LowCardinality(String),
            tool_call_id String,
            tool_arguments String CODEC(ZSTD(3)),
            tool_result String CODEC(ZSTD(3)),
            agent_name LowCardinality(String),
            session_id String,
            input_messages String CODEC(ZSTD(3)),
            output_messages String CODEC(ZSTD(3)),
            system_instructions String CODEC(ZSTD(3)),
            finish_reasons Array(LowCardinality(String)),
            error_type LowCardinality(String),
            attributes Map(LowCardinality(String), String) CODEC(ZSTD(3)),
            resource_attributes Map(LowCardinality(String), String) CODEC(ZSTD(3)),
            events String CODEC(ZSTD(3)),
            INDEX idx_trace_id trace_id TYPE bloom_filter(0.001) GRANULARITY 1,
            INDEX idx_session_id session_id TYPE bloom_filter(0.01) GRANULARITY 4
        )
        ENGINE = MergeTree
        PARTITION BY toDate(start_time)
        ORDER BY (service_name, start_time, trace_id)
        TTL toDateTime(start_time) + INTERVAL {ttl_days} DAY
        SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {db}.trace_summaries
        (
            trace_id String,
            start_time SimpleAggregateFunction(min, DateTime64(9, 'UTC')),
            end_time SimpleAggregateFunction(max, DateTime64(9, 'UTC')),
            root_name SimpleAggregateFunction(max, String),
            root_service SimpleAggregateFunction(max, String),
            session_id SimpleAggregateFunction(max, String),
            span_count SimpleAggregateFunction(sum, UInt64),
            error_count SimpleAggregateFunction(sum, UInt64),
            root_error SimpleAggregateFunction(max, UInt8),
            llm_calls SimpleAggregateFunction(sum, UInt64),
            tool_calls SimpleAggregateFunction(sum, UInt64),
            input_tokens SimpleAggregateFunction(sum, UInt64),
            output_tokens SimpleAggregateFunction(sum, UInt64),
            cost_usd SimpleAggregateFunction(sum, Decimal(38, 9)),
            services SimpleAggregateFunction(groupUniqArrayArray, Array(String)),
            models SimpleAggregateFunction(groupUniqArrayArray, Array(String))
        )
        ENGINE = AggregatingMergeTree
        ORDER BY trace_id
        TTL toDateTime(end_time) + INTERVAL {ttl_days} DAY
        """,
        f"""
        CREATE MATERIALIZED VIEW IF NOT EXISTS {db}.trace_summaries_mv TO {db}.trace_summaries AS
        SELECT
            trace_id,
            min(start_time) AS start_time,
            max(end_time) AS end_time,
            max(if(parent_span_id = '', name, '')) AS root_name,
            max(if(parent_span_id = '', service_name, '')) AS root_service,
            max(session_id) AS session_id,
            toUInt64(count()) AS span_count,
            toUInt64(countIf(status_code = 'error')) AS error_count,
            toUInt8(max(parent_span_id = '' AND status_code = 'error')) AS root_error,
            toUInt64(countIf(operation IN ('chat', 'text_completion', 'generate_content'))) AS llm_calls,
            toUInt64(countIf(tool_name != '')) AS tool_calls,
            toUInt64(sum(input_tokens)) AS input_tokens,
            toUInt64(sum(output_tokens)) AS output_tokens,
            toDecimal128(sum(cost_usd), 9) AS cost_usd,
            groupUniqArray(toString(service_name)) AS services,
            groupUniqArrayIf(
                toString(if(response_model != '', response_model, request_model)),
                request_model != '' OR response_model != ''
            ) AS models
        FROM {db}.spans
        GROUP BY trace_id
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {db}.span_rollup_1m
        (
            bucket DateTime('UTC'),
            service_name LowCardinality(String),
            is_root UInt8,
            operation LowCardinality(String),
            model LowCardinality(String),
            span_count SimpleAggregateFunction(sum, UInt64),
            error_count SimpleAggregateFunction(sum, UInt64),
            input_tokens SimpleAggregateFunction(sum, UInt64),
            output_tokens SimpleAggregateFunction(sum, UInt64),
            cost_usd SimpleAggregateFunction(sum, Decimal(38, 9)),
            duration_digest AggregateFunction(quantilesTDigest(0.5, 0.95, 0.99), Float64)
        )
        ENGINE = AggregatingMergeTree
        PARTITION BY toYYYYMM(bucket)
        ORDER BY (service_name, bucket, is_root, operation, model)
        TTL bucket + INTERVAL {ttl_days * 3} DAY
        """,
        f"""
        CREATE MATERIALIZED VIEW IF NOT EXISTS {db}.span_rollup_1m_mv TO {db}.span_rollup_1m AS
        SELECT
            toStartOfMinute(start_time) AS bucket,
            service_name,
            toUInt8(parent_span_id = '') AS is_root,
            operation,
            if(response_model != '', response_model, request_model) AS model,
            toUInt64(count()) AS span_count,
            toUInt64(countIf(status_code = 'error')) AS error_count,
            toUInt64(sum(input_tokens)) AS input_tokens,
            toUInt64(sum(output_tokens)) AS output_tokens,
            toDecimal128(sum(cost_usd), 9) AS cost_usd,
            quantilesTDigestState(0.5, 0.95, 0.99)(duration_ms) AS duration_digest
        FROM {db}.spans
        GROUP BY bucket, service_name, is_root, operation, model
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {db}.tool_rollup_1h
        (
            bucket DateTime('UTC'),
            tool_name LowCardinality(String),
            service_name LowCardinality(String),
            calls SimpleAggregateFunction(sum, UInt64),
            failures SimpleAggregateFunction(sum, UInt64),
            duration_digest AggregateFunction(quantilesTDigest(0.5, 0.95), Float64)
        )
        ENGINE = AggregatingMergeTree
        PARTITION BY toYYYYMM(bucket)
        ORDER BY (tool_name, bucket, service_name)
        TTL bucket + INTERVAL {ttl_days * 3} DAY
        """,
        f"""
        CREATE MATERIALIZED VIEW IF NOT EXISTS {db}.tool_rollup_1h_mv TO {db}.tool_rollup_1h AS
        SELECT
            toStartOfHour(start_time) AS bucket,
            tool_name,
            service_name,
            toUInt64(count()) AS calls,
            toUInt64(countIf(status_code = 'error')) AS failures,
            quantilesTDigestState(0.5, 0.95)(duration_ms) AS duration_digest
        FROM {db}.spans
        WHERE tool_name != ''
        GROUP BY bucket, tool_name, service_name
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {db}.trace_index
        (
            start_hour DateTime('UTC'),
            trace_id String
        )
        ENGINE = ReplacingMergeTree
        PARTITION BY toYYYYMM(start_hour)
        ORDER BY (start_hour, trace_id)
        TTL start_hour + INTERVAL {ttl_days} DAY
        """,
        f"""
        CREATE MATERIALIZED VIEW IF NOT EXISTS {db}.trace_index_mv TO {db}.trace_index AS
        SELECT toStartOfHour(min(start_time)) AS start_hour, trace_id
        FROM {db}.spans
        GROUP BY trace_id
        """,
    ]


def backfill_statements(database: str) -> list[str]:
    """Indexes traces stored before trace_index existed. A no-op once the index has rows."""
    db = database
    return [
        f"""
        INSERT INTO {db}.trace_index
        SELECT toStartOfHour(min(start_time)) AS start_hour, trace_id
        FROM {db}.spans
        WHERE (SELECT count() FROM {db}.trace_index) = 0
        GROUP BY trace_id
        """
    ]
