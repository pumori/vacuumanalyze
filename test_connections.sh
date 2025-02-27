#!/bin/zsh
while IFS=, read -r host db port user pass; do
    if [[ "$host" == "hostname" ]]; then continue; fi  # Skip header
    echo "\nTesting connection to $db on $host..."
    PGPASSWORD=$pass psql -h $host -d $db -U $user -p $port -c "\dt maintenance.*"
done < ../db_inventory.csv
