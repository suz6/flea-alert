@echo off
cd /d %~dp0
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% ===== >> ig_log.txt
git pull --rebase --autostash >> ig_log.txt 2>&1
python ig_collect.py >> ig_log.txt 2>&1
git add data/ig_events.json data/ig_seen.json >> ig_log.txt 2>&1
git commit -m "ig update" >> ig_log.txt 2>&1
git pull --rebase --autostash >> ig_log.txt 2>&1
git push >> ig_log.txt 2>&1
