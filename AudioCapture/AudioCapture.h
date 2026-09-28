#import <Cocoa/Cocoa.h>
#import <AudioUnit/AudioUnit.h>
#import <AudioToolbox/AudioToolbox.h>

@class AVCaptureSession;
@class AVCaptureDeviceInput;
@class AVCaptureAudioDataOutput;

@interface AudioCapture : NSObject {
	
@private	
	AVCaptureSession					*captureSession;
	AVCaptureDeviceInput				*captureAudioDeviceInput;
	AVCaptureAudioDataOutput			*captureAudioDataOutput;
	dispatch_queue_t					captureAudioDataOutputQueue;
	
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
