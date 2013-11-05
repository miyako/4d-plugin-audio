#import "AudioCapture.h"

#import <QTKit/QTKit.h>

static OSStatus PushCurrentInputBufferIntoAudioUnit(void *							inRefCon,
													AudioUnitRenderActionFlags *	ioActionFlags,
													const AudioTimeStamp *			inTimeStamp,
													UInt32							inBusNumber,
													UInt32							inNumberFrames,
													AudioBufferList *				ioData);

@implementation AudioCapture

@synthesize outputFile;
@synthesize recording;
@synthesize running;

- (id)initWithPath:(NSString *)path
{
	if(!(self = [super init]))return self;
	
	self.outputFile = path;
	
	QTCaptureDevice *audioDevice = [QTCaptureDevice defaultInputDeviceWithMediaType:QTMediaTypeSound];
	
	BOOL success;
	NSError *error;
	
	success = [audioDevice open:&error];
	
	if (success) {
		
		captureSession = [[QTCaptureSession alloc]init];
		captureAudioDeviceInput = [[QTCaptureDeviceInput alloc] initWithDevice:audioDevice];
		success = [captureSession addInput:captureAudioDeviceInput error:&error];
		
		if (!success) {
			[captureAudioDeviceInput release];
			captureAudioDeviceInput = nil;
			[audioDevice close];
			[captureSession release];
			captureSession = nil;
		}else{
		
			captureAudioDataOutput = [[QTCaptureDecompressedAudioOutput alloc]init];
			[captureAudioDataOutput setDelegate:self];
			success = [captureSession addOutput:captureAudioDataOutput error:&error];
			
			if (!success) {
				[captureAudioDeviceInput release];
				captureAudioDeviceInput = nil;
				[audioDevice close];		
				[captureAudioDataOutput release];
				captureAudioDataOutput = nil;
				[captureSession release];
				captureSession = nil;
			}
			
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
				
				[captureAudioDeviceInput release];
				captureAudioDeviceInput = nil;
				[audioDevice close];
				
				[captureSession release];
				captureSession = nil;
			}else{
				[captureSession startRunning];
				[self setRunning:YES];
			}
		}
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
	
	if(captureAudioDeviceInput){
		QTCaptureDevice *audioDevice = [captureAudioDeviceInput device];
		if(audioDevice){
			if ([audioDevice isOpen])
				[audioDevice close];
		}
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
	
	if (extAudioFile){
		ExtAudioFileDispose(extAudioFile);
	}
	
	[outputFile release];
	
	[super dealloc];
}

- (void)captureOutput:(QTCaptureOutput *)captureOutput didOutputAudioSampleBuffer:(QTSampleBuffer *)sampleBuffer fromConnection:(QTCaptureConnection *)connection
{
	OSStatus err = noErr;
	
	BOOL isRecording = [self isRecording];
	
    /* Get the sample buffer's AudioStreamBasicDescription, which will be used to set the input format of the effect audio unit and the ExtAudioFile. */
	QTFormatDescription *formatDescription = [sampleBuffer formatDescription];
    NSValue *sampleBufferASBDValue = [formatDescription attributeForKey:QTFormatDescriptionAudioStreamBasicDescriptionAttribute];
    if (!sampleBufferASBDValue)
        return;
    
    AudioStreamBasicDescription sampleBufferASBD = {0};
    [sampleBufferASBDValue getValue:&sampleBufferASBD];    
    
    if ((sampleBufferASBD.mChannelsPerFrame != currentInputASBD.mChannelsPerFrame) || (sampleBufferASBD.mSampleRate != currentInputASBD.mSampleRate)) {
        /* Although QTCaptureAudioDataOutput guarantees that it will output sample buffers in the canonical format, the number of channels or the
         sample rate of the audio can changes at any time while the capture session is running. If this occurs, the audio unit receiving the buffers
         from the QTCaptureAudioDataOutput needs to be reconfigured with the new format. This also must be done when a buffer is received for the
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
			NSLog(@"Failed to set up audio units (%d)", err);
			
			didSetUpAudioUnits = NO;
			bzero(&currentInputASBD, sizeof(currentInputASBD));
		}
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
		
		NSData *inputChannelLayoutData = [formatDescription attributeForKey:QTFormatDescriptionAudioChannelLayoutAttribute];
		AudioChannelLayout *recordedChannelLayout = (AudioChannelLayout *)[inputChannelLayoutData bytes];
		
		err = ExtAudioFileCreateWithURL((CFURLRef)[NSURL fileURLWithPath:[self outputFile]],
										kAudioFileAIFFType,
										&recordedASBD,
										recordedChannelLayout,
										kAudioFileFlags_EraseFile,
										&extAudioFile);
		if (noErr == err) 
			err = ExtAudioFileSetProperty(extAudioFile, kExtAudioFileProperty_ClientDataFormat, sizeof(currentInputASBD), &currentInputASBD);
		
		if (noErr != err) {
			NSLog(@"Failed to set up ExtAudioFile (%d)", err);
			
			ExtAudioFileDispose(extAudioFile);
			extAudioFile = NULL;
		}
	} else if (!isRecording && extAudioFile) {
		/* Stop recording by disposing of the ExtAudioFile. */
		ExtAudioFileDispose(extAudioFile);
		extAudioFile = NULL;
	}
    
    NSUInteger numberOfFrames = [sampleBuffer numberOfSamples];	/* -[QTSampleBuffer numberOfSamples] corresponds to the number of CoreAudio audio frames. */
	
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
		UInt32 dataSize = numberOfFrames * currentInputASBD.mBytesPerFrame;
		outputABL->mBuffers[channelIndex].mDataByteSize = dataSize;
		outputABL->mBuffers[channelIndex].mData = malloc(dataSize);
		outputABL->mBuffers[channelIndex].mNumberChannels = 1;
	}
	
	/*
	 Get an audio buffer list from the sample buffer and assign it to the currentInputAudioBufferList instance variable.
	 The the effect audio unit render callback, PushCurrentInputBufferIntoAudioUnit(), can access this value by calling the currentInputAudioBufferList method.
	 */
    currentInputAudioBufferList = [sampleBuffer audioBufferListWithOptions:QTSampleBufferAudioBufferListOptionAssure16ByteAlignment];
    
    /* Tell the effect audio unit to render. This will synchronously call PushCurrentInputBufferIntoAudioUnit(), which will feed the audio buffer list into the effect audio unit. */
    err = AudioUnitRender(effectAudioUnit, &flags, &timeStamp, 0, numberOfFrames, outputABL);
    currentInputAudioBufferList = NULL;
	
	if ((noErr == err) && extAudioFile) {
		err = ExtAudioFileWriteAsync(extAudioFile, numberOfFrames, outputABL);
	}
	
	for (channelIndex = 0; channelIndex < currentInputASBD.mChannelsPerFrame; channelIndex++) {
		free(outputABL->mBuffers[channelIndex].mData);
	}
	free(outputABL);
}

/* Used by PushCurrentInputBufferIntoAudioUnit() to access the current audio buffer list that has been output by the QTCaptureAudioDataOutput. */
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
