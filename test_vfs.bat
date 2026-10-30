@echo off
echo === Test: minimal VFS ===
python emulator.py --vfs vfs_minimal.json --script startup_vfs_test.txt
echo.
echo === Test: medium VFS ===
python emulator.py --vfs vfs_medium.json --script startup_vfs_test.txt
echo.
echo === Test: full VFS (3+ levels) ===
python emulator.py --vfs vfs_full.json --script startup_vfs_test.txt
