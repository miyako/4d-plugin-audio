$RecordPath:=OBJECT Get pointer:C1124(Object named:K67:5; "RecordPath")
$RecordPath->:=System folder:C487(Desktop:K41:16)+"Audio Recording.aif"

$PlayRef:=OBJECT Get pointer:C1124(Object named:K67:5; "PlayRef")
$PlayRef->:=AUDIO Open file($RecordPath->)

$Duration:=OBJECT Get pointer:C1124(Object named:K67:5; "Duration")
$Duration->:=AUDIO Get duration($PlayRef->)

//dial: min;max;unit;step{;flags}
//thermo: min;max;unit;step;flags{;format{;display}}
OBJECT SET FORMAT:C236(*; "Time"; "0;"+String:C10($Duration->+0)+";1;1;32")

AUDIO PLAY($PlayRef->)
SET TIMER:C645(1)