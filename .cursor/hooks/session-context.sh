#!/bin/bash
# Inject cucut agent context at session start.
echo '{
  "additional_context": "Cucut repo — DJI/MP4 dead-segment scanner + lossless trimmer. Read AGENTS.md first. Git hooks (.githooks/) run checks on commit/push automatically after setup-hooks.sh. Skills: cucut-project, cucut-workflow, cucut-versioning. Token saving: caveman suite."
}'
exit 0
