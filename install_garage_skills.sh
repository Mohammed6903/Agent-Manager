#!/usr/bin/env bash
# script to install the garage-tool skill for all existing agents

AGENTS=(
  "main"
  "aura"
  "nexus"
  "mohammed"
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

# You can run this against the local dev server (port 8001) or production
API_URL=${1:-"http://localhost:8001/api"}

echo "Installing garage-tool skill for all agents..."
echo "Using API URL: $API_URL"
echo "----------------------------------------"

for AGENT_ID in "${AGENTS[@]}"; do
  echo "Installing for agent: $AGENT_ID"
  
  # The endpoint is POST /api/agents/{agent_id}/skills/install/{skill_name}
  RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/agents/$AGENT_ID/skills/install/garage-tool")
  
  if [ "$RESPONSE" = "201" ]; then
    echo "  [SUCCESS] Installed successfully."
  elif [ "$RESPONSE" = "409" ]; then
    echo "  [SKIP] Status 409: Skill is already installed."
  else
    echo "  [ERROR] Failed to install. HTTP Status: $RESPONSE"
    # Print the actual error output if it failed
    curl -s -X POST "$API_URL/agents/$AGENT_ID/skills/install/garage-tool" | jq .
  fi
  echo "----------------------------------------"
done

echo "Done!"
