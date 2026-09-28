//%attributes = {}
$path:=System folder:C487(Desktop:K41:16)+"My Recording.aif"

$audio:=AUDIO Open file($path)

C_TIME:C306($time; $duration)
$time:=AUDIO Get time($audio)  //current time
$duration:=AUDIO Get duration($audio)  //total
AUDIO SET TIME($audio; $time)  //to start from middle

AUDIO PLAY($audio)
AUDIO PAUSE($audio)
AUDIO RESUME($audio)

While (1=AUDIO Is playing($audio) & Not:C34(Caps lock down:C547)
	DELAY PROCESS:C323(Current process:C322; 0)
End while 

AUDIO STOP($audio)

AUDIO CLOSE($audio)