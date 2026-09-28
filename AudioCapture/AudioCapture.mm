#import "AudioCapture.h"

#import <AVFoundation/AVFoundation.h>
#import <CoreMedia/CoreMedia.h>

/*
 Migrated from QTKit to AVFoundation.
 
 QTKit (QTCaptureSession / QTCaptureDeviceInput / QTCaptureDecompressedAudioOutput)
 was deprecated by Apple in OS X 10.9 and its headers/framework have since been
 removed from the SDK entirely - "'QTKit/QTKit.h' file not found" on any current
 Xcode/SDK is expected, not a configuration problem. This file now uses the
 AVFoundation equivalents:
 
   QTCaptureDevice                   -> AVCaptureDevice
   QTCaptureSession                  -> AVCaptureSession
   QTCaptureDeviceInput               -> AVCaptureDeviceInput
   QTCaptureDecompressedAudioOutput   -> AVCaptureAudioDataOutput
   QTSampleBuffer / QTFormatDescription -> CMSampleBufferRef / CMFormatDescriptionRef
 
 IMPORTANT - project/plist changes this migration ALSO requires, which live
 outside the files in this repo and must be done in the Xcode project / the
 host app's Info.plist:
 
  1. Link AVFoundation.framework and CoreMedia.framework; remove QTKit.framework
     from "Link Binary With Libraries" if it's still listed.
  2. macOS requires an NSMicrophoneUsageDescription entry in Info.plist for any
     process that requests microphone access (this is enforced by TCC and is
     unrelated to compiling - QTKit predates this entirely, so it's new).
     Without it, AVCaptureDeviceInput creation / session start will fail (and
     on some OS versions the requesting process can be terminated outright)
     rather than silently no-op. Since this is a 4D plugin, the usage
     description has to be present in *the host application's* Info.plist
     (i.e. 4D.app's, or your built runtime's), not just the plugin bundle.
     The user will be shown the standard system mic-access prompt the first
     time AUDIO_Begin_recording actually starts the capture session.
*/

static OSStatus PushCurrentInputBufferIntoAudioUnit(void *							inRefCon,
													AudioUnitRenderActionFlags *	ioActionFlags,
													const AudioTimeStamp *			inTimeStamp,
													UInt32							inBusNumber,
													UInt32							inNumberFrames,
													AudioBufferList *				ioData);

@interface AudioCapture () <AVCaptureAudioDataOutputSampleBufferDelegate>
@end

@implementation AudioCapture

@synthesize outputFile;
@synthesize recording;
@synthesize running;

- (id)initWithPath:(NSString *)path
{
	if(!(self = [super init]))return self;
	
	self.outputFile = path;
	
	AVCaptureDevice *audioDevice = [AVCaptureDevice defaultDeviceWithMediaType:AVMediaTypeAudio];
	
	if(audioDevice){
		
		NSError *error = nil;
		
		/* Unlike QTCaptureDevice, AVCaptureDevice has no separate open/close step -
		   AVCaptureDeviceInput acquires/releases the device as it's added to /
		   removed from a running session. */
		captureAudioDeviceInput = [[AVCaptureDeviceInput alloc] initWithDevice:audioDevice error:&error];
		
		if(captureAudioDeviceInput){
			
			captureSession = [[AVCaptureSession alloc]init];
			
			if([captureSession canAddInput:captureAudioDeviceInput]){
				
				[captureSession addInput:captureAudioDeviceInput];
				
				captureAudioDataOutput = [[AVCaptureAudioDataOutput alloc]init];
				captureAudioDataOutputQueue = dispatch_queue_create("com.miyako.4dplugin.audio.capture", DISPATCH_QUEUE_SERIAL);
				[captureAudioDataOutput setSampleBufferDelegate:self queue:captureAudioDataOutputQueue];
				
				if([captureSession canAddOutput:captureAudioDataOutput]){
					
					[captureSession addOutput:captureAudioDataOutput];
					
					/* Create an effect audio unit to add an effect to the audio before it is written to a file. */
					AudioComponentDescription effectAudioUnitComponentDescription;
					effectAudioUnitComponentDescription.componentType = kAudioUnitType_Effect;
					effectAudioUnitComponentDescription.componentSubType = kAudioUnitSubType_GraphicEQ;
					effectAudioUnitComponentDescription.componentManufacturer = kAudioUnitManufacturer_Apple;
					effectAudioUnitComponentDescription.componentFlags = 0;
					effectAudioUnitComponentDescription.componentFlagsMask = 0;
					
					AudioComponent effectAudioUnitComponent = AudioComponentFindNext(NULL, &effectAudioUnitComponentDescription);
					
					OSStatus err = noErr;
					
					err = AudioComponentInstanceNew(effectAudioUnitComponent, &effectAudioUnit);
					
					if (noErr == err) {
						/* Set a callback on the effect unit that will supply the audio buffers received from the audio data output. */
						AURenderCallbackStruct renderCallbackStruct;
						renderCallbackStruct.inputProc = PushCurrentInputBufferIntoAudioUnit;
						renderCallbackStruct.inputProcRefCon = self;
						err = AudioUnitSetProperty(effectAudioUnit, kAudioUnitProperty_SetRenderCallback, kAudioUnitScope_Input, 0, &renderCallbackStruct, sizeof(renderCallbackStruct));
					}
					
					if (noErr != err) {
						if (effectAudioUnit) {
							AudioComponentInstanceDispose(effectAudioUnit);
							effectAudioUnit = NULL;
						}
						
						[captureSession removeInput:captureAudioDeviceInput];
						[captureSession removeOutput:captureAudioDataOutput];
						
						[captureAudioDataOutput release];
						captureAudioDataOutput = nil;
						[captureAudioDeviceInput release];
						captureAudioDeviceInput = nil;
						[captureSession release];
						captureSession = nil;
					}else{
						[captureSession startRunning];
						[self setRunning:YES];
					}
					
				}else{
					/* couldn't add the output - tear down what we already built */
					[captureAudioDataOutput release];
					captureAudioDataOutput = nil;
					[captureSession removeInput:captureAudioDeviceInput];
					[captureAudioDeviceInput release];
					captureAudioDeviceInput = nil;
					[captureSession release];
					captureSession = nil;
				}
				
			}else{
				/* couldn't add the input */
				[captureAudioDeviceInput release];
				captureAudioDeviceInput = nil;
				[captureSession release];
				captureSession = nil;
			}
			
		}
		/* if captureAudioDeviceInput is nil here, the device couldn't be opened -
		   commonly a denied/missing microphone permission (see the note above
		   about NSMicrophoneUsageDescription). `error` describes why. */
	}
	
	return self;
}

- (void)dealloc 
{
	[self setRecording:NO];
	
	if(captureSession){
		[captureSession stopRunning];
		[self setRunning:NO];
	}
	
	if(captureAudioDataOutput){
		[captureAudioDataOutput setSampleBufferDelegate:nil queue:NULL];
	}
	
	if(captureSession){
		[captureSession release];
	}
	
	if(captureAudioDeviceInput){
		[captureAudioDeviceInput release];
	}
	
	if(captureAudioDataOutput){
		[captureAudioDataOutput release];
	}
	
	if(captureAudioDataOutputQueue){
		dispatch_release(captureAudioDataOutputQueue);
		captureAudioDataOutputQueue = NULL;
	}
	
	if (extAudioFile){
		ExtAudioFileDispose(extAudioFile);
	}
	
	if (effectAudioUnit) {
		if (didSetUpAudioUnits) {
			AudioUnitUninitialize(effectAudioUnit);
		}
		AudioComponentInstanceDispose(effectAudioUnit);
		effectAudioUnit = NULL;
	}
	
	[outputFile release];
	
	[super dealloc];
}

- (void)captureOutput:(AVCaptureOutput *)captureOutput didOutputSampleBuffer:(CMSampleBufferRef)sampleBuffer fromConnection:(AVCaptureConnection *)connection
{
	OSStatus err = noErr;
	
	BOOL isRecording = [self isRecording];
	
	/* Get the sample buffer's AudioStreamBasicDescription, which will be used to set the input format of the effect audio unit and the ExtAudioFile. */
	CMFormatDescriptionRef formatDescription = CMSampleBufferGetFormatDescription(sampleBuffer);
	if (!formatDescription)
		return;
	
	const AudioStreamBasicDescription *sampleBufferASBDPtr = CMAudioFormatDescriptionGetStreamBasicDescription(formatDescription);
	if (!sampleBufferASBDPtr)
		return;
	
	AudioStreamBasicDescription sampleBufferASBD = *sampleBufferASBDPtr;
	
	if ((sampleBufferASBD.mChannelsPerFrame != currentInputASBD.mChannelsPerFrame) || (sampleBufferASBD.mSampleRate != currentInputASBD.mSampleRate)) {
		/* Although AVCaptureAudioDataOutput guarantees that it will output sample buffers in the canonical format, the number of channels or the
		 sample rate of the audio can changes at any time while the capture session is running. If this occurs, the audio unit receiving the buffers
		 from the AVCaptureAudioDataOutput needs to be reconfigured with the new format. This also must be done when a buffer is received for the
		 first time. */
		
		currentInputASBD = sampleBufferASBD;
		
		if (didSetUpAudioUnits) {
			/* The audio units were previously set up, so they must be uninitialized now. */
			AudioUnitUninitialize(effectAudioUnit);
			
			/* If recording was in progress, the recording needs to be stopped because the audio format changed. */
			if (extAudioFile) {
				ExtAudioFileDispose(extAudioFile);
				extAudioFile = NULL;
			}
		} else {
			didSetUpAudioUnits = YES;
		}
		
		/* Set the input and output formats of the effect audio unit to match that of the sample buffer. */
		err = AudioUnitSetProperty(effectAudioUnit, kAudioUnitProperty_StreamFormat, kAudioUnitScope_Input, 0, &currentInputASBD, sizeof(currentInputASBD));
		
		if (noErr == err)
			err = AudioUnitSetProperty(effectAudioUnit, kAudioUnitProperty_StreamFormat, kAudioUnitScope_Output, 0, &currentInputASBD, sizeof(currentInputASBD));
		
		if (noErr == err)
			err = AudioUnitInitialize(effectAudioUnit);
		
		if (noErr != err) {
			NSLog(@"Failed to set up audio units (%d)", (int)err);
			
			didSetUpAudioUnits = NO;
			bzero(&currentInputASBD, sizeof(currentInputASBD));
		}
	}
	
	if (currentInputASBD.mChannelsPerFrame == 0) {
		/* No valid format established (or the format setup above just failed) -
		   nothing safe to do with this buffer. Without this guard,
		   (mChannelsPerFrame - 1) below would underflow (it's unsigned) and
		   drive an enormous calloc, which is a real crash risk. */
		return;
	}
	
	if (isRecording && !extAudioFile) {
		/* Start recording by creating an ExtAudioFile and configuring it with the same sample rate and channel layout as those of the current sample buffer. */
		AudioStreamBasicDescription recordedASBD = {0};
		recordedASBD.mSampleRate = currentInputASBD.mSampleRate;
		recordedASBD.mFormatID = kAudioFormatLinearPCM;
		recordedASBD.mFormatFlags = kAudioFormatFlagIsBigEndian | kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked;
		recordedASBD.mBytesPerPacket = 2 * currentInputASBD.mChannelsPerFrame;
		recordedASBD.mFramesPerPacket = 1;
		recordedASBD.mBytesPerFrame = 2 * currentInputASBD.mChannelsPerFrame;
		recordedASBD.mChannelsPerFrame = currentInputASBD.mChannelsPerFrame;
		recordedASBD.mBitsPerChannel = 16;
		
		size_t channelLayoutSize = 0;
		const AudioChannelLayout *recordedChannelLayout = CMAudioFormatDescriptionGetChannelLayout(formatDescription, &channelLayoutSize);
		
		err = ExtAudioFileCreateWithURL((CFURLRef)[NSURL fileURLWithPath:[self outputFile]],
										kAudioFileAIFFType,
										&recordedASBD,
										recordedChannelLayout,
										kAudioFileFlags_EraseFile,
										&extAudioFile);
		if (noErr == err) 
			err = ExtAudioFileSetProperty(extAudioFile, kExtAudioFileProperty_ClientDataFormat, sizeof(currentInputASBD), &currentInputASBD);
		
		if (noErr != err) {
			NSLog(@"Failed to set up ExtAudioFile (%d)", (int)err);
			
			if (extAudioFile) {
				ExtAudioFileDispose(extAudioFile);
				extAudioFile = NULL;
			}
		}
	} else if (!isRecording && extAudioFile) {
		/* Stop recording by disposing of the ExtAudioFile. */
		ExtAudioFileDispose(extAudioFile);
		extAudioFile = NULL;
	}
	
	CMItemCount numberOfFrames = CMSampleBufferGetNumSamples(sampleBuffer);	/* corresponds to the number of CoreAudio audio frames, same as -[QTSampleBuffer numberOfSamples] before it. */
	
	/* In order to render continuously, the effect audio unit needs a new time stamp for each buffer. Use the number of frames for each unit of time. */
	currentSampleTime += (double)numberOfFrames;
	
	AudioTimeStamp timeStamp = {0};
	timeStamp.mSampleTime = currentSampleTime;
	timeStamp.mFlags |= kAudioTimeStampSampleTimeValid;		
	
	AudioUnitRenderActionFlags flags = 0;
	
	/* Create an AudioBufferList large enough to hold the number of frames from the sample buffer in 32-bit floating point PCM format. */
	AudioBufferList *outputABL = (AudioBufferList *)calloc(1, sizeof(*outputABL) + (currentInputASBD.mChannelsPerFrame - 1)*sizeof(outputABL->mBuffers[0]));
	outputABL->mNumberBuffers = currentInputASBD.mChannelsPerFrame;
	UInt32 channelIndex;
	for (channelIndex = 0; channelIndex < currentInputASBD.mChannelsPerFrame; channelIndex++) {
		UInt32 dataSize = (UInt32)numberOfFrames * currentInputASBD.mBytesPerFrame;
		outputABL->mBuffers[channelIndex].mDataByteSize = dataSize;
		outputABL->mBuffers[channelIndex].mData = malloc(dataSize);
		outputABL->mBuffers[channelIndex].mNumberChannels = 1;
	}
	
	/*
	 Pull an audio buffer list out of the CMSampleBuffer and assign it to the currentInputAudioBufferList instance variable.
	 The effect audio unit render callback, PushCurrentInputBufferIntoAudioUnit(), accesses this value by calling the currentInputAudioBufferList method.
	 CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer follows the Create rule: blockBuffer must be released when we're done with it.
	 */
	CMBlockBufferRef blockBuffer = NULL;
	AudioBufferList capturedAudioBufferList;
	size_t capturedAudioBufferListSize = 0;
	
	err = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(sampleBuffer,
																	&capturedAudioBufferListSize,
																	&capturedAudioBufferList,
																	sizeof(capturedAudioBufferList),
																	NULL,
																	NULL,
																	kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment,
																	&blockBuffer);
	
	if (noErr == err) {
		
		currentInputAudioBufferList = &capturedAudioBufferList;
		
		/* Tell the effect audio unit to render. This will synchronously call PushCurrentInputBufferIntoAudioUnit(), which will feed the audio buffer list into the effect audio unit. */
		err = AudioUnitRender(effectAudioUnit, &flags, &timeStamp, 0, (UInt32)numberOfFrames, outputABL);
		currentInputAudioBufferList = NULL;
		
		if ((noErr == err) && extAudioFile) {
			err = ExtAudioFileWriteAsync(extAudioFile, (UInt32)numberOfFrames, outputABL);
		}
		
		if (blockBuffer) {
			CFRelease(blockBuffer);
		}
	}
	
	for (channelIndex = 0; channelIndex < currentInputASBD.mChannelsPerFrame; channelIndex++) {
		free(outputABL->mBuffers[channelIndex].mData);
	}
	free(outputABL);
}

/* Used by PushCurrentInputBufferIntoAudioUnit() to access the current audio buffer list that has been output by the AVCaptureAudioDataOutput. */
- (AudioBufferList *)currentInputAudioBufferList
{
	return currentInputAudioBufferList;
}

@end

static OSStatus PushCurrentInputBufferIntoAudioUnit(void *							inRefCon,
													AudioUnitRenderActionFlags *	ioActionFlags,
													const AudioTimeStamp *			inTimeStamp,
													UInt32							inBusNumber,
													UInt32							inNumberFrames,
													AudioBufferList *				ioData)
{
	AudioCapture *self = (AudioCapture *)inRefCon;
	
	if(![self isRecording])
		return siNoSoundInHardware;
	
	AudioBufferList *currentInputAudioBufferList = [self currentInputAudioBufferList];
	UInt32 bufferIndex, bufferCount = currentInputAudioBufferList->mNumberBuffers;
	
	if (bufferCount != ioData->mNumberBuffers)
		return badFormat;
	
	/* Fill the provided AudioBufferList with the data from the AudioBufferList output by the audio data output. */
	for (bufferIndex = 0; bufferIndex < bufferCount; bufferIndex++) {
		ioData->mBuffers[bufferIndex].mDataByteSize = currentInputAudioBufferList->mBuffers[bufferIndex].mDataByteSize;
		ioData->mBuffers[bufferIndex].mData = currentInputAudioBufferList->mBuffers[bufferIndex].mData;
		ioData->mBuffers[bufferIndex].mNumberChannels = currentInputAudioBufferList->mBuffers[bufferIndex].mNumberChannels;
	}
	
	return noErr;
}
