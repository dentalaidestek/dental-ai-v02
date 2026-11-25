#!/bin/bash
# Uzun gradle derlemesi sırasında disk temizlikçisi: boş alan <150MB olunca
# yenilenebilir önbellekleri sırayla siler. ZCode'un kendi günlüklerini
# (/tmp/zcode-bash-*) ve derlemeye ait gerçek çıktıları ASLA silmez.
LOG=/tmp/janitor.log
echo "janitor start $(date)" >>"$LOG"
for i in $(seq 1 100); do
  sleep 45
  free_kb=$(df -P -k / | awk 'NR==2{print $4}')
  echo "$(date +%H:%M:%S) free=$((free_kb/1024))MB" >>"$LOG"
  if [ "$free_kb" -lt 150000 ]; then
    rm -rf /home/z/.gradle/caches/8.14.3/kotlin-dsl >>"$LOG" 2>&1
    rm -rf /home/z/.gradle/caches/journal-1 /home/z/.gradle/caches/jars-9 >>"$LOG" 2>&1
    rm -rf /home/z/.gradle/daemon >>"$LOG" 2>&1
    find /tmp -maxdepth 1 -type f ! -name 'janitor*' -mmin +10 -delete >>"$LOG" 2>&1
    rm -f /home/z/my-project/android-sdk/sdkmanager.log >>"$LOG" 2>&1
    echo "$(date +%H:%M:%S) CLEANED at free=$((free_kb/1024))MB" >>"$LOG"
  fi
done
