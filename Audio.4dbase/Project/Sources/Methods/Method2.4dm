//%attributes = {}
//destination must be "aif"
$path:=System folder:C487(Desktop:K41:16)+"My Recording.aif"

//the default input device (see system preferences) is used
If (0=AUDIO Is recording)  //only 1 at a time
	$success:=AUDIO Begin recording($path)
	Repeat 
		DELAY PROCESS:C323(Current process:C322; 0)
	Until (Caps lock down:C547)
	
	//the path is returned
	SHOW ON DISK:C922(AUDIO End recording)
	
End if 