/*
     File: AudioDevice.h 
 Abstract: CAPlayThough Classes. 
  Version: 1.2.2 
  
 Disclaimer: IMPORTANT:  This Apple software is supplied to you by Apple 
 Inc. ("Apple") in consideration of your agreement to the following 
 terms, and your use, installation, modification or redistribution of 
 this Apple software constitutes acceptance of these terms.  If you do 
 not agree with these terms, please do not use, install, modify or 
 redistribute this Apple software. 
  
 In consideration of your agreement to abide by the following terms, and 
 subject to these terms, Apple grants you a personal, non-exclusive 
 license, under Apple's copyrights in this original Apple software (the 
 "Apple Software"), to use, reproduce, modify and redistribute the Apple 
 Software, with or without modifications, in source and/or binary forms; 
 provided that if you redistribute the Apple Software in its entirety and 
 without modifications, you must retain this notice and the following 
 text and disclaimers in all such redistributions of the Apple Software. 
 Neither the name, trademarks, service marks or logos of Apple Inc. may 
 be used to endorse or promote products derived from the Apple Software 
 without specific prior written permission from Apple.  Except as 
 expressly stated in this notice, no other rights or licenses, express or 
 implied, are granted by Apple herein, including but not limited to any 
 patent rights that may be infringed by your derivative works or by other 
 works in which the Apple Software may be incorporated. 
  
 The Apple Software is provided by Apple on an "AS IS" basis.  APPLE 
 MAKES NO WARRANTIES, EXPRESS OR IMPLIED, INCLUDING WITHOUT LIMITATION 
 THE IMPLIED WARRANTIES OF NON-INFRINGEMENT, MERCHANTABILITY AND FITNESS 
 FOR A PARTICULAR PURPOSE, REGARDING THE APPLE SOFTWARE OR ITS USE AND 
 OPERATION ALONE OR IN COMBINATION WITH YOUR PRODUCTS. 
  
 IN NO EVENT SHALL APPLE BE LIABLE FOR ANY SPECIAL, INDIRECT, INCIDENTAL 
 OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF 
 SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS 
 INTERRUPTION) ARISING IN ANY WAY OUT OF THE USE, REPRODUCTION, 
 MODIFICATION AND/OR DISTRIBUTION OF THE APPLE SOFTWARE, HOWEVER CAUSED 
 AND WHETHER UNDER THEORY OF CONTRACT, TORT (INCLUDING NEGLIGENCE), 
 STRICT LIABILITY OR OTHERWISE, EVEN IF APPLE HAS BEEN ADVISED OF THE 
 POSSIBILITY OF SUCH DAMAGE. 
  
 Copyright (C) 2013 Apple Inc. All Rights Reserved. 
  
*/

#ifndef __AudioDevice_h__
#define __AudioDevice_h__

#include <CoreServices/CoreServices.h>
#include <CoreAudio/CoreAudio.h>

// verify_noerr (and its siblings require/require_noerr/verify) are the
// underscore-free convenience macros from Apple's <AssertMacros.h>. They are
// only defined when __ASSERT_MACROS_DEFINE_VERSIONS_WITHOUT_UNDERSCORES is
// set to 1 *before AssertMacros.h's first inclusion in the translation
// unit*. Older SDKs had Carbon/CoreServices set that flag implicitly; on
// newer SDKs (seen breaking CI with Xcode 26.6 / macOS 26.5 SDK:
// "use of undeclared identifier 'verify_noerr'" in AudioDevice.cpp) they no
// longer do, and by the time this header's own #include lines run, the
// 4D-generated precompiled prefix header has typically already pulled in
// Carbon.h/CoreServices.h (without the flag set), so simply defining the
// flag and re-including <AssertMacros.h> here would be a no-op due to its
// include guard. Providing our own fallback, guarded so it steps aside if
// the macro is already available, keeps this file portable across SDKs
// without depending on prefix-header contents we don't control.
#ifndef verify_noerr
	#define verify_noerr(errorCode) do { OSStatus _voe_err = (OSStatus)(errorCode); (void)_voe_err; } while(0)
#endif

class AudioDevice {
public:
	AudioDevice() : mID(kAudioDeviceUnknown) { }
	AudioDevice(AudioDeviceID devid, bool isInput) { Init(devid, isInput); }

	void	Init(AudioDeviceID devid, bool isInput);
	
	bool	Valid() { return mID != kAudioDeviceUnknown; }
	
	void	SetBufferSize(UInt32 size);
	
	int		CountChannels();
	char *	GetName(char *buf, UInt32 maxlen);

public:
	AudioDeviceID					mID;
	bool							mIsInput;
	UInt32							mSafetyOffset;
	UInt32							mBufferSizeFrames;
	AudioStreamBasicDescription		mFormat;	
};


#endif // __AudioDevice_h__
