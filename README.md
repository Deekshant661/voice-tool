# Voice Tool

Hold **Right Ctrl**, speak, release. Your words appear wherever the cursor is: a terminal, a
chat box, notes, a browser. Speech recognition runs on this laptop's GPU with Whisper
(`large-v3-turbo`). It's free, and the audio never leaves the machine.

Every dictation is also saved as training data, so Whisper can later be fine-tuned on your
voice. This is the first piece of Jarvis.

## Keys

| Keys | What happens |
|---|---|
| Hold **Right Ctrl**, speak, release | Dictate, and the text is pasted at the cursor |
| Right Ctrl + any other key | Normal shortcut. No dictation happens. |
| **Right Ctrl + Right Shift** | Open recent dictations, to fix misheard words |
| **Right Ctrl + Delete** | Delete the last recording (for anything sensitive) |

The tray icon is grey when idle, red while recording and amber while transcribing. Right-click
it to see the model status and recordings size, turn saving on or off, keep the model loaded,
unload it now, open the data folder, or quit.

The first dictation after startup, or after the model unloaded, takes a few seconds while the
model loads onto the GPU. Loading starts the moment you press the key. The model unloads after
30 minutes of no use.

If you switch windows before the text arrives, or the target is an admin window, the text is
left on the clipboard instead and a notification says so. Paste it with Ctrl+V.

## Setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1
```

`setup.ps1` creates the Python environment in `%USERPROFILE%\.voice-tool\venv` and downloads
nothing else. The model downloads on first use (1.6 GB). The second command starts the tool at
every login. Undo it with `scripts\uninstall-autostart.ps1`.

To run it now without logging out:

```powershell
& "$env:USERPROFILE\.voice-tool\venv\Scripts\pythonw.exe" -m voicetool
```

## Settings

Edit `config.toml`, then restart the tool (Quit from the tray, then start it again):
- the `vocabulary` list, for words Whisper should spell your way;
- `[cleanup.replacements]`, for fixes Whisper keeps needing;
- the keys, the model, the idle-unload minutes and the recordings-size warning.

## Where things live

Everything heavy lives outside OneDrive, in `%USERPROFILE%\.voice-tool\`:
- `venv\` holds Python and the libraries (~2.2 GB);
- `models\` holds Whisper (~1.6 GB);
- `data\audio\*.flac` plus `data\dictations.db` are the training data, about 1 GB per 5 hours
  of speech. Nothing is ever deleted automatically. The tray warns you past 5 GB.
- `voicetool.log` records errors. Check it if the tool stops responding.

## Tests

```powershell
$py = "$env:USERPROFILE\.voice-tool\venv\Scripts\python.exe"
& $py -m pytest            # fast unit tests, no hardware needed
& $py -m pytest -m gpu     # real Whisper on the GPU
& $py -m pytest -m mic     # real microphone
& $py -m pytest -m win     # real clipboard, paste, keyboard hook, autostart, app launch
```

The `gpu` and `win` end-to-end test pastes a spoken sentence into a real window. Windows' own
voice stands in for the microphone.

## macOS

Same tool, Mac keys. Settings are in `config.mac.toml` (Windows keeps `config.toml`).

| Keys | What happens |
|---|---|
| Hold **Right Option**, speak, release | Dictate, and the text is pasted at the cursor |
| Right Option + any other key | Normal shortcut. No dictation happens. |
| **Right Option + Right Shift** | Open recent dictations |
| **Right Option + Delete** | Delete the last recording |

The menu bar shows `VT` when idle, `VT ●` while recording and `VT …` while transcribing. Click
it for the same menu as the Windows tray. Speech runs on the Mac's GPU with
`whisper-large-v3-turbo-q4` (464 MB), chosen because this Mac has 8 GB of RAM.

### Setup

```bash
brew install python@3.12 python-tk@3.12
/opt/homebrew/bin/python3.12 -m venv ~/.voice-tool/venv
~/.voice-tool/venv/bin/pip install -r requirements-mac.txt
HF_HUB_DISABLE_XET=1 ~/.voice-tool/venv/bin/hf download mlx-community/whisper-large-v3-turbo-q4 \
  --local-dir ~/.voice-tool/models/whisper-large-v3-turbo-q4
```

`HF_HUB_DISABLE_XET=1` matters: the newer download protocol stalled at 0 bytes on this network.

### Permissions

macOS gives permissions to the app that **starts** the tool, here the terminal (Ghostty). In
System Settings → Privacy & Security, turn the terminal on under:
- **Microphone**, to record;
- **Input Monitoring**, to see the Right Option key;
- **Accessibility**, to paste with Cmd+V and to swallow the Option shortcuts.

Quit and reopen the terminal after changing them. Without Accessibility the tool still starts,
says so in a notification and in the log, and leaves text on the clipboard.

### Run

```bash
cd ~/voice-tool/voice-tool && ~/.voice-tool/venv/bin/python -m voicetool
```

Quit from the menu bar. Recordings stay in `~/.voice-tool/data` on this Mac; nothing syncs.
The log is `~/.voice-tool/voicetool.log`.

### Tests

```bash
~/.voice-tool/venv/bin/python -m pytest          # fast unit tests
~/.voice-tool/venv/bin/python -m pytest -m mac   # real pasteboard and real Whisper model
```
