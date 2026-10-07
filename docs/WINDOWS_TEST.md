# Testing on Windows

The automated tests in CI cover the logic. The window itself needs a real screen, so please run this on each Windows machine (Windows 10 and 11, and ideally one laptop at 125% or 150% scaling and one external monitor).

## 1. Automatic checks
```powershell
python limitline.py --selftest
```
Look for `RESULT: ALL CHECKS PASSED`. Send `%USERPROFILE%\limitline-selftest.txt` with any bug report. During the run a toast notification should appear, and a startup entry is written and removed again.

## 2. Look at it (2 minutes)
```powershell
python limitline.py --demo
```
Tick each line:
- [ ] Icons (top right) are smooth, not jagged; hovering shows a rounded highlight
- [ ] Cards have rounded corners; no stray square corners or dark rectangles
- [ ] No text cut off in any of the four tabs (press `1` to `4`)
- [ ] Window is not larger than the screen at your scaling; it scrolls instead
- [ ] Drag by the title bar; double-click the title to get the small pill; drag the pill; get back
- [ ] Windows 11: rounded window corners and a dark title bar; Windows 10: still looks fine
- [ ] Move the window to a second monitor with different scaling; text stays sharp
- [ ] `S` opens settings; with a short screen the Save and Cancel buttons stay visible
- [ ] Dark and light themes both readable; accent colours switch
- [ ] Always-on-top toggle (`T`) works; the window appears in the taskbar when borderless

## 3. Real data
```powershell
python limitline.py --install-statusline
```
Send a message in Claude Code, then check the limits card shows your 5-hour and weekly percentages and that Claude Code's own status line still shows what it did before. Undo with `--uninstall-statusline`.

- [ ] Alerts: set "Alert at" to a low number such as 1 and confirm the banner and notification
- [ ] Launch at login: switch on, sign out and in, confirm it starts; switch off, confirm it does not
- [ ] `pythonw limitline.py` starts with no console window

## 4. Report
Open an issue with the self-test report, your Windows version, scaling (Settings > Display) and screenshots of anything odd.
