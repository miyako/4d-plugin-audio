4d-plugin-audio
===============

4D plugin to record and play audio on OS X 10.6 and later.

###Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|

###Version

<img src="https://cloud.githubusercontent.com/assets/1725068/18940649/21945000-8645-11e6-86ed-4a0f800e5a73.png" width="32" height="32" /> <img src="https://cloud.githubusercontent.com/assets/1725068/18940648/2192ddba-8645-11e6-864d-6d5692d55717.png" width="32" height="32" />

###Recording

```
  //destination must be "aif"
$path:=System folder(Desktop)+"My Recording.aif"

  //the default input device (see system preferences) is used
If (0=AUDIO Is recording )  //only 1 at a time
	$success:=AUDIO Begin recording ($path)
	Repeat 
		DELAY PROCESS(Current process;10)
	Until (Caps lock down)
	
	  //the path is returned
	SHOW ON DISK(AUDIO End recording )
	
End if 
```

###Playing

```
$path:=System folder(Desktop)+"My Recording.aif"

$audio:=AUDIO Open file ($path)

C_TIME($time;$duration)
$time:=AUDIO Get time ($audio)  //current time
$duration:=AUDIO Get duration ($audio)  //total
AUDIO SET TIME ($audio;$time)  //to start from middle

  //the default output device (see system preferences) is used
AUDIO PLAY ($audio)
AUDIO PAUSE ($audio)
AUDIO RESUME ($audio)

While (1=AUDIO Is playing ($audio) & Not(Caps lock down)
	DELAY PROCESS(Current process;10)
End while 

AUDIO STOP ($audio)

AUDIO CLOSE ($audio)
```

###Converting

```
$inPath:=System folder(Desktop)+"My Recording.aif"
  //always aac
$outPath:=System folder(Desktop)+"My Recording.aac"

$sampleRate:=22050
$success:=AUDIO Convert ($inPath;$outPath;$sampleRate)
```

**Note**: The idea is to record in ``AIF`` and then convert to ``AAC`` once the recording is complete.
