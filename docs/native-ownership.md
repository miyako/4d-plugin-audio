# Native ownership audit

Baseline: `af865dee787734a11b518f267cdc9488c0f90a45`.
Scope: first-party native string ownership, including compiled dormant wrappers.
No bundled engine SDK implementation, Apple helper, manifest, prebuilt binary,
project setting, or manual release workflow is changed.

## Inventory and reachability

The tracked native inventory comprises 23 translation units and 30 headers/prefix
headers. Both `manifest.json` and the bundled
`Audio.4dbase/Plugins/Audio.bundle/Contents/Resources/manifest.json` declare the
same 15 commands. `AUDIO DEVICE LIST(&Y;&Y;&L)` has array-capable metadata;
`&Y` alone does not establish a text array or its ownership contract.

`PluginMain` in `4DPlugin.cpp` routes selectors 2/3/4/15 through
`CommandDispatcherInMainProcess` for recording/conversion. Its other selectors
reach `CommandDispatcher`: selector 1 produces device arrays; 5-14 manipulate
sound references and numeric values. Startup/close-process selectors do not
export arrays. Recording and conversion copy scalar paths through `C_TEXT`;
the end-recording text return uses a content setter. No current selector invokes
`CPicture` or `C_POINTER`. There are no first-party object/collection getters,
JSON Parse calls, or owning method/function callback return values.

| Native surfaces (paths relative to repository root) | Compilation / ownership findings |
|---|---|
| `4DPlugin.cpp`, `4DPlugin.h`, `4D Plugin_Prefix.pch` | Actual dispatcher and declarations; scalar inputs copied before use, device names copied into `ARRAY_TEXT`, returned strings use `PA_SetUnistring`. Objective-C copied paths/URLs and retained sound references are released by callers. |
| `4D Plugin API/Classes/ARRAY_TEXT.cpp/.h` | Compiled by Xcode and Visual Studio. Copies borrowed incoming descriptors into C++ strings before output mutation. Allocates a distinct string for every output element, transfers it, does not dispose the transferred alias. Includes element zero, replacement and shrink semantics. No normal-path ownership defect found. |
| `4D Plugin API/Classes/C_TEXT.cpp/.h` | Compiled by both projects. Copies scalar UTF-16 inputs; UTF-8 conversion and platform path helpers use independent content; output/return content setters differ from descriptor transfer. No ownership change needed. |
| `4D Plugin API/Classes/C_PICTURE.cpp/.h` | Compiled by both projects despite no current command reaching it. Fixed shallow path double-disposal, overwritten initial string/picture allocations, retained output and temporary picture leaks, and UTF-16 bytes used as code units. Borrowed input detachment and owning returned-picture handoffs remain intact. |
| `4D Plugin API/Classes/C_POINTER.cpp/.h` | Compiled, dormant. `getVariable` interprets `PA_GetPointerValue` as variable-definition metadata (`fFiller=1`). Deferred: the header's cleanup instruction conflicts with the metadata interpretation; do not blindly clear or relabel an unverified value. |
| `4D Plugin API/Classes/ARRAY_BOOLEAN.cpp/.h`, `ARRAY_DATE.cpp/.h`, `ARRAY_INTEGER.cpp/.h`, `ARRAY_LONGINT.cpp/.h`, `ARRAY_REAL.cpp/.h`, `ARRAY_TIME.cpp/.h` | All compiled by both projects. Non-string element wrappers. `ARRAY_LONGINT` supplies active device IDs; other wrappers are dormant. No string allocations/transfers. |
| `4D Plugin API/Classes/C_BLOB.cpp/.h` | Compiled, dormant except picture byte-cache helper. Copies byte content; hex/base64 conversions use `C_TEXT`. No shallow string descriptor ownership. Unrelated byte-cache/empty-vector behavior is outside this fix. |
| `4D Plugin API/Classes/C_DATE.cpp/.h`, `C_INTEGER.cpp/.h`, `C_LONGINT.cpp/.h`, `C_REAL.cpp/.h`, `C_TIME.cpp/.h` | All compiled by both projects; scalar value copies, no owning strings. |
| `4D Plugin API/Classes/C_TYPES.h` | Tracked platform includes and string/vector type aliases, not an independently compiled source. |
| `AudioCapture/AudioCapture.mm/.h` | Xcode sources. `outputFile` is a copied property, released in `dealloc`; no `PA_Unistring` callbacks. Audio capture and asynchronous sample callbacks were inspected but not executed or redesigned. |
| `AudioDevice/AudioDevice.cpp/.h`, `AudioDeviceList.cpp/.h` | Xcode sources; Apple-derived helpers excluded from fixes. Names are copied through caller byte buffers into `BuildDeviceList`, then independently converted to UTF-16. No engine string owners. |
| `CADebugMacros.cpp/.h`, `CAStreamBasicDescription.cpp/.h`, `CAMath.h` | Apple-derived helpers excluded from fixes; Xcode compiles the two `.cpp` files, with `CAMath.h` included by the stream helper. Formatting/math/debug code has no engine string ownership. |
| `4D Plugin API/4DPluginAPI.c/.h`, `PublicTypes.h`, `PrivateTypes.h`, `EntryPoints.h`, `Flags.h`, `4DPluginAPI.def`, `licence.txt` | Bundled SDK boundary, definitions and export list, unchanged. Both projects compile this API and all 16 class implementations. Xcode uses Objective-C++; Visual Studio lists only the API/classes/dispatcher, not the macOS capture/device helpers. Its Windows build/runtime is not certified. |

`Audio.xcodeproj/project.pbxproj` and `Audio.vcxproj` resolve headers to this
single bundled API/classes directory. The lowercase `audio/Audio.xcodeproj`
contains workspace/user state, not another native project or SDK copy. No
separate native source or header resides in the bundled plugin; its existing
macOS/Windows executables are not regenerated by this audit.

## SDK evidence and fixes

Canonical guidance read from `miyako/skills`:
`4d-skills/skills/4dplugin/SKILL.md` at
`e6b492fcb81e5e1a7f7db723594b420e63bf6eb9`, including merged PRs 69 and 71.
The bundled SDK `.c` comment says v14 and its headers say v13; neither is a
verified upstream release identity. Provenance is the repository baseline and
these Git blob IDs:

| File in `4D Plugin API/` | Git blob |
|---|---|
| `4DPluginAPI.c` | `478081f0238f6bc5393222f574bc2656f010b67b` |
| `4DPluginAPI.h` | `9054b45ffc7ff6f5b8d57529a3788a55d977b314` |
| `PublicTypes.h` | `2bb392e73e9c556c274fe0a75b3a6b83e310b77c` |
| `PrivateTypes.h` | `77053dc0c0a3718d2d3b6f158371a6af78c6ae66` |

Verified against that implementation:

- `PA_SetStringInArray` (4444-4459) accepts only Unicode arrays with non-null
  data, index zero through `fNbElements`, and a non-null descriptor pointer.
  Acceptance disposes the old element and shallow-transfers the descriptor.
  Rejected type/index/data/null descriptor does not consume caller ownership.
  `PA_GetStringInArray` (4266-4283) returns a borrowed descriptor.
- `PA_SetStringVariable` (3826-3831) shallow-assigns without clearing old content.
  `PA_CreateVariable(eVK_Unistring)` (3523-3648) creates an empty owned string;
  picture creation similarly creates an owned empty picture. Initialize
  overwritten input variables as Undefined rather than leaking those empties.
- `PA_GetPictureVariable` explicitly returns a picture still owned by the
  variable. `setPicture` retains it with `PA_DuplicatePicture(..., 1)`, so the
  original argument/local owner must then be released. The fixed path clears
  its string argument exactly once and its picture argument after retaining.
- `createCopy` and `createGrayScale` retain an independent input reference,
  detach the resulting picture before clearing the argument, and return an
  owner that survives wrapper destruction. `getSize`/`createThumbnail` detach
  borrowed input pictures before argument cleanup; these detachments are kept.
- `PA_ConvertCharsetToCharset` (4776-4792) forwards source size and destination
  byte capacity and returns output bytes via `fParam3`. The fixed constructor
  divides that result by `sizeof(PA_Unichar)` for UTF-16 code units.
- `PA_ReturnString` calls `PA_SetUnistring`, an engine-backed content setter,
  rather than the array descriptor setter. Scalar cleanup was not removed.
- `PA_ExecuteCommandByID` passes pointers to the supplied variables synchronously
  and returns a separate variable. The picture helpers call procedures
  678/1002/988/457/679, not functions producing an owning result; the shim does
  not invent owning returned values for them.

## Regression evidence

Run on macOS with the installed Xcode compiler:

```sh
python3 tests/run_native_ownership.py --baseline
python3 -m unittest discover -s .github/tests -q
```

The **same harness** compiles all 16 actual class sources and the **entire
unchanged** `4DPluginAPI.c`, using bundled headers and prefix header, with
ASan/UBSan. Only `gCall4D` engine calls are simulated. The runner verifies every
non-class SDK file against the immutable baseline, extracts baseline sources
without altering a checkout, and deletes its temporary build files afterward.

| Case | Immutable baseline | Fixed source |
|---|---|---|
| `path` | String disposed twice | Pass; string and retained output owners balanced |
| `bytes` | Temporary picture reference leaked | Pass |
| `copy` | ASan heap-buffer-overflow in actual UTF-16 string construction | Pass; exact conversion text and owner balance |
| `grayscale` | Initial picture allocation leaked | Pass; owning handoff survives wrapper destruction |
| `size` | Initial picture allocation leaked | Pass; borrowed picture survives |
| `thumbnail` | Initial picture allocation leaked | Pass; borrowed input and independent output survive |
| `arrays` | Pass | Pass; independent transfers, borrowed copies, repeated replacement, shrink/clear, all setter rejection conditions |
| `scalars` | Pass | Pass; copied content survives input destruction, independent scalar owner and content-setting return |

Every case runs with allocated and null empty string representations. Fixed
picture/text cases assert exact ASCII, BMP, supplementary surrogate pairs and
empty text. Conversion capacity and returned length are bytes; termination is
outside content. Tracked string allocations, handle allocations, and picture
references must all balance explicitly; macOS LeakSanitizer is not used.
The failed picture-data getter deliberately returns poisoned metadata, which
the actual wrapper must not inspect or clear after the SDK reports an error.

The unsigned `Native ownership` CI runs these checks, all 40 existing lifecycle
tests, and syntax-only compilation of the remaining six native sources,
including the actual dispatcher and capture code. It does not construct
capture/device objects, play/record media, request permissions, or invoke
release scripts. The original Build/Bump workflows remain manual-only and
unchanged; no signing, packaging, publication or manual dispatch is needed.

## Deferred and untested boundaries

- Successful `PA_GetPictureData` metadata and SDK-only application-path outputs
  have insufficient ownership documentation. No guessed disposal was added;
  successful picture metadata enumeration is not certified by the shim.
- `C_POINTER` metadata ownership remains deferred as described above.
- SDK resize allocation-failure count corruption is outside scope. Normal
  resize tests do not establish allocation-failure correctness.
- No real 4D host, Windows execution, capture/playback device, external media,
  or exact original Windows Poppler crash was exercised. The shim verifies the
  named wrapper defects and the bundled SDK boundary, not the actual engine.
