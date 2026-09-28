$event:=Form event code:C388

Case of 
	: ($event=On Load:K2:1)
		OBJECT SET ENABLED:C1123(*; "Is Recording"; False:C215)
		OBJECT SET ENABLED:C1123(*; "Is Playing"; False:C215)
	: ($event=On Unload:K2:2)
		SET TIMER:C645(0)
	: ($event=On Timer:K2:25)
		
		$PlayRef:=OBJECT Get pointer:C1124(Object named:K67:5; "PlayRef")
		
		$IsRecording:=OBJECT Get pointer:C1124(Object named:K67:5; "Is Recording")
		$IsRecording->:=AUDIO Is recording
		
		$IsPlaying:=OBJECT Get pointer:C1124(Object named:K67:5; "Is Playing")
		$IsPlaying->:=AUDIO Is playing($PlayRef->)
		
		$Time:=OBJECT Get pointer:C1124(Object named:K67:5; "Time")
		$Time->:=AUDIO Get time($PlayRef->)
		
		OBJECT SET VISIBLE:C603(*; "Time"; 1=$IsPlaying->)
		
		If (0=$IsPlaying->)
			SET TIMER:C645(0)
		End if 
		
	: ($event=On Clicked:K2:4)
		OBJECT SET ENABLED:C1123(*; "End"; 1=AUDIO Is recording)
		OBJECT SET ENABLED:C1123(*; "Begin"; 0=AUDIO Is recording)
End case 