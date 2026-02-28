#!/bin/bash

# Configuration
API_URL="http://localhost:8000"
SKILL_TO_SYNC="cron-manager"

# Target Agents
AGENTS=(
  "garage690f1eea755add84faae0d7f"
  "garage690f214ec7b7788d3b6dd79b"
  "garage690f1eea755add84faae0d7ff1e503"
  "garage690f1eea755add84faae0d7fedad35"
  "garage690f1eea755add84faae0d7f0bcdf9"
  "garage690f1eea755add84faae0d7f760577"
  "garage68f1fe06876fcc5fadb61984ea2595"
  "garage68f1fe06876fcc5fadb6198449d96f"
  "garage68f1fe06876fcc5fadb61984d10437"
  "garage695e39d798657913918f4a49f57381"
)

echo "Starting bulk sync of skill '$SKILL_TO_SYNC' for ${#AGENTS[@]} agents..."

for AGENT_ID in "${AGENTS[@]}"; do
    echo -n "Syncing for agent $AGENT_ID... "
    
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/agents/$AGENT_ID/skills/$SKILL_TO_SYNC/sync")
    
    if [ "$RESPONSE" -eq 200 ]; then
        echo "✅ Success"
    else
        echo "❌ Failed (HTTP $RESPONSE)"
    fi
done

echo "Done!"
