@echo off
echo === Test: all commands (stage 4) ===
python emulator.py --vfs vfs_full.json --script startup_commands.txt
