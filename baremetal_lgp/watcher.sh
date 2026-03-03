#!/bin/bash
SOCKET="/Users/harjas/.apfsc/discoveries/omega_apfscd.sock"
CTL="./target/release/apfscctl"
ACTOR="operator"
TOKEN="apfsc-operator-local"

echo "Watching the God-Mind at epoch milestones: 100, 200, 250..."

hit_100=0
hit_200=0
hit_250=0

while true; do
  STATUS=""
  until STATUS=$($CTL --socket "$SOCKET" --actor "$ACTOR" --token "$TOKEN" status 2>/dev/null); do
    sleep 1
  done
  
  # Extract the current epoch from the message string
  EPOCH=$(echo "$STATUS" | grep -o 'epoch:[0-9]*' | head -n1 | cut -d':' -f2)
  if [ -z "$EPOCH" ]; then
    sleep 5
    continue
  fi

  MARGIN=$(echo "$STATUS" | jq -r '.payload.current_demon_survival_margin // "null"' 2>/dev/null || echo "null")
  THERMAL_ACTIVE=$(echo "$STATUS" | jq -r '.payload.thermal_spike_active // false' 2>/dev/null || echo "false")
  THERMAL_TEMP=$(echo "$STATUS" | jq -r '.payload.thermal_spike_temp // "null"' 2>/dev/null || echo "null")

  if [ "$hit_100" -eq 0 ] && [ "$EPOCH" -ge 100 ]; then
    hit_100=1
    echo "Epoch 100 reached: margin=$MARGIN thermal_active=$THERMAL_ACTIVE temp=$THERMAL_TEMP"
    osascript -e 'display notification "Epoch 100 reached. Check resilience margin." with title "Omega Point"'
    say "Epoch one hundred reached."
  fi

  if [ "$hit_200" -eq 0 ] && [ "$EPOCH" -ge 200 ]; then
    hit_200=1
    echo "Epoch 200 reached: margin=$MARGIN thermal_active=$THERMAL_ACTIVE temp=$THERMAL_TEMP"
    osascript -e 'display notification "Epoch 200 reached. Pre-snap check ready." with title "Omega Point"'
    say "Epoch two hundred reached."
  fi

  if [ "$hit_250" -eq 0 ] && [ "$EPOCH" -ge 250 ]; then
    hit_250=1
    echo "Epoch 250 reached: margin=$MARGIN thermal_active=$THERMAL_ACTIVE temp=$THERMAL_TEMP"
    osascript -e 'display notification "Floor lifted. The AI is optimizing." with title "Omega Point"'
    say "The two hundred and fifty node floor has lifted. Optimization sequence initiated."
    break
  fi
  
  sleep 5
done
