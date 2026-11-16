#!/bin/sh
# Generate Part 4, then resume Part 2, then Part 3. Each exports an MP3 to Downloads.
cd "$HOME/projects/f5-tts/projects"
run() {  # dir, wav name, mp3 name
  ( cd "$1" && HF_HUB_OFFLINE=1 caffeinate -i "$HOME/projects/f5-tts/.venv/bin/python" generate.py >> generate.log 2>&1 < /dev/null )
  if [ -f "$1/$2" ]; then
    ffmpeg -hide_banner -loglevel error -y -i "$1/$2" -c:a libmp3lame -q:a 2 "$HOME/Downloads/$3" && echo "MP3_DONE $1 $(date)" >> queue.log
  else
    echo "FAILED $1 $(date)" >> queue.log
  fi
}
echo "QUEUE_START $(date)" >> queue.log
run shadowheart4 shadowheart_civpro_part4_full.wav "Shadowheart Tutor - Civil Procedure I Part 4 Cheat Sheet (full).mp3"
run shadowheart2 shadowheart_civpro_part2_full.wav "Shadowheart Tutor - Civil Procedure I Part 2 (full).mp3"
run shadowheart3 shadowheart_civpro_part3_full.wav "Shadowheart Tutor - Civil Procedure I Part 3 (full).mp3"
echo "QUEUE_DONE $(date)" >> queue.log
