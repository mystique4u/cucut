#!/bin/bash
# Inject cucut agent context at session start.
echo '{
  "additional_context": "Cucut repo — DJI/MP4 dead-segment scanner + lossless trimmer. Read AGENTS.md first. ENGLISH ONLY in all repo files (code, docs, comments, CLI) — see cucut-language skill. Git hooks run checks on commit/push after setup-hooks.sh. Skills: cucut-project, cucut-workflow, cucut-versioning, cucut-language. Token saving: caveman suite."
}'
exit 0
