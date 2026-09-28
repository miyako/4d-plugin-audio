//%attributes = {}
$inPath:=System folder:C487(Desktop:K41:16)+"My Recording.aif"
//always aac
$outPath:=System folder:C487(Desktop:K41:16)+"My Recording.aac"

$sampleRate:=22050
$success:=AUDIO Convert($inPath; $outPath; $sampleRate)
