#!/bin/bash

llm_model="${ACE_LLM_MODEL:-deepseek-v4-flash}"
embedding_model="${ACE_EMBEDDING_MODEL:-BAAI/bge-small-en-v1.5}"
python_bin="${ACE_PYTHON:-.venv/bin/python}"
results_jsonl="${ACE_RESULTS_JSONL:-results/replancheck_m1/case_studies/runs.jsonl}"

if [[ ! -x "$python_bin" ]]; then
    python_bin="python"
fi

while true; do
    echo
    read -p "Enter case number (1, 2, 3) or 'q' to quit: " case_num

    if [[ "$case_num" == "q" || "$case_num" == "Q" ]]; then
        echo "Exiting..."
        break
    elif [[ "$case_num" =~ ^[1-3]$ ]]; then
        manifest="benchmarks/case_studies/case_${case_num}/tools/manifest.json"

        echo "Running case $case_num with manifest: $manifest"
        echo "Using LLM model: $llm_model"
        echo "Using embedding model: $embedding_model"
        
        echo "Calculate the fare from Main Street to Elms Ave with QuickRide and MetroHail. DO NOT use f strings and nested function calls including type casting. Remember that tool calls might fail and use try/catch to set reasonable default values." | \
        PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}src" "$python_bin" -m ace \
            --llm-model "$llm_model" \
            --embedding-model "$embedding_model" \
            --tool-manifest "$manifest" \
            --results-jsonl "$results_jsonl"
    else
        echo "Invalid input. Please enter 1, 2, 3, or 'q' to quit."
    fi
done
