#!/bin/bash
# Remind agents to run pre-push checks before git push.
input=$(cat)
command=$(echo "$input" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{console.log(JSON.parse(d).command||'')}catch{}})" 2>/dev/null || echo "")

if [[ "$command" =~ git[[:space:]]+push ]]; then
  if [[ "$command" =~ push[[:space:]]+.*main ]] || [[ "$command" =~ push[[:space:]]+origin[[:space:]]+main ]]; then
    echo '{
      "permission": "ask",
      "user_message": "Pushing to main: service-only changes skip CI/version. App code requires bump-version.sh + pre-push-check.sh.",
      "agent_message": "Service paths in scripts/service-paths.list skip pipeline. App changes to main need: (1) bash scripts/bump-version.sh, (2) update CHANGELOG.md, (3) bash scripts/pre-push-check.sh."
    }'
    exit 0
  fi

  echo '{
    "permission": "ask",
    "user_message": "Run pre-push validation before pushing?",
    "agent_message": "Run bash scripts/pre-push-check.sh before git push. See AGENTS.md."
  }'
  exit 0
fi

echo '{ "permission": "allow" }'
exit 0
