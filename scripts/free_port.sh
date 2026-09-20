#!/usr/bin/env bash
#
# Print the first free TCP port at or above the one given.
# Shared machines have the usual ports taken (on the hackathon
# GPU box 8080 is the instance's own shell gateway).

port="${1:-8080}"

while (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; do
  port=$((port + 1))
done

echo "$port"
