4d-plugin-audio
===============

4D plugin to record and play audio on OS X 10.6 and later.



###Recording

```
  //destination must be "aif"
$path:=System folder(Desktop)+"My Recording.aif"

  //the default input device (see system preferences) is used
If (0=AUDIO Is recording )  //only 1 at a time
	$success:=AUDIO Begin recording ($path)
	Repeat 
		DELAY PROCESS(Current process;0)
	Until (Caps lock down)
	
	  //the path is returned
	SHOW ON DISK(AUDIO End recording )
	
End if 
```
