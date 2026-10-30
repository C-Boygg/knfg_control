@echo off
echo === Test: mkdir (stage 5) ===
python emulator.py --vfs vfs_full.json --script startup_mkdir.txt
