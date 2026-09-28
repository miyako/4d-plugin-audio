# 4d-plugin-audio

A 4D plugin for recording, playing back, converting, and enumerating audio
devices on macOS (10.6+, Carbon/Cocoa) and Windows (32/64-bit).

This document is written for **4D developers** calling the plugin's commands
from 4D code — it does not cover the plugin's internal C++/Objective-C
implementation.

---

## Contents

1. [Overview](#overview)
2. [Command index](#command-index)
3. [Recording commands](#recording-commands)
   - `AUDIO Begin recording`
   - `AUDIO End recording`
   - `AUDIO Is recording`
4. [Playback commands](#playback-commands)
   - `AUDIO Open file`
   - `AUDIO CLOSE`
   - `AUDIO PLAY`
   - `AUDIO PAUSE`
   - `AUDIO RESUME`
   - `AUDIO STOP`
   - `AUDIO Is playing`
   - `AUDIO Get duration`
   - `AUDIO Get time`
   - `AUDIO SET TIME`
5. [Conversion command](#conversion-command)
   - `AUDIO Convert`
6. [Device commands](#device-commands)
   - `AUDIO DEVICE LIST`
7. [Complete workflows](#complete-workflows)
8. [Error handling notes](#error-handling-notes)

---

## Overview

The plugin works with **one active recording** and **any number of open
playback files** at a time:

- Recording is a single global session — only one `AUDIO Begin recording` can
  be active at once. Starting a new recording while one is in progress
  replaces it.
- Playback files are referenced by an integer handle returned from
  `AUDIO Open file`. You can have several files open simultaneously (each
  with its own handle), play/pause/stop them independently, and must
  `AUDIO CLOSE` each one when you're done with it.
- `AUDIO Convert` is a one-shot, synchronous, blocking call — it does not
  return a handle and does not run in the background.

**Recording format:** always AIFF (`.aif`). Record to `.aif`, then use
`AUDIO Convert` to produce a compressed file (AAC by default, or MP3).

---

## Command index

| Command | Purpose |
|---|---|
| `AUDIO DEVICE LIST` | List available input or output audio devices |
| `AUDIO Begin recording` | Start recording from the default input device |
| `AUDIO End recording` | Stop the current recording, return its file path |
| `AUDIO Is recording` | Check whether a recording is in progress |
| `AUDIO Open file` | Open an audio file for playback, get a handle |
| `AUDIO CLOSE` | Close a playback handle and release its resources |
| `AUDIO PLAY` | Start/resume playback from the beginning of the buffer |
| `AUDIO PAUSE` | Pause playback |
| `AUDIO RESUME` | Resume playback after a pause |
| `AUDIO STOP` | Stop playback |
| `AUDIO Is playing` | Check whether a handle is currently playing |
| `AUDIO Get duration` | Get the total duration of a playback file |
| `AUDIO Get time` | Get the current playback position |
| `AUDIO SET TIME` | Set the current playback position |
| `AUDIO Convert` | Convert an audio file to AAC or MP3 |

---

## Recording commands

### `AUDIO Begin recording`

Starts recording audio from the system's **default input device** (the one
selected in System Preferences / Settings → Sound → Input) into the given
file path.

```4d
success:=AUDIO Begin recording (path)
```

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `path` | Text | In | Destination file path. Must end in an AIFF-compatible extension (use `.aif`). |
| `success` | Integer | Out | `1` if recording started successfully, `0` otherwise. |

**Notes**

- Only one recording session exists at a time. Calling this again while a
  recording is already in progress **stops the current recording and starts
  a new one** — the file from the interrupted recording will contain
  whatever was captured up to that point, but you won't get its path back
  (use `AUDIO End recording` first if you need it).
- Use `AUDIO Is recording` to guard against starting a second recording by
  mistake.
- If `path` is empty or otherwise invalid, the command fails without
  starting anything and any prior recording in progress is left untouched.
- This command returns as soon as recording starts; it does not block until
  recording stops.

**Example**

```4d
$path:=System folder(Desktop)+"My Recording.aif"

If (0=AUDIO Is recording)  //only 1 at a time
	$success:=AUDIO Begin recording ($path)
End if 
```

---

### `AUDIO End recording`

Stops the current recording (if any) and returns the path of the file that
was written.

```4d
path:=AUDIO End recording 
```

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `path` | Text | Out | Path of the file that was recorded. Empty if no recording was in progress. |

**Notes**

- Safe to call even if nothing is recording — it simply returns an empty
  string.
- After this call, `AUDIO Is recording` returns `0`.

**Example**

```4d
SHOW ON DISK(AUDIO End recording)
```

---

### `AUDIO Is recording`

```4d
recording:=AUDIO Is recording 
```

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `recording` | Integer | Out | `1` if a recording is currently in progress, `0` otherwise. |

**Example**

```4d
If (0=AUDIO Is recording)
	// ok to start a new recording
End if 
```

---

## Playback commands

Playback commands operate on a **handle** (a `Longint` reference) obtained
from `AUDIO Open file`. Always match every `AUDIO Open file` with an
`AUDIO CLOSE` once you're done with the file, to release the underlying
`NSSound`/platform resource.

### `AUDIO Open file`

Opens an audio file for playback and returns a handle to it.

```4d
audio:=AUDIO Open file (path)
```

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `path` | Text | In | Path of the audio file to open. |
| `audio` | Longint | Out | A handle to use with all other playback commands. `0` if the file could not be opened. |

**Notes**

- Always check that `audio` is non-zero before using it — a `0` handle means
  the file failed to load (wrong path, unsupported/corrupt file, etc.).
- The handle is only valid for the lifetime of the plugin/session — don't
  persist it to disk or reuse it after `AUDIO CLOSE`.

**Example**

```4d
$path:=System folder(Desktop)+"My Recording.aif"
$audio:=AUDIO Open file ($path)
If ($audio#0)
	// proceed
End if 
```

---

### `AUDIO CLOSE`

Closes a playback handle, stopping playback if necessary and releasing its
resources.

```4d
AUDIO CLOSE (audio)
```

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `audio` | Longint | In | The handle returned by `AUDIO Open file`. |

**Notes**

- Always call this once you're done with a handle. Leaving handles open
  indefinitely accumulates memory for the lifetime of the 4D session.
- Calling it twice on the same handle, or on a handle that was never valid,
  is harmless (it's simply a no-op the second time).

---

### `AUDIO PLAY`

```4d
AUDIO PLAY (audio)
```

Starts (or restarts) playback of the given handle from the beginning.

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `audio` | Longint | In | The handle to play. |

---

### `AUDIO PAUSE`

```4d
AUDIO PAUSE (audio)
```

Pauses playback, keeping the current position. Use `AUDIO RESUME` to
continue from where it left off.

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `audio` | Longint | In | The handle to pause. |

---

### `AUDIO RESUME`

```4d
AUDIO RESUME (audio)
```

Resumes playback after a pause, from the paused position.

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `audio` | Longint | In | The handle to resume. |

---

### `AUDIO STOP`

```4d
AUDIO STOP (audio)
```

Stops playback entirely (unlike pause, playback position is not guaranteed
to be preserved — use `AUDIO SET TIME` afterward if you need to resume from
a specific point).

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `audio` | Longint | In | The handle to stop. |

---

### `AUDIO Is playing`

```4d
playing:=AUDIO Is playing (audio)
```

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `audio` | Longint | In | The handle to check. |
| `playing` | Integer | Out | `1` if currently playing, `0` otherwise. |

**Example**

```4d
While (1=AUDIO Is playing ($audio) & Not(Caps lock down))
	DELAY PROCESS(Current process; 10)
End while 
```

---

### `AUDIO Get duration`

```4d
duration:=AUDIO Get duration (audio)
```

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `audio` | Longint | In | The handle to query. |
| `duration` | Time | Out | Total length of the audio file. |

---

### `AUDIO Get time`

```4d
time:=AUDIO Get time (audio)
```

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `audio` | Longint | In | The handle to query. |
| `time` | Time | Out | Current playback position. |

---

### `AUDIO SET TIME`

```4d
AUDIO SET TIME (audio; time)
```

Seeks to a given position. Works whether the file is currently playing,
paused, or stopped.

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `audio` | Longint | In | The handle to seek. |
| `time` | Time | In | The position to seek to. |

---

## Conversion command

### `AUDIO Convert`

Converts an audio file to a compressed format (AAC by default). This call
is **synchronous** — it blocks the calling process until the conversion
finishes (or fails), so avoid calling it from the main/interactive process
if the source file is large.

```4d
success:=AUDIO Convert (in; out; sampleRate)
```

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `in` | Text | In | Path of the source audio file. |
| `out` | Text | In | Path of the destination file. |
| `sampleRate` | Real | In | Output sample rate in Hz (e.g. `22050`, `44100`). Pass `0` to keep the source's sample rate. |
| `success` | Integer | Out | `1` on success, `0` on failure. |

**Notes and current limitations**

- The output is always AAC (`.aac`) at present — the output extension you
  choose is cosmetic; the encoder used is fixed.
- **Best practice: only convert AIFF (`.aif`) source files produced by**
  **`AUDIO Begin recording`/`AUDIO End recording`.** This is the only
  configuration that's been exercised in the plugin's own examples. Source
  files that are *not* linear PCM (i.e. already-compressed formats such as
  AAC or MP3) are a known problem case in the current implementation and
  should not be passed as `in` until that's addressed on the C++ side —
  see the engineering note below.
- If `sampleRate` is `0`, the source's own sample rate is kept.
- Because the call blocks, wrap it with your own progress UI or run it in a
  background 4D process if the source file is more than a few seconds long.

**Example**

```4d
$inPath:=System folder(Desktop)+"My Recording.aif"
$outPath:=System folder(Desktop)+"My Recording.aac"

$sampleRate:=22050
$success:=AUDIO Convert ($inPath; $outPath; $sampleRate)
```

> **Engineering note (not a 4D-language concern, but worth knowing as a
> caller):** the current native implementation of `AUDIO Convert` computes
> a buffer size using the client audio format's bytes-per-frame, which is
> only valid for linear PCM (uncompressed) sources. Passing an already
> -compressed file as `in` is not a supported input today. Stick to AIFF
> sources (as produced by this plugin's own recording commands) until this
> is revisited.

---

## Device commands

### `AUDIO DEVICE LIST`

Enumerates the audio input or output devices currently available on the
system (as seen in System Preferences / Settings → Sound).

```4d
AUDIO DEVICE LIST (names; ids; kind)
```

| Parameter | Type | In/Out | Description |
|---|---|---|---|
| `names` | Array Text | Out | Device names. |
| `ids` | Array Longint | Out | Corresponding device IDs (native `AudioDeviceID` on macOS). |
| `kind` | Longint | In | `0` = input devices, `1` = output devices. |

**Notes**

- The two arrays are parallel: `names{i}` and `ids{i}` describe the same
  device.
- Only devices with at least one channel for the requested direction are
  listed (e.g. a webcam mic shows up under input, a set of headphones
  under output).
- This command only **lists** devices — there is currently no command to
  select which input/output device recording or playback should use; the
  system default is always used. To change the actual device 4D records
  from or plays to, the user must change it in System Preferences /
  Settings.

**Example**

```4d
ARRAY TEXT($inNames; 0)
ARRAY LONGINT($inIds; 0)
ARRAY TEXT($outNames; 0)
ARRAY LONGINT($outIds; 0)

AUDIO DEVICE LIST($inNames; $inIds; 0)   //inputs
AUDIO DEVICE LIST($outNames; $outIds; 1) //outputs
```

---

## Complete workflows

### Record, then convert to AAC

```4d
$path:=System folder(Desktop)+"My Recording.aif"

If (0=AUDIO Is recording)  //only 1 recording at a time
	$success:=AUDIO Begin recording ($path)
	
	Repeat 
		DELAY PROCESS(Current process; 10)
	Until (Caps lock down)  //replace with your own stop condition
	
	$recordedPath:=AUDIO End recording 
	SHOW ON DISK($recordedPath)
	
	$outPath:=System folder(Desktop)+"My Recording.aac"
	$success:=AUDIO Convert ($recordedPath; $outPath; 22050)
End if 
```

### Open, seek, and play a file

```4d
$path:=System folder(Desktop)+"My Recording.aif"

$audio:=AUDIO Open file ($path)

If ($audio#0)
	
	C_TIME($time; $duration)
	$time:=AUDIO Get time ($audio)         //current position
	$duration:=AUDIO Get duration ($audio) //total length
	
	AUDIO SET TIME ($audio; $duration/2)   //start from the middle
	AUDIO PLAY ($audio)
	
	While (1=AUDIO Is playing ($audio) & Not(Caps lock down))
		DELAY PROCESS(Current process; 10)
	End while 
	
	AUDIO STOP ($audio)
	AUDIO CLOSE ($audio)  //always close what you open
	
End if 
```

### Pause / resume a playing file

```4d
AUDIO PLAY ($audio)
DELAY PROCESS(Current process; 300)  // 5 seconds @ 60 ticks/sec

AUDIO PAUSE ($audio)
DELAY PROCESS(Current process; 300)

AUDIO RESUME ($audio)
```

### Enumerate devices for a settings screen

```4d
ARRAY TEXT($names; 0)
ARRAY LONGINT($ids; 0)

AUDIO DEVICE LIST($names; $ids; 0)  //input devices

For ($i; 1; Size of array($names))
	ALERT($names{$i}+" (id "+String($ids{$i})+")")
End for 
```

---

## Error handling notes

Because this is a native plugin, most failures surface as a **zero/empty
return value** rather than a 4D error dialog:

| Command | Failure looks like |
|---|---|
| `AUDIO Begin recording` | `success` = `0` |
| `AUDIO End recording` | Empty path returned |
| `AUDIO Open file` | `audio` = `0` |
| `AUDIO Convert` | `success` = `0` |
| `AUDIO PLAY` / `PAUSE` / `RESUME` / `STOP` / `SET TIME` | Silently do nothing if the handle is invalid or `0` |
| `AUDIO Get duration` / `Get time` | Returns a zero `Time` if the handle is invalid |

**Recommended pattern:** always check the return value of
`AUDIO Begin recording`, `AUDIO Open file`, and `AUDIO Convert` before
proceeding, and guard playback commands with `If ($audio#0)`.

```4d
$audio:=AUDIO Open file ($path)
If ($audio=0)
	ALERT("Could not open audio file: "+$path)
Else
	AUDIO PLAY ($audio)
	// ...
	AUDIO CLOSE ($audio)
End if 
```

---

*Platform support: Carbon and Cocoa on macOS 10.6+; 32-bit and 64-bit
Windows are listed as platform targets but are not yet implemented.*
