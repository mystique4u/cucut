#!/bin/bash
# Inject cucut agent context at session start.
echo '{
  "additional_context": "Cucut repo — DJI/MP4 dead-segment scanner + lossless trimmer. Read AGENTS.md first. Mandatory: feature/fix branches from main, bash scripts/pre-push-check.sh before push, update CHANGELOG.md, bump version before pushing app changes to main. Skills: cucut-project, cucut-workflow, cucut-versioning in .agents/skills/. Token saving: caveman, caveman-compress, cavecrew in .agents/skills/."
}'
exit 0
