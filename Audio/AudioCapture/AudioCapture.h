#import <Cocoa/Cocoa.h>
#import <AudioUnit/AudioUnit.h>
#import <AudioToolbox/AudioToolbox.h>

@class QTCaptureSession;
@class QTCaptureDeviceInput;
@class QTCaptureDecompressedAudioOutput;

@interface AudioCapture : NSObject {
	
@private	
	QTCaptureSession					*captureSession;
	QTCaptureDeviceInput				*captureAudioDeviceInput;
	QTCaptureDecompressedAudioOutput	*captureAudioDataOutput;	
	
	AudioUnit							effectAudioUnit;
	ExtAudioFileRef						extAudioFile;
	
	AudioStreamBasicDescription			currentInputASBD;
	AudioBufferList						*currentInputAudioBufferList;	
	
	double								currentSampleTime;
	BOOL								didSetUpAudioUnits;	
	
	NSString							*outputFile;
	BOOL								recording;
	BOOL								running;
}

- (id)initWithPath:(NSString *)path;

@property(copy)					NSString	*outputFile;
@property(getter=isRecording)	BOOL		recording;
@property(getter=isRunning)		BOOL		running;

@end