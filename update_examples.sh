#!/usr/bin/env bash

for cb_file in examples/*.cb; do
    base="${cb_file%.cb}"

    python3 -m cobalt "${base}.cb" > /dev/null 2>&1
    python3 -m cobalt.explain "${base}.esir.json" > /dev/null 2>&1
done

echo
echo "Generated files:"
echo

for cb_file in examples/*.cb; do
    base="${cb_file%.cb}"

    if [ -f "${base}.esir.json" ]; then
        json="yes"
    else
        json="no"
    fi

    if [ -f "${base}.esir.html" ]; then
        html="yes"
    else
        html="no"
    fi

    printf "%-45s JSON: %-3s HTML: %-3s\n" "$cb_file" "$json" "$html"
done

