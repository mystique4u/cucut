#!/bin/bash
# Optional Cursor hint on push to main (git pre-push hook does real validation).
input=$(cat)
command=$(echo "$input" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{console.log(JSON.parse(d).command||'')}catch{}})" 2>/dev/null || echo "")

if [[ "$command" =~ git[[:space:]]+push ]] && [[ "$command" =~ push[[:space:]]+.*main|origin[[:space:]]+main ]]; then
  echo '{
    "permission": "allow",
    "agent_message": "Push to main: pre-push hook runs automatically (tests, ruff, version gate). App code needs bump-version.sh + CHANGELOG before push."
  }'
  exit 0
fi

echo '{ "permission": "allow" }'
exit 0
