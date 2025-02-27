SELECT 
    table_schema,
    table_name,
    pg_size_pretty(pg_total_relation_size(format('%I.%I', table_schema, table_name))) AS size
FROM maintenance.vacuum_control
WHERE status = 'active';
