#include "4DPluginAPI.h"
#include "PrivateTypes.h"
#include "EntryPoints.h"

#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <set>

// Only the engine boundary is simulated; all PA_* functions come from the
// complete, unchanged bundled SDK translation unit.
static std::set<PA_Unichar*> strings;
static std::map<PA_Handle, size_t> handles;
struct SyntheticPicture { unsigned refs; };
static std::set<SyntheticPicture*> pictures;
static bool allocatedEmpty;
static CUTF16String expected;

static void require(bool condition, const char* message)
{
    if (!condition) {
        std::fprintf(stderr, "ownership regression: %s\n", message);
        std::abort();
    }
}

static CUTF16String text(const char* utf8)
{
    CFStringRef s = CFStringCreateWithCString(nullptr, utf8, kCFStringEncodingUTF8);
    require(s != nullptr, "valid synthetic UTF-8");
    CUTF16String result(CFStringGetLength(s), 0);
    if (!result.empty())
        CFStringGetCharacters(s, CFRangeMake(0, result.size()), &result[0]);
    CFRelease(s);
    return result;
}

static PA_Unistring makeString(const PA_Unichar* source)
{
    const size_t n = source ? std::char_traits<PA_Unichar>::length(source) : 0;
    PA_Unistring result = {};
    if (n || allocatedEmpty) {
        result.fString = new PA_Unichar[n + 1];
        if (n) std::memcpy(result.fString, source, n * sizeof(PA_Unichar));
        result.fString[n] = 0;
        PA_Unichar* pointer = result.fString;
        strings.insert(pointer);
    }
    result.fLength = static_cast<PA_long32>(n);
    return result;
}

static void dropString(PA_Unistring& value)
{
    PA_Unichar* pointer = value.fString;
    if (pointer) {
        require(strings.erase(pointer) == 1, "string disposed twice or borrowed");
        delete[] pointer;
    }
    value = {};
}

static void checkString(PA_Unistring value, const CUTF16String& wanted)
{
    require(value.fLength == wanted.size(), "exact UTF-16 code-unit count");
    PA_Unichar* pointer = value.fString;
    if (pointer) {
        require(strings.count(pointer) == 1, "live string owner");
        require(value.fString[value.fLength] == 0, "terminator outside content");
        require(CUTF16String(value.fString, value.fLength) == wanted, "exact text");
    } else {
        require(wanted.empty(), "null only represents empty");
    }
}

static PA_Picture newPicture()
{
    SyntheticPicture* p = new SyntheticPicture{1};
    pictures.insert(p);
    return p;
}

static SyntheticPicture* livePicture(PA_Picture value)
{
    SyntheticPicture* p = static_cast<SyntheticPicture*>(value);
    require(p && pictures.count(p), "live picture handoff");
    return p;
}

static void dropPicture(PA_Picture value)
{
    if (!value) return;
    SyntheticPicture* p = livePicture(value);
    if (--p->refs == 0) {
        pictures.erase(p);
        delete p;
    }
}

static void clear(PA_Variable& value)
{
    switch (value.fType) {
        case eVK_Unistring: dropString(value.uValue.fString); break;
        case eVK_Picture: dropPicture(value.uValue.fPicture); break;
        case eVK_ArrayUnicode:
            if (value.uValue.fArray.fData) {
                PA_Unistring* data = reinterpret_cast<PA_Unistring*>(*value.uValue.fArray.fData);
                for (PA_long32 i = 0; i <= value.uValue.fArray.fNbElements; ++i)
                    dropString(data[i]);
                PA_DisposeHandle(value.uValue.fArray.fData);
            }
            break;
        case eVK_Undefined: case eVK_Longint: break;
        default: require(false, "unexpected variable cleanup");
    }
    value = {};
    value.fType = eVK_Undefined;
}

static void engine(short selector, EngineBlock* eb)
{
    switch (selector) {
        case EX_CREATE_UNISTRING:
            eb->fUniString1 = makeString(reinterpret_cast<PA_Unichar*>(eb->fHandle));
            break;
        case EX_DISPOSE_UNISTRING: dropString(eb->fUniString1); break;
        case EX_SET_UNISTRING: {
            // Copy before freeing the previous content, as a content setter.
            CUTF16String copy(reinterpret_cast<PA_Unichar*>(eb->fHandle));
            dropString(eb->fUniString1);
            eb->fUniString1 = makeString(copy.c_str());
            break;
        }
        case EX_CREATE_PICTURE: eb->fPicture = newPicture(); eb->fError = 0; break;
        case EX_DISPOSE_PICTURE: dropPicture(eb->fPicture); break;
        case EX_DUPLICATE_PICTURE:
            if (eb->fParam1 == 0) ++livePicture(eb->fPicture)->refs;
            else { livePicture(eb->fPicture); eb->fPicture = newPicture(); }
            break;
        case EX_GET_PICTURE_DATA:
            livePicture(eb->fPicture);
            // Metadata output ownership is undocumented here. Do not invent a
            // disposable successful result. Poison the failed output instead.
            eb->fError = eER_IncompatibleTypes;
            eb->fUniString1 = {};
            eb->fUniString1.fString = reinterpret_cast<PA_Unichar*>(1);
            break;
        case EX_CLEAR_VARIABLE: clear(*static_cast<PA_Variable*>(eb->fPtr1)); break;
        case EX_HANDLE_MANAGER: {
            PA_Handle handle;
            if (eb->fParam1 != 1) handle = eb->fHandle;
            switch (eb->fParam1) {
                case 1:
                    handle = new char*;
                    *handle = static_cast<char*>(std::calloc(1, eb->fParam2 ? eb->fParam2 : 1));
                    handles[handle] = eb->fParam2;
                    eb->fHandle = handle;
                    break;
                case 2:
                    require(handles.erase(handle) == 1, "handle disposed once");
                    std::free(*handle);
                    delete handle;
                    break;
                case 3: {
                    require(handles.count(handle), "resize live handle");
                    void* resized = std::realloc(*handle, eb->fParam2 ? eb->fParam2 : 1);
                    require(resized, "synthetic handle allocation");
                    *handle = static_cast<char*>(resized);
                    handles[handle] = eb->fParam2;
                    break;
                }
                case 4: eb->fParam2 = handles.at(handle); break;
                case 5:
                    require(handles.count(handle), "lock live handle");
                    eb->fParam3 = reinterpret_cast<sLONG_PTR>(*handle);
                    break;
                case 6: require(handles.count(handle), "unlock live handle"); break;
                default: require(false, "unexpected handle operation");
            }
            eb->fError = 0;
            break;
        }
        case EX_CONVERT_CHARSET_TO_CHARSET: {
            require(eb->fParam2 == eVTC_UTF_8 && eb->fParam4 == eVTC_UTF_16,
                    "expected UTF-8 to UTF-16 conversion");
            CFStringRef s = CFStringCreateWithBytes(nullptr,
                static_cast<UInt8*>(eb->fPtr1), eb->fParam1, kCFStringEncodingUTF8, false);
            require(s, "valid conversion input");
            const CFIndex n = CFStringGetLength(s);
            require(eb->fParam3 >= n * sizeof(PA_Unichar), "conversion capacity in bytes");
            require(eb->fParam3 == (eb->fParam1 + 1) * sizeof(PA_Unichar),
                    "wrapper supplies byte capacity including terminator space");
            CFStringGetCharacters(s, CFRangeMake(0, n), static_cast<UniChar*>(eb->fPtr2));
            require(static_cast<UniChar*>(eb->fPtr2)[n] == 0,
                    "conversion does not overwrite wrapper's zero terminator");
            CFRelease(s);
            eb->fParam3 = n * sizeof(PA_Unichar); // bytes, excluding terminator
            eb->fError = 0;
            break;
        }
        case EX_EXECUTE_COMMAND_BY_ID: {
            auto args = static_cast<PA_Variable**>(eb->fPtr1);
            auto returned = static_cast<PA_Variable*>(eb->fPtr2);
            require(returned->fType == eVK_Undefined, "initial command result");
            switch (eb->fParam1) {
                case 678:
                    require(eb->fParam2 == 2, "READ PICTURE FILE argument count");
                    require(args[0]->fType == eVK_Unistring, "typed path argument");
                    checkString(args[0]->uValue.fString, expected);
                    require(args[1]->fType == eVK_Picture, "typed picture output");
                    dropPicture(PA_GetPictureVariable(*args[1]));
                    PA_SetPictureVariable(args[1], newPicture());
                    break;
                case 1002:
                    require(args[1]->fType == eVK_Unistring, "typed conversion argument");
                    checkString(args[1]->uValue.fString, expected);
                    [[fallthrough]];
                case 988: {
                    livePicture(PA_GetPictureVariable(*args[0]));
                    dropPicture(PA_GetPictureVariable(*args[0]));
                    PA_SetPictureVariable(args[0], newPicture());
                    break;
                }
                case 457:
                    livePicture(PA_GetPictureVariable(*args[0]));
                    PA_SetLongintVariable(args[1], 12);
                    PA_SetLongintVariable(args[2], 34);
                    break;
                case 679:
                    livePicture(PA_GetPictureVariable(*args[0]));
                    require(PA_GetLongintVariable(*args[2]) == 12 &&
                            PA_GetLongintVariable(*args[3]) == 34, "thumbnail dimensions");
                    dropPicture(PA_GetPictureVariable(*args[1]));
                    PA_SetPictureVariable(args[1], newPicture());
                    break;
                default: require(false, "unexpected 4D command");
            }
            // These are procedures; do not manufacture owning return values.
            eb->fError = 0;
            break;
        }
        default: require(false, "unimplemented engine selector");
    }
}

extern "C" void PluginMain(PA_long32, PA_PluginParameters) {}

static void balanced()
{
    require(strings.empty(), "leaked string owner");
    require(handles.empty(), "leaked handle owner");
    require(pictures.empty(), "leaked picture reference");
}

static void pictureCase(const char* name)
{
    const char* fixtures[] = {"ASCII", "\xE6\x97\xA5\xE6\x9C\xAC",
                             "\xF0\x9F\x98\x80", ""};
    for (const char* fixture : fixtures) {
        expected = text(fixture);
        PA_Picture handoff = nullptr;
        {
            CPicture picture;
            if (std::strcmp(name, "path") == 0) {
                CUTF8String path(reinterpret_cast<const uint8_t*>(fixture));
                picture.fromFileAtPath(&path);
                livePicture(picture.getPicture());
                require(strings.empty(), "path argument and initial empty released");
                require(pictures.size() == 1 &&
                        livePicture(picture.getPicture())->refs == 1, "path output owner released");
            } else if (std::strcmp(name, "bytes") == 0) {
                const uint8_t bytes[] = {0, 1, 2};
                picture.setBytes(bytes, sizeof(bytes));
                picture.setBytes(bytes, 0);
                require(pictures.size() == 1 &&
                        livePicture(picture.getPicture())->refs == 1, "setBytes temporary released");
            } else if (std::strcmp(name, "copy") == 0) {
                handoff = picture.createCopy(fixture);
                require(strings.empty(), "conversion string and initial empty released");
                require(pictures.size() == 2, "copy has exactly two picture owners");
            } else if (std::strcmp(name, "grayscale") == 0) {
                handoff = picture.createGrayScale();
                require(pictures.size() == 2, "grayscale initial picture released");
            } else if (std::strcmp(name, "size") == 0) {
                unsigned width = 0, height = 0;
                picture.getSize(&width, &height);
                require(width == 12 && height == 34, "size output values");
                require(pictures.size() == 1 &&
                        livePicture(picture.getPicture())->refs == 1, "size borrowed owner preserved");
            } else if (std::strcmp(name, "thumbnail") == 0) {
                handoff = picture.createThumbnail(12, 34);
                require(pictures.size() == 2, "thumbnail borrowed input and owned output");
            } else require(false, "unknown picture test");
            if (handoff) require(livePicture(handoff)->refs == 1, "independent returned owner");
        }
        if (handoff) {
            require(livePicture(handoff)->refs == 1, "handoff survives wrapper destruction");
            PA_DisposePicture(handoff);
        }
        balanced();
    }
}

static void arrayCase()
{
    PA_Variable array = PA_CreateVariable(eVK_Undefined);
    BytePtr params[] = {reinterpret_cast<BytePtr>(&array)};
    const char* fixtures[] = {"", "ASCII", "\xE6\x97\xA5", "\xF0\x9F\x98\x80", "ASCII"};
    ARRAY_TEXT output;
    for (const char* fixture : fixtures) {
        CUTF16String value = text(fixture);
        output.appendUTF16String(value.c_str(), value.size());
    }
    for (unsigned repeat = 0; repeat < 3; ++repeat) {
        output.toParamAtIndex(params, 1);
        for (unsigned i = 0; i < 5; ++i)
            checkString(PA_GetStringInArray(array, i), text(fixtures[i]));
        require(PA_GetStringInArray(array, 1).fString !=
                PA_GetStringInArray(array, 4).fString, "independent equal-text transfers");
    }
    ARRAY_TEXT copy;
    copy.fromParamAtIndex(params, 1);
    PA_ResizeArray(&array, 0);
    PA_ClearVariable(&array);
    copy.toParamAtIndex(params, 1);
    for (unsigned i = 0; i < 5; ++i)
        checkString(PA_GetStringInArray(array, i), text(fixtures[i]));

    PA_Unistring candidate = PA_CreateUnistring(const_cast<PA_Unichar*>(text("caller").c_str()));
    PA_Unichar* original = candidate.fString;
    PA_Variable wrong = PA_CreateVariable(eVK_Longint);
    PA_SetStringInArray(wrong, 0, &candidate);
    PA_SetStringInArray(array, -1, &candidate);
    PA_SetStringInArray(array, 99, &candidate);
    PA_Variable noData = {};
    noData.fType = eVK_ArrayUnicode;
    noData.uValue.fArray.fNbElements = 1;
    PA_SetStringInArray(noData, 0, &candidate);
    PA_Unistring first = PA_GetStringInArray(array, 0);
    PA_SetStringInArray(array, 0, nullptr);
    require(PA_GetStringInArray(array, 0).fString == first.fString, "null descriptor rejection");
    require(candidate.fString == original, "rejected descriptor retained");
    checkString(candidate, text("caller"));
    PA_DisposeUnistring(&candidate);
    CUTF16String callbackText = text("independent");
    PA_Unistring accepted = PA_CreateUnistring(const_cast<PA_Unichar*>(callbackText.c_str()));
    PA_Unichar* transferred = accepted.fString;
    PA_SetStringInArray(array, 0, &accepted);
    require(accepted.fString == transferred &&
            PA_GetStringInArray(array, 0).fString == transferred,
            "accepted transfer keeps local alias, not a second owner");
    PA_Variable callback = PA_CreateVariable(eVK_Undefined);
    PA_Unistring independent = PA_CreateUnistring(const_cast<PA_Unichar*>(callbackText.c_str()));
    PA_SetStringVariable(&callback, &independent);
    require(callback.uValue.fString.fString != transferred, "independent scalar and array owners");
    PA_ClearVariable(&array);
    checkString(callback.uValue.fString, callbackText);
    PA_ClearVariable(&callback);
    balanced();
}

static void scalarCase()
{
    for (const char* fixture : {"", "ASCII", "\xE6\x97\xA5", "\xF0\x9F\x98\x80"}) {
        CUTF16String value = text(fixture);
        PA_Unistring source = PA_CreateUnistring(const_cast<PA_Unichar*>(value.c_str()));
        C_TEXT copy;
        copy.setUTF16String(&source);
        PA_Variable callback = PA_CreateVariable(eVK_Undefined);
        PA_Unistring independent = PA_CreateUnistring(const_cast<PA_Unichar*>(value.c_str()));
        PA_SetStringVariable(&callback, &independent);
        checkString(callback.uValue.fString, value);
        PA_ClearVariable(&callback);
        PA_DisposeUnistring(&source);
        PA_Unistring destination = PA_CreateUnistring(nullptr);
        BytePtr params[] = {reinterpret_cast<BytePtr>(&destination)};
        copy.toParamAtIndex(params, 1);
        checkString(destination, value);
        PA_Unistring* result = &destination;
        copy.setReturn(reinterpret_cast<sLONG_PTR*>(&result));
        checkString(destination, value);
        PA_DisposeUnistring(&destination);
        balanced();
    }
}

int main(int argc, char** argv)
{
    require(argc == 3, "usage: native_ownership CASE allocated|null");
    allocatedEmpty = std::strcmp(argv[2], "allocated") == 0;
    gCall4D = engine;
    if (std::strcmp(argv[1], "arrays") == 0) arrayCase();
    else if (std::strcmp(argv[1], "scalars") == 0) scalarCase();
    else pictureCase(argv[1]);
    balanced();
    std::printf("PASS %s (%s empty)\n", argv[1], argv[2]);
}
