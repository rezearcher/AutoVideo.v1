#!/bin/bash

# Exit on error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the latest workflow run
echo -e "${YELLOW}Fetching latest workflow runs...${NC}"
WORKFLOW_RUNS=$(gh api repos/:owner/:repo/actions/runs --jq '.workflow_runs[0:5]')

# Function to get status color
get_status_color() {
    case $1 in
        "completed")
            echo -e "${GREEN}"
            ;;
        "in_progress")
            echo -e "${YELLOW}"
            ;;
        "queued")
            echo -e "${YELLOW}"
            ;;
        *)
            echo -e "${RED}"
            ;;
    esac
}

# Function to get conclusion color
get_conclusion_color() {
    case $1 in
        "success")
            echo -e "${GREEN}"
            ;;
        "failure")
            echo -e "${RED}"
            ;;
        "cancelled")
            echo -e "${YELLOW}"
            ;;
        *)
            echo -e "${NC}"
            ;;
    esac
}

# Print workflow runs
echo -e "\n${YELLOW}Latest Workflow Runs:${NC}"
echo "$WORKFLOW_RUNS" | jq -r '.[] | "\(.name) - Run #\(.run_number)\nStatus: \(.status)\nConclusion: \(.conclusion)\nURL: \(.html_url)\n"' | while read -r line; do
    if [[ $line == *"Status:"* ]]; then
        status=$(echo $line | cut -d':' -f2 | xargs)
        color=$(get_status_color $status)
        echo -e "${color}${line}${NC}"
    elif [[ $line == *"Conclusion:"* ]]; then
        conclusion=$(echo $line | cut -d':' -f2 | xargs)
        color=$(get_conclusion_color $conclusion)
        echo -e "${color}${line}${NC}"
    else
        echo "$line"
    fi
done

# Get detailed logs for the latest run
LATEST_RUN_ID=$(echo "$WORKFLOW_RUNS" | jq -r '.[0].id')
echo -e "\n${YELLOW}Fetching detailed logs for latest run (ID: $LATEST_RUN_ID)...${NC}"

# Get jobs for the latest run
JOBS=$(gh api repos/:owner/:repo/actions/runs/$LATEST_RUN_ID/jobs)

echo -e "\n${YELLOW}Jobs in latest run:${NC}"
echo "$JOBS" | jq -r '.jobs[] | "\(.name)\nStatus: \(.status)\nConclusion: \(.conclusion)\n"' | while read -r line; do
    if [[ $line == *"Status:"* ]]; then
        status=$(echo $line | cut -d':' -f2 | xargs)
        color=$(get_status_color $status)
        echo -e "${color}${line}${NC}"
    elif [[ $line == *"Conclusion:"* ]]; then
        conclusion=$(echo $line | cut -d':' -f2 | xargs)
        color=$(get_conclusion_color $conclusion)
        echo -e "${color}${line}${NC}"
    else
        echo "$line"
    fi
done

# Function to watch a specific job
watch_job() {
    local job_id=$1
    echo -e "\n${YELLOW}Watching job $job_id...${NC}"
    gh run watch $job_id
}

# Ask if user wants to watch the latest run
echo -e "\n${YELLOW}Would you like to watch the latest run? (y/n)${NC}"
read -r watch_response
if [[ $watch_response =~ ^[Yy]$ ]]; then
    watch_job $LATEST_RUN_ID
fi 